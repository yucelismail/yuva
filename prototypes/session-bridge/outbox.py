"""Bounded, in-memory event outbox sketch; no transport or Yuva integration."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable


class OutboxError(ValueError):
    """Invalid event, conflicting reuse, or configured capacity exhaustion."""


class IdempotencyConflict(OutboxError):
    """An event ID was reused with a different canonical payload."""


class CapacityExceeded(OutboxError):
    """The bounded outbox is full; records are never silently evicted."""


_SEND_OUTCOMES = frozenset({
    "accepted", "delivered", "not_sent_proven", "unknown", "rejected",
})
_RECONCILE_OUTCOMES = frozenset({"delivered", "not_found", "unknown", "rejected"})
_TERMINAL_STATES = frozenset({"delivered", "rejected"})


@dataclass(frozen=True)
class SendObservation:
    """Explicit transport result. Exceptions and malformed results mean unknown."""

    outcome: str
    external_receipt: Any = None


@dataclass(frozen=True)
class Receipt:
    """Detached immutable view. `payload_json` is canonical and immutable."""

    event_id: str
    payload_digest: str
    payload_json: str
    state: str
    attempts: int
    external_receipt_json: str | None
    last_reconciliation: str | None
    last_error_type: str | None

    def payload(self) -> Any:
        """Return a fresh copy so callers cannot mutate outbox state."""
        return json.loads(self.payload_json)


@dataclass
class _Entry:
    event_id: str
    digest: str
    payload_json: str
    payload_size: int
    state: str = "pending"
    attempts: int = 0
    external_receipt_json: str | None = None
    last_reconciliation: str | None = None
    last_error_type: str | None = None


def _validate_payload(value: Any, path: str = "payload") -> None:
    """Require a stable JSON value with string object keys and finite numbers."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise OutboxError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_payload(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise OutboxError(f"{path} object keys must be strings")
            _validate_payload(item, f"{path}.{key}")
        return
    raise OutboxError(f"{path} contains unsupported value type: {type(value).__name__}")


def _bounded_json(value: Any, max_bytes: int, label: str) -> tuple[str, int]:
    """Serialize incrementally and stop before retaining an over-limit value."""
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
    chunks = []
    size = 0
    try:
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("utf-8")
            size += len(encoded)
            if size > max_bytes:
                raise CapacityExceeded(f"{label} exceeds its configured byte limit")
            chunks.append(chunk)
    except CapacityExceeded:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise OutboxError(f"{label} cannot be encoded as canonical JSON ({type(exc).__name__})") from exc
    return "".join(chunks), size


