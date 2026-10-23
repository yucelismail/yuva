#!/usr/bin/env python3
"""In-memory mock for the Yuva model-session adapter contract.

No network, subprocess, terminal, or Yuva imports are used. This is a contract
sketch, not a production adapter.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any


STATUSES = {"queued", "accepted", "running", "completed", "failed", "waiting_approval"}
TRANSITIONS = {
    "queued": {"accepted", "failed"},
    "accepted": {"running", "waiting_approval", "failed"},
    "running": {"waiting_approval", "completed", "failed"},
    # This fake has no approval-answer/resume operation; pending approval can
    # only be observed or fail in this prototype.
    "waiting_approval": {"failed"},
    "completed": set(),
    "failed": set(),
}


class ContractError(ValueError):
    """An invalid adapter-contract operation."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Session:
    yuva_identity: str
    session_id: str
    cwd: str
    ownership: str = "yuva_owned"
    adapter: str = "mock"
    adapter_version: str = "0.1"


@dataclass(frozen=True)
class Delivery:
    yuva_identity: str
    session_id: str
    message_id: str
    text: str
    status: str = "queued"
    response: str | None = None
    error: str | None = None
    accepted_at: str | None = None
    updated_at: str = ""


class MockTransport:
    """Fake transport: records admission locally and never contacts a tool."""

    name = "fake-memory"

    def __init__(self) -> None:
        self._admitted: dict[tuple[str, str], tuple[str, str]] = {}

    def admit(self, session_id: str, message_id: str, text: str) -> str:
        """Return the original acceptance timestamp for new or duplicate content."""
        key = (session_id, message_id)
        previous = self._admitted.get(key)
        if previous is not None:
            previous_text, accepted_at = previous
            if previous_text != text:
                raise ContractError("message_id already exists with different content")
            return accepted_at
        accepted_at = now()
        self._admitted[key] = (text, accepted_at)
        return accepted_at


