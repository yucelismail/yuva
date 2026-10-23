"""Pure event reducer and read-only OpenCode reconnect reconciliation example.

This module does not connect on import and does not write Yuva state. Callers
must explicitly pass an adapter and invoke ``reconcile_after_disconnect``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


_ACTIVITY_VALUES = {"busy", "idle"}
_EVENT_FINGERPRINT_LIMIT = 4096
_OBSERVED_MESSAGE_LIMIT = 4096
_CONFLICT_LIMIT = 128


def _fingerprint(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), default=str).encode("utf-8")
    except (TypeError, ValueError):
        encoded = repr(value).encode("utf-8", "replace")
    return hashlib.sha256(encoded).hexdigest()


def _event_session_id(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    # Status event scope is accepted only at the expected OpenCode envelope
    # path. Do not infer a session from info.id or other lookalike fields.
    properties = data.get("properties")
    if not isinstance(properties, dict):
        return None
    value = properties.get("sessionID")
    return value if isinstance(value, str) and value else None


def _status_type(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    candidates = [data]
    seen = set()
    while candidates:
        candidate = candidates.pop(0)
        if id(candidate) in seen:
            continue
        seen.add(id(candidate))
        value = candidate.get("type")
        if isinstance(value, str) and value.lower() in _ACTIVITY_VALUES:
            return value.lower()
        for key in ("properties", "status"):
            nested = candidate.get(key)
            if isinstance(nested, dict):
                candidates.append(nested)
    return None


@dataclass
class SessionObservation:
    session_id: str
    generation: int = 0
    activity: str = "unknown"
    connected: bool = False
    status_order_ambiguous: bool = False
    # SSE event IDs are opaque dedupe keys. They are never sorted as cursors.
    event_fingerprints: Dict[str, str] = field(default_factory=dict)
    observed_message_ids: Dict[str, str] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    # Sticky signal: evicted keys can be observed again, so dedupe is best effort.
    dedupe_history_evicted: bool = False

    def _record_conflict(self, reason: str) -> None:
        self.conflicts.append(reason)
        if len(self.conflicts) > _CONFLICT_LIMIT:
            del self.conflicts[0]

    def _record_bounded(self, collection: Dict[str, str], key: str,
                        value: str, limit: int) -> None:
        if key in collection:
            del collection[key]
        collection[key] = value
        if len(collection) > limit:
            del collection[next(iter(collection))]
            self.dedupe_history_evicted = True

    def stream_opened(self, generation: int) -> dict[str, Any]:
        if generation <= self.generation:
            return {"action": "ignored_stale_generation", "activity": self.activity}
        self.generation = generation
        self.connected = True
        # Reconnect does not restore the old activity. Wait for fresh evidence.
        self.activity = "unknown"
        self.status_order_ambiguous = False
        return {"action": "connected_unknown", "generation": generation,
                "activity": self.activity}

    def stream_interrupted(self, generation: int, reason: str) -> dict[str, Any]:
        if generation != self.generation:
            return {"action": "ignored_stale_generation", "activity": self.activity}
        self.connected = False
        self.activity = "unknown"
        return {"action": "reconcile_required", "generation": generation,
                "reason": reason, "activity": "unknown"}

    def ingest(self, event: Any, *, generation: int) -> dict[str, Any]:
        if generation != self.generation or not self.connected:
            return {"action": "ignored_stale_or_disconnected", "activity": self.activity}
        event_id = getattr(event, "event_id", None)
        event_name = getattr(event, "event", None) or ""
        data = getattr(event, "data", None)
        target_session = _event_session_id(data)
        if event_name in {"session.idle", "session.status"}:
            if target_session is None:
                return {"action": "unmatched_event", "activity": self.activity,
                        "reason": "missing_session_scope",
                        "dedupe_history_evicted": self.dedupe_history_evicted}
            if target_session != self.session_id:
                return {"action": "ignored_other_session", "activity": self.activity,
                        "dedupe_history_evicted": self.dedupe_history_evicted}

        fingerprint = _fingerprint({"event": event_name, "data": data})
        if isinstance(event_id, str) and event_id:
            dedupe_key = f"{generation}:{event_id}"
            previous = self.event_fingerprints.get(dedupe_key)
            if previous is not None:
                if previous == fingerprint:
                    return {"action": "duplicate_ignored", "event_id": event_id,
                            "activity": self.activity,
                            "dedupe_history_evicted": self.dedupe_history_evicted}
                self.activity = "unknown"
                self._record_conflict("event_id_payload_conflict")
                return {"action": "conflict_unknown", "event_id": event_id,
                        "activity": self.activity,
                        "dedupe_history_evicted": self.dedupe_history_evicted}
            self._record_bounded(self.event_fingerprints, dedupe_key, fingerprint,
                                 _EVENT_FINGERPRINT_LIMIT)

        if event_name == "session.idle":
            if self.status_order_ambiguous:
                self.activity = "unknown"
                return {"action": "unsequenced_status_order_unknown",
                        "activity": self.activity}
            if self.activity in _ACTIVITY_VALUES and self.activity != "idle":
                self.activity = "unknown"
                self.status_order_ambiguous = True
                return {"action": "unsequenced_status_transition_unknown",
                        "activity": self.activity}
            self.activity = "idle"
            return {"action": "status_observed", "activity": self.activity}
        if event_name == "session.status":
            status = _status_type(data)
            if status in _ACTIVITY_VALUES:
                if self.status_order_ambiguous:
                    self.activity = "unknown"
                    return {"action": "unsequenced_status_order_unknown",
                            "activity": self.activity}
                if (self.activity in _ACTIVITY_VALUES
                        and self.activity != status):
                    self.activity = "unknown"
                    self.status_order_ambiguous = True
                    return {"action": "unsequenced_status_transition_unknown",
                            "activity": self.activity}
                self.activity = status
                return {"action": "status_observed", "activity": status}
            self.activity = "unknown"
            return {"action": "status_unknown", "activity": self.activity}

        # A message event is an observation, not a Yuva delivery receipt.
        message_id = None
        if isinstance(data, dict):
            properties = data.get("properties")
            candidates = [data] + ([properties] if isinstance(properties, dict) else [])
            for candidate in candidates:
                info = candidate.get("info")
                if isinstance(info, dict):
                    candidate = info
                value = candidate.get("id", candidate.get("messageID"))
                if isinstance(value, str) and value:
                    message_id = value
                    break
        if event_name == "message.updated" and message_id:
            # A stable message ID can receive legitimate content updates. Only
            # exact event duplicates are suppressed; never infer ordering or a
            # Yuva delivery receipt from the message ID itself.
            if self.observed_message_ids.get(message_id) == fingerprint:
                return {"action": "duplicate_message_observation", "message_id": message_id,
                        "activity": self.activity,
                        "dedupe_history_evicted": self.dedupe_history_evicted}
            self._record_bounded(self.observed_message_ids, message_id, fingerprint,
                                 _OBSERVED_MESSAGE_LIMIT)
            return {"action": "message_observed", "message_id": message_id,
                    "activity": self.activity,
                    "dedupe_history_evicted": self.dedupe_history_evicted}
        return {"action": "unclassified_observation", "event": event_name,
                "activity": self.activity}


def _status_for_session(body: Any, session_id: str) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    item = body.get(session_id)
    if isinstance(item, dict):
        value = item.get("type")
        if isinstance(value, str) and value.lower() in _ACTIVITY_VALUES:
            return value.lower()
    # Some server versions may return a single status object rather than a map.
    target = body.get("sessionID", body.get("session_id"))
    if target == session_id:
        value = _status_type(body)
        if value in _ACTIVITY_VALUES:
            return value
    return None


def _message_ids(body: Any) -> Tuple[str, ...]:
    if not isinstance(body, list):
        return ()
    found = []
    for message in body:
        if not isinstance(message, dict):
            continue
        info = message.get("info")
        candidate = info if isinstance(info, dict) else message
        message_id = candidate.get("id", candidate.get("messageID"))
        if isinstance(message_id, str) and message_id and message_id not in found:
            found.append(message_id)
    return tuple(found)


@dataclass(frozen=True)
class ReconcileResult:
    session_id: str
    activity: str
    status_observed: bool
    history_observed: bool
    history_message_ids: Tuple[str, ...]
    unresolved_reason: Optional[str] = None


async def reconcile_after_disconnect(adapter: Any, *, session_id: str,
                                     history_limit: int = 100) -> ReconcileResult:
    """Read status and history after SSE loss; never resend or claim Yuva receipt.

    ``adapter`` must be an explicitly supplied OpenCodeAdapter (or compatible
    object). Both reads are attempted; an absent/malformed snapshot stays
    unknown. History confirms only that provider messages are observable.
    """
    try:
        status_result, history_result = await asyncio.gather(
            adapter.status(), adapter.messages(limit=history_limit))
    except Exception:
        # Provider transport/schema errors do not prove idle, success, or failure.
        return ReconcileResult(session_id, "unknown", False, False, (),
                               "status_or_history_request_failed")

    status_body = getattr(status_result, "body", None)
    history_body = getattr(history_result, "body", None)
    status_ok = getattr(status_result, "status", None) == 200
    history_ok = getattr(history_result, "status", None) == 200
    status_observed = status_ok and _status_for_session(status_body, session_id) is not None
    history_observed = history_ok and isinstance(history_body, list)
    activity = _status_for_session(status_body, session_id) or "unknown"
    reason = None if status_observed and history_observed else "incomplete_or_unmatched_snapshot"
    return ReconcileResult(session_id, activity, status_observed, history_observed,
                           _message_ids(history_body), reason)