def _canonical_payload(payload: Any, max_bytes: int) -> tuple[str, int, str]:
    _validate_payload(payload)
    encoded, size = _bounded_json(payload, max_bytes, "event payload")
    return encoded, size, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class EventOutbox:
    """Local duplicate-safe outbox with strict capacity and conservative retries.

    A transport callback must return an explicit `SendObservation`. A thrown
    exception is ambiguous, never proof that no bytes were sent. The class does
    not perform network or filesystem I/O and does not persist state.
    """

    def __init__(self, *, max_items: int = 1024,
                 max_payload_bytes: int = 64 * 1024,
                 max_total_payload_bytes: int = 8 * 1024 * 1024,
                 max_external_receipt_bytes: int = 4096) -> None:
        for name, value in (("max_items", max_items),
                            ("max_payload_bytes", max_payload_bytes),
                            ("max_total_payload_bytes", max_total_payload_bytes),
                            ("max_external_receipt_bytes", max_external_receipt_bytes)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.max_items = max_items
        self.max_payload_bytes = max_payload_bytes
        self.max_total_payload_bytes = max_total_payload_bytes
        self.max_external_receipt_bytes = max_external_receipt_bytes
        self._entries: dict[str, _Entry] = {}
        self._payload_bytes = 0
        self._lock = threading.RLock()

    def enqueue(self, event_id: str, payload: Any) -> Receipt:
        """Record once by stable event ID; duplicate payload is a no-op."""
        if (not isinstance(event_id, str) or not event_id or len(event_id) > 256
                or not event_id.isascii() or any(ord(ch) < 0x21 for ch in event_id)):
            raise OutboxError("event_id must be 1..256 printable ASCII characters")
        payload_json, payload_size, digest = _canonical_payload(
            payload, self.max_payload_bytes)
        with self._lock:
            existing = self._entries.get(event_id)
            if existing is not None:
                if existing.digest != digest:
                    raise IdempotencyConflict("event_id already exists with a different payload")
                return self._snapshot(existing)
            if len(self._entries) >= self.max_items:
                raise CapacityExceeded("outbox max_items reached; no record was evicted")
            if self._payload_bytes + payload_size > self.max_total_payload_bytes:
                raise CapacityExceeded("outbox max_total_payload_bytes reached; no record was evicted")
            entry = _Entry(event_id, digest, payload_json, payload_size)
            self._entries[event_id] = entry
            self._payload_bytes += payload_size
            return self._snapshot(entry)

    def get(self, event_id: str) -> Receipt | None:
        """Return a detached receipt, or None if this process never recorded it."""
        with self._lock:
            entry = self._entries.get(event_id)
            return self._snapshot(entry) if entry is not None else None

    def dispatch(self, event_id: str,
                 send: Callable[[str, Any], SendObservation]) -> Receipt:
        """Make the initial external send only while the entry is pending."""
        return self._transmit(event_id, send, allowed_states={"pending"})

    def retry_not_sent(self, event_id: str,
                       send: Callable[[str, Any], SendObservation]) -> Receipt:
        """Retry only after explicit proof the prior attempt wrote zero bytes."""
        return self._transmit(event_id, send, allowed_states={"not_sent_proven"})

    def _transmit(self, event_id: str,
                  send: Callable[[str, Any], SendObservation],
                  *, allowed_states: set[str]) -> Receipt:
        with self._lock:
            entry = self._require(event_id)
            if entry.state not in allowed_states:
                return self._snapshot(entry)
            entry.state = "sending"
            entry.attempts += 1
            attempt_number = entry.attempts
            payload = json.loads(entry.payload_json)

        try:
            observation = send(event_id, payload)
            if (not isinstance(observation, SendObservation)
                    or observation.outcome not in _SEND_OUTCOMES):
                observation = SendObservation("unknown")
            receipt_json, receipt_error = self._receipt_json(observation.external_receipt)
            if receipt_error and observation.outcome == "delivered":
                observation = SendObservation("unknown")
        except Exception as exc:
            observation = SendObservation("unknown")
            receipt_json = None
            error_type = type(exc).__name__
        else:
            error_type = receipt_error

        with self._lock:
            current = self._require(event_id)
            # No other operation may change a sending entry, but retain this
            # guard so future concurrent implementations fail closed.
            if current.state != "sending" or current.attempts != attempt_number:
                current.state = "unknown"
                current.last_error_type = "ConcurrentStateConflict"
                return self._snapshot(current)
            current.state = observation.outcome
            current.external_receipt_json = receipt_json
            current.last_error_type = error_type
            return self._snapshot(current)

    def record_reconciliation(self, event_id: str, outcome: str,
                              external_receipt: Any = None) -> Receipt:
        """Record read-only external evidence; `not_found` never enables retry."""
        if not isinstance(outcome, str) or outcome not in _RECONCILE_OUTCOMES:
            raise OutboxError("unsupported reconciliation outcome")
        receipt_json, receipt_error = self._receipt_json(external_receipt)
        with self._lock:
            entry = self._require(event_id)
            if entry.state == "sending":
                raise OutboxError("cannot reconcile while a send call is in flight")
            if entry.state in _TERMINAL_STATES:
                return self._snapshot(entry)
            if receipt_error and outcome == "delivered":
                outcome = "unknown"
            entry.last_reconciliation = outcome
            entry.last_error_type = receipt_error
            if outcome in ("delivered", "rejected"):
                entry.state = outcome
                entry.external_receipt_json = receipt_json
            elif outcome == "not_found":
                # A read miss may be stale or race an in-flight remote request.
                entry.state = "unknown"
            else:
                entry.state = "unknown"
            return self._snapshot(entry)

    def _require(self, event_id: str) -> _Entry:
        try:
            return self._entries[event_id]
        except KeyError as exc:
            raise OutboxError("unknown event_id") from exc

    def _receipt_json(self, value: Any) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        try:
            encoded, _ = _bounded_json(
                value, self.max_external_receipt_bytes, "external receipt")
        except CapacityExceeded:
            return None, "ExternalReceiptTooLarge"
        except OutboxError:
            # An unrepresentable external receipt is not delivery proof.
            return None, "InvalidExternalReceipt"
        return encoded, None

    @staticmethod
    def _snapshot(entry: _Entry) -> Receipt:
        return Receipt(
            event_id=entry.event_id,
            payload_digest=entry.digest,
            payload_json=entry.payload_json,
            state=entry.state,
            attempts=entry.attempts,
            external_receipt_json=entry.external_receipt_json,
            last_reconciliation=entry.last_reconciliation,
            last_error_type=entry.last_error_type,
        )