class MockAdapter:
    """Reference identity/session/delivery semantics over a fake transport."""

    def __init__(self, transport: MockTransport | None = None) -> None:
        self.transport = transport or MockTransport()
        self.sessions: dict[str, Session] = {}
        self.deliveries: dict[tuple[str, str], Delivery] = {}
        self.events: list[dict[str, Any]] = []

    def capabilities(self) -> dict[str, Any]:
        return {
            "adapter": "mock",
            "version": "0.1",
            "transport": self.transport.name,
            "features": ["identity_session_mapping", "idempotent_submit", "event_cursor", "reconcile"],
            "real_connections": False,
            "approval_decision": False,
        }

    def attach_or_start(
        self,
        yuva_identity: str,
        cwd: str,
        session_id: str | None = None,
        ownership: str = "yuva_owned",
    ) -> Session:
        if not yuva_identity.strip() or not cwd.strip():
            raise ContractError("yuva_identity and cwd are required")
        current = self.sessions.get(yuva_identity)
        if current:
            if session_id and current.session_id != session_id:
                raise ContractError("identity is already mapped to a different session")
            if current.cwd != cwd:
                raise ContractError("identity session cwd mismatch")
            return current
        new_id = session_id or f"mock-{uuid.uuid4().hex}"
        if not new_id.startswith("mock-"):
            raise ContractError("mock sessions must use a mock- session_id")
        if any(existing.session_id == new_id for existing in self.sessions.values()):
            raise ContractError("session_id is already mapped to another Yuva identity")
        session = Session(yuva_identity, new_id, cwd, ownership)
        self.sessions[yuva_identity] = session
        self._event(session, "session_attached")
        return session

    def submit(self, yuva_identity: str, session_id: str, message_id: str, text: str) -> Delivery:
        session = self._session(yuva_identity, session_id)
        if not message_id.strip() or not text.strip():
            raise ContractError("message_id and text are required")
        key = (session_id, message_id)
        existing = self.deliveries.get(key)
        if existing:
            if existing.yuva_identity != yuva_identity or existing.text != text:
                raise ContractError("message_id idempotency conflict")
            return existing

        # Admission returns the same receipt for an identical message even when
        # another adapter sharing this transport admitted it first. Resolve a
        # payload conflict before adding local delivery state or events.
        accepted_at = self.transport.admit(session_id, message_id, text)
        delivery = Delivery(yuva_identity, session_id, message_id, text, updated_at=now())
        self.deliveries[key] = delivery
        self._event(session, "delivery_status", delivery=delivery, status="queued")

        # Fake transport admission means accepted, never completed.
        delivery = replace(
            delivery,
            status="accepted",
            accepted_at=accepted_at,
            updated_at=now(),
        )
        self.deliveries[key] = delivery
        self._event(session, "delivery_status", delivery=delivery, status="accepted")
        return delivery

    def mark_running(self, yuva_identity: str, session_id: str, message_id: str) -> Delivery:
        delivery = self._delivery(yuva_identity, session_id, message_id)
        return self._transition(delivery, "running", "turn_started")

    def wait_for_approval(self, yuva_identity: str, session_id: str, message_id: str) -> Delivery:
        delivery = self._delivery(yuva_identity, session_id, message_id)
        return self._transition(delivery, "waiting_approval", "approval_requested")

    def complete(self, yuva_identity: str, session_id: str, message_id: str, response: str) -> Delivery:
        delivery = self._delivery(yuva_identity, session_id, message_id)
        if delivery.status != "running":
            raise ContractError("only a running delivery can complete")
        return self._transition(replace(delivery, response=response), "completed", "turn_completed")

    def fail(self, yuva_identity: str, session_id: str, message_id: str, error: str) -> Delivery:
        delivery = self._delivery(yuva_identity, session_id, message_id)
        return self._transition(replace(delivery, error=error), "failed", "turn_failed")

    def read_status(self, yuva_identity: str, session_id: str, message_id: str) -> dict[str, Any]:
        return asdict(self._delivery(yuva_identity, session_id, message_id))

    def reconcile(self, yuva_identity: str, session_id: str, after_seq: int = 0) -> dict[str, Any]:
        session = self._session(yuva_identity, session_id)
        latest_seq = self.events[-1]["seq"] if self.events else 0
        if type(after_seq) is not int or after_seq < 0:
            raise ContractError("after_seq must be a non-negative integer cursor")
        if after_seq > latest_seq:
            raise ContractError("after_seq is ahead of the current global cursor")
        later = [
            event for event in self.events
            if event["yuva_identity"] == yuva_identity
            and event["session_id"] == session_id
            and event["seq"] > after_seq
        ]
        return {
            "session": asdict(session),
            "deliveries": [
                asdict(item)
                for (sid, _), item in self.deliveries.items()
                if sid == session_id and item.yuva_identity == yuva_identity
            ],
            "events": deepcopy(later),
            # Global cursor lets a reconnect move beyond other sessions' events too.
            "next_cursor": latest_seq,
        }

    def _session(self, yuva_identity: str, session_id: str) -> Session:
        session = self.sessions.get(yuva_identity)
        if session is None or session.session_id != session_id:
            raise ContractError("unknown identity/session mapping")
        return session

    def _delivery(self, yuva_identity: str, session_id: str, message_id: str) -> Delivery:
        self._session(yuva_identity, session_id)
        try:
            delivery = self.deliveries[(session_id, message_id)]
        except KeyError as exc:
            raise ContractError("unknown session/message_id") from exc
        if delivery.yuva_identity != yuva_identity:
            raise ContractError("message belongs to another Yuva identity")
        return delivery

    def _transition(self, delivery: Delivery, status: str, event_type: str) -> Delivery:
        if status not in STATUSES or status not in TRANSITIONS.get(delivery.status, set()):
            raise ContractError(f"invalid transition {delivery.status} -> {status}")
        changed = replace(delivery, status=status, updated_at=now())
        key = (changed.session_id, changed.message_id)
        self.deliveries[key] = changed
        self._event(self.sessions[changed.yuva_identity], event_type, delivery=changed, status=status)
        return changed

    def _event(
        self,
        session: Session,
        event_type: str,
        delivery: Delivery | None = None,
        **extra: Any,
    ) -> None:
        item: dict[str, Any] = {
            "seq": len(self.events) + 1,
            "ts": now(),
            "type": event_type,
            "yuva_identity": session.yuva_identity,
            "session_id": session.session_id,
        }
        if delivery:
            # Snapshot the dataclass as plain JSON data; never store a live object
            # reference in the event log.
            item["message_id"] = delivery.message_id
            item["status"] = delivery.status
            item["delivery"] = asdict(delivery)
        item.update(extra)
        self.events.append(item)


