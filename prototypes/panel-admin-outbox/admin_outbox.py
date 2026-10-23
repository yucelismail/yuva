"""Synthetic, temporary-root fixture for state + admin-audit delivery.

This deliberately does not import panel.server or use Yuva's live stores.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator


class FixtureError(RuntimeError):
    pass


class IdempotencyConflict(FixtureError):
    pass


class CommitUnknown(FixtureError):
    pass


class DeliveryUnknown(FixtureError):
    pass


class SimulatedCrash(BaseException):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise FixtureError("fixture value is not canonical JSON") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class PanelAdminOutbox:
    """Fixture contract: state+receipt+outbox commit, then exact-ID JSONL delivery."""

    def __init__(self, root: str | Path, *, faults: set[str] | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "durum.json"
        self.audit_path = self.root / "audit.jsonl"
        self.lock_path = self.root / ".kilit"
        self.faults = faults if faults is not None else set()
        self.lock_path.touch(exist_ok=True)
        if not self.state_path.exists():
            self._write_state({
                "schema_version": 1,
                "rev": 0,
                "users": {"synthetic-target": {"sorumlu_kimlik": None}},
                "operations": {},
                "outbox": [],
            })
        self.audit_path.touch(exist_ok=True)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self.lock_path.open("rb") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                if "lock_fd_close" in self.faults:
                    self.faults.remove("lock_fd_close")
                    stream.close()
                    raise OSError("injected lock descriptor close error")

    def _read_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"),
                               object_pairs_hook=_unique_object)
        except (OSError, UnicodeError, ValueError) as exc:
            raise FixtureError("synthetic state snapshot is unreadable") from exc
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or not isinstance(value.get("users"), dict)
                or not isinstance(value.get("operations"), dict)
                or not isinstance(value.get("outbox"), list)):
            raise FixtureError("synthetic state snapshot shape is invalid")
        return value

    def _write_state(self, state: dict[str, Any]) -> None:
        data = _canonical(state)
        fd, temp_name = tempfile.mkstemp(prefix=".durum.", suffix=".tmp",
                                         dir=self.root)
        replaced = False
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.state_path)
            replaced = True
            if "state_directory_fsync" in self.faults:
                self.faults.remove("state_directory_fsync")
                raise OSError("injected state directory fsync failure")
            dir_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            closed = False
            try:
                os.fsync(dir_fd)
                if "state_directory_close" in self.faults:
                    self.faults.remove("state_directory_close")
                    os.close(dir_fd)
                    closed = True
                    raise OSError("injected state directory descriptor close error")
            finally:
                if not closed:
                    os.close(dir_fd)
        except OSError as exc:
            if not replaced:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                raise FixtureError("synthetic state write failed before replace") from exc
            raise CommitUnknown("state replaced; directory durability is unknown") from exc

    @staticmethod
    def _event_id(operation_id: str) -> str:
        digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return f"admin-event-{digest}"

    def apply(self, operation_id: str, target_id: str,
              new_owner: str | None) -> dict[str, Any]:
        if (not isinstance(operation_id, str) or not operation_id
                or len(operation_id.encode("utf-8")) > 128
                or not isinstance(target_id, str) or not target_id
                or (new_owner is not None and not isinstance(new_owner, str))):
            raise FixtureError("operation ID, target and owner have invalid types")
        request = {"operation": "sorumlu.set", "target_id": target_id,
                   "new_owner": new_owner}
        request_digest = hashlib.sha256(_canonical(request)).hexdigest()
        with self._locked():
            state = self._read_state()
            previous = state["operations"].get(operation_id)
            if previous is not None:
                if previous["request_digest"] != request_digest:
                    raise IdempotencyConflict("operation ID reused with changed request")
                return dict(previous)
            user = state["users"].get(target_id)
            if not isinstance(user, dict):
                raise FixtureError("target is not in the synthetic roster")
            before = user.get("sorumlu_kimlik")
            event_id = self._event_id(operation_id)
            event = {"id": event_id, "operation_id": operation_id,
                     "operation": "sorumlu.set", "target_id": target_id,
                     "before": before, "after": new_owner}
            receipt = {
                "operation_id": operation_id,
                "request_digest": request_digest,
                "status": "committed",
                "result": {"target_id": target_id, "sorumlu_kimlik": new_owner},
                "event_id": event_id,
                "audit_delivery": "pending",
            }
            user["sorumlu_kimlik"] = new_owner
            state["rev"] = state.get("rev", 0) + 1
            state["operations"][operation_id] = receipt
            state["outbox"].append({**event, "delivery": "pending"})
            self._write_state(state)
            return dict(receipt)

    def _readback(self, expected: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        if "readback_error" in self.faults:
            self.faults.remove("readback_error")
            return None, "readback_error"
        found = None
        try:
            with self.audit_path.open("rb") as stream:
                for raw in stream:
                    if not raw.endswith(b"\n"):
                        return None, "malformed_tail"
                    try:
                        event = json.loads(raw.decode("utf-8"),
                                           object_pairs_hook=_unique_object)
                    except (UnicodeError, ValueError):
                        return None, "malformed_record"
                    if not isinstance(event, dict):
                        return None, "malformed_record"
                    if event.get("id") == expected["id"]:
                        if found is not None:
                            return None, "duplicate_event_id"
                        found = event
        except OSError:
            return None, "readback_error"
        return found, None

    def _append(self, event: dict[str, Any]) -> None:
        data = _canonical(event) + b"\n"
        if "append_before_write" in self.faults:
            self.faults.remove("append_before_write")
            raise DeliveryUnknown("injected uncertain append before write")
        try:
            with self.audit_path.open("ab") as stream:
                if "partial_append" in self.faults:
                    self.faults.remove("partial_append")
                    stream.write(data[:max(1, len(data) // 2)])
                    stream.flush()
                    os.fsync(stream.fileno())
                    raise OSError("injected partial append")
                stream.write(data)
                stream.flush()
                if "append_fsync" in self.faults:
                    self.faults.remove("append_fsync")
                    raise OSError("injected append fsync uncertainty")
                os.fsync(stream.fileno())
        except OSError as exc:
            raise DeliveryUnknown("audit append outcome is unknown") from exc

    def _set_delivery(self, state: dict[str, Any], event_id: str,
                      delivery: str) -> None:
        event = next(item for item in state["outbox"] if item["id"] == event_id)
        event["delivery"] = delivery
        state["operations"][event["operation_id"]]["audit_delivery"] = delivery

    def deliver_pending(self) -> list[dict[str, str]]:
        results = []
        with self._locked():
            state = self._read_state()
            for pending in state["outbox"]:
                status = pending["delivery"]
                if status == "delivered":
                    continue
                expected = {key: pending[key] for key in
                            ("id", "operation_id", "operation", "target_id", "before", "after")}
                found, problem = self._readback(expected)
                if problem or (found is not None and _canonical(found) != _canonical(expected)):
                    if status != "delivery_unknown":
                        self._set_delivery(state, expected["id"], "delivery_unknown")
                        self._write_state(state)
                    results.append({"event_id": expected["id"], "state": "delivery_unknown"})
                    continue
                if found is not None:
                    self._set_delivery(state, expected["id"], "delivered")
                    self._write_state(state)
                    results.append({"event_id": expected["id"], "state": "delivered_readback"})
                    continue
                if status == "delivery_unknown":
                    results.append({"event_id": expected["id"], "state": "delivery_unknown"})
                    continue
                try:
                    self._append(expected)
                except DeliveryUnknown:
                    self._set_delivery(state, expected["id"], "delivery_unknown")
                    self._write_state(state)
                    results.append({"event_id": expected["id"], "state": "delivery_unknown"})
                    continue
                if "after_append_crash" in self.faults:
                    self.faults.remove("after_append_crash")
                    raise SimulatedCrash("injected crash after append before marker")
                self._set_delivery(state, expected["id"], "delivered")
                self._write_state(state)
                results.append({"event_id": expected["id"], "state": "delivered"})
        return results

    def snapshot(self) -> dict[str, Any]:
        with self._locked():
            return self._read_state()

    def audit_events(self) -> list[dict[str, Any]]:
        found = []
        with self._locked():
            data = self.audit_path.read_bytes()
            if data and not data.endswith(b"\n"):
                raise DeliveryUnknown("synthetic audit tail is malformed")
            for line in data.splitlines():
                found.append(json.loads(line.decode("utf-8"),
                                        object_pairs_hook=_unique_object))
        return found