def self_check() -> dict[str, Any]:
    """Exercise fake-only delivery, isolation, serialization, and reconciliation."""
    adapter = MockAdapter()
    first_session = adapter.attach_or_start("agent3", "/tmp/yuva-mock-workspace")
    try:
        adapter.attach_or_start(
            "agent-b", "/tmp/yuva-mock-collision", session_id=first_session.session_id
        )
    except ContractError:
        pass
    else:
        raise AssertionError("one session_id cannot map to two Yuva identities")
    second_session = adapter.attach_or_start("agent4", "/tmp/yuva-mock-other-workspace")
    first = adapter.submit("agent3", first_session.session_id, "yuva-msg-1", "mock request")
    duplicate = adapter.submit("agent3", first_session.session_id, "yuva-msg-1", "mock request")
    assert first is duplicate and first.status == "accepted"
    adapter.mark_running("agent3", first_session.session_id, first.message_id)
    adapter.wait_for_approval("agent3", first_session.session_id, first.message_id)
    adapter.submit("agent4", second_session.session_id, "yuva-msg-2", "other mock request")

    pending = adapter.reconcile("agent3", first_session.session_id, after_seq=2)
    other = adapter.reconcile("agent4", second_session.session_id)
    assert pending["deliveries"][0]["status"] == "waiting_approval"
    assert pending["events"] and all(
        event["yuva_identity"] == "agent3" and event["session_id"] == first_session.session_id
        for event in pending["events"]
    )
    assert all(
        event["yuva_identity"] == "agent4" and event["session_id"] == second_session.session_id
        for event in other["events"]
    )
    assert [item["message_id"] for item in pending["deliveries"]] == ["yuva-msg-1"]
    assert [item["message_id"] for item in other["deliveries"]] == ["yuva-msg-2"]
    json.dumps(pending, ensure_ascii=False)
    json.dumps(other, ensure_ascii=False)
    first_event_seq = pending["events"][0]["seq"]
    stored_event_type = adapter.events[first_event_seq - 1]["type"]
    pending["events"][0]["type"] = "caller-mutated-copy"
    pending["deliveries"][0]["status"] = "caller-mutated-copy"
    assert adapter.events[first_event_seq - 1]["type"] == stored_event_type
    assert adapter.read_status("agent3", first_session.session_id, "yuva-msg-1")["status"] == "waiting_approval"

    try:
        adapter.submit("agent3", first_session.session_id, "yuva-msg-1", "changed payload")
    except ContractError:
        pass
    else:
        raise AssertionError("changed payload must fail idempotency check")
    # Every state/status operation requires the owner identity and session.
    before_wrong_owner_calls = len(adapter.events)
    wrong_owner_calls = [
        lambda: adapter.mark_running("agent4", first_session.session_id, first.message_id),
        lambda: adapter.wait_for_approval("agent4", first_session.session_id, first.message_id),
        lambda: adapter.complete("agent4", first_session.session_id, first.message_id, "no"),
        lambda: adapter.fail("agent4", first_session.session_id, first.message_id, "no"),
        lambda: adapter.read_status("agent4", first_session.session_id, first.message_id),
    ]
    for operation in wrong_owner_calls:
        try:
            operation()
        except ContractError:
            pass
        else:
            raise AssertionError("wrong identity must not read or mutate another delivery")
    assert len(adapter.events) == before_wrong_owner_calls

    # Public objects are immutable snapshots; dict status reads are copies.
    try:
        first.status = "completed"  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:
        raise AssertionError("returned Delivery must be immutable")
    status_snapshot = adapter.read_status("agent3", first_session.session_id, first.message_id)
    status_snapshot["status"] = "completed"
    assert adapter.read_status("agent3", first_session.session_id, first.message_id)["status"] == "waiting_approval"

    latest = adapter.events[-1]["seq"]
    at_end = adapter.reconcile("agent3", first_session.session_id, after_seq=latest)
    assert at_end["events"] == [] and at_end["next_cursor"] == latest
    try:
        adapter.reconcile("agent3", first_session.session_id, after_seq=latest + 1)
    except ContractError:
        pass
    else:
        raise AssertionError("a cursor ahead of the global event sequence must be rejected")

    final_delivery = adapter.fail("agent3", first_session.session_id, first.message_id, "mock approval left pending")
    final = adapter.read_status("agent3", first_session.session_id, first.message_id)
    assert final["status"] == "failed"
    return {
        "result": "PASS",
        "transport": adapter.transport.name,
        "session_isolation": "two identities; reconcile events stayed within each session",
        "session_id_collision": "same session_id rejected for another identity",
        "delivery_isolation": "reconcile deliveries stayed within each identity/session",
        "event_serialization": "json.dumps(reconcile(...)) succeeded for both sessions",
        "ownership_checks": "wrong identity rejected for running, approval, complete, fail, and status",
        "immutable_results": "Delivery is frozen; read/reconcile copies cannot mutate state or events",
        "cursor_boundary": "equal-to-end returns no events; ahead-of-end cursor is rejected",
        "duplicate_submit": "same delivery returned",
        "approval": "waiting_approval surfaced; no approval API exists",
        "approval_continuation": "waiting_approval has no resume/approve path; failure is terminal",
        "reconcile_events_after_seq_2": len(pending["events"]),
        "final_status": final["status"],
        "events": len(adapter.events),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="run the fake-only contract walkthrough")
    args = parser.parse_args()
    if not args.self_check:
        parser.error("use --self-check; this prototype has no live integration mode")
    print(json.dumps(self_check(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
