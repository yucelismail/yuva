"""Provider-neutral, read-only shared-inbox wait algorithm sketch.

No Yuva CLI, filesystem, panel, provider, or service is imported or contacted.
The caller supplies a detached snapshot reader and owns any durable cursor.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time
from typing import Callable, Iterable, Mapping, Sequence


MAX_TIMEOUT_SECONDS = 300.0
MAX_POLL_INTERVAL_SECONDS = 2.0
MAX_MESSAGE_ID_LENGTH = 128
MAX_TEXT_LENGTH = 64 * 1024
SUPPORTED_MESSAGE_SCHEMA_VERSIONS = frozenset({1, 2})
ALL_RECIPIENTS = frozenset({"@hepsi", "@all", "@*"})


@dataclass(frozen=True)
class UntrustedEnvelope:
    """Small data-only projection; claims in the source envelope stay claims."""

    message_id: str
    recipient_claim: str
    sender_claim: str
    timestamp_claim: str
    text: str
    source_claim: str
    source_class_claim: str = "unknown"
    source_class_trust: str = "unverified"
    source_trust: str = "unverified"
    content_class: str = "data_only"


@dataclass(frozen=True)
class WaitResult:
    """Observation only; no ack, provider receipt, or task transition exists."""

    status: str
    message: UntrustedEnvelope | None = None
    next_cursor: str | None = None
    reason: str = ""


class _SnapshotError(ValueError):
    pass


def _validate_options(recipient_values: Iterable[str], after_id: str,
                      timeout: float, poll_interval: float) -> frozenset[str]:
    targets = frozenset(recipient_values)
    if (not targets or any(not isinstance(target, str) or not target.startswith("@")
                           or target.strip() != target or target.lower() in ALL_RECIPIENTS
                           for target in targets)):
        raise ValueError("recipient_values must be exact direct @recipient values")
    if (not isinstance(after_id, str) or not after_id
            or len(after_id) > MAX_MESSAGE_ID_LENGTH):
        raise ValueError("after_id must be an exact non-empty message ID")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout < 0
            or timeout > MAX_TIMEOUT_SECONDS):
        raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT_SECONDS:g} seconds")
    if (isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float))
            or not math.isfinite(poll_interval) or poll_interval <= 0
            or poll_interval > MAX_POLL_INTERVAL_SECONDS):
        raise ValueError(f"poll_interval must be in (0, {MAX_POLL_INTERVAL_SECONDS:g}] seconds")
    return targets


def _project(record: object) -> UntrustedEnvelope:
    if not isinstance(record, Mapping):
        raise _SnapshotError("record_not_object")
    message_id = record.get("id")
    recipient = record.get("kime")
    text = record.get("metin")
    if (not isinstance(message_id, str) or not message_id
            or len(message_id) > MAX_MESSAGE_ID_LENGTH):
        raise _SnapshotError("message_id_invalid")
    if not isinstance(recipient, str) or not recipient.startswith("@"):
        raise _SnapshotError("recipient_invalid")
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT_LENGTH:
        raise _SnapshotError("text_invalid_or_oversized")
    version = record.get("schema_version", 1)
    if type(version) is not int or version not in SUPPORTED_MESSAGE_SCHEMA_VERSIONS:
        raise _SnapshotError("unsupported_message_schema")

    # Sender, source, trust, provenance, and identity_claim are never used to
    # authorize the message or elevate its body. Their string values are claims.
    sender = record.get("kimden", "unknown")
    timestamp = record.get("ts", "")
    source = record.get("source", "unknown")
    source_class = record.get("source_class", "unknown")
    if not isinstance(source_class, str) or source_class not in {"operator", "agent", "unknown"}:
        source_class = "unknown"
    return UntrustedEnvelope(
        message_id=message_id,
        recipient_claim=recipient,
        sender_claim=sender if isinstance(sender, str) else "unknown",
        timestamp_claim=timestamp if isinstance(timestamp, str) else "",
        text=text,
        source_claim=source if isinstance(source, str) else "unknown",
        source_class_claim=source_class,
    )


def dispatch_authorized(message: UntrustedEnvelope, *, control_plane_approved: bool = False) -> bool:
    """A message label never authorizes dispatch; only separate control evidence can."""
    return isinstance(message, UntrustedEnvelope) and control_plane_approved is True


def _next_message(records: Sequence[object], recipient_values: frozenset[str],
                  after_id: str) -> WaitResult | None:
    projected: list[UntrustedEnvelope] = []
    seen_ids: set[str] = set()
    for raw in records:
        message = _project(raw)
        if message.message_id in seen_ids:
            return WaitResult("source_invalid", reason="duplicate_message_id")
        seen_ids.add(message.message_id)
        projected.append(message)

    cursor_positions = [index for index, message in enumerate(projected)
                        if message.message_id == after_id]
    if len(cursor_positions) != 1:
        return WaitResult("cursor_unavailable", reason="cursor_not_unique_in_snapshot")
    for message in projected[cursor_positions[0] + 1:]:
        if (message.recipient_claim in recipient_values
                and message.recipient_claim.lower() not in ALL_RECIPIENTS):
            return WaitResult("message", message=message, next_cursor=message.message_id)
    return None


def wait_for_message(
    read_snapshot: Callable[[], Sequence[object]],
    *,
    recipient_values: Iterable[str],
    after_id: str,
    timeout: float = 30.0,
    poll_interval: float = 0.25,
    cancel_event: threading.Event | None = None,
) -> WaitResult:
    """Poll detached snapshots until a direct message, timeout, or cancel.

    The snapshot must be in append order and include the unique cursor row. A
    missing/ambiguous cursor or malformed row fails closed rather than guessing.
    The caller should durably save `next_cursor` after observing the result;
    failing to do so can replay the same message (at-least-once observation).
    """
    targets = _validate_options(recipient_values, after_id, timeout, poll_interval)
    deadline = time.monotonic() + float(timeout)
    while True:
        if cancel_event is not None and cancel_event.is_set():
            return WaitResult("cancelled", reason="cancel_requested")
        try:
            records = read_snapshot()
            if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
                return WaitResult("source_invalid", reason="snapshot_not_sequence")
            result = _next_message(records, targets, after_id)
        except _SnapshotError as error:
            return WaitResult("source_invalid", reason=str(error))
        except Exception as error:
            return WaitResult("source_error", reason=type(error).__name__)
        if result is not None:
            return result

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return WaitResult("timeout", reason="no_new_direct_message")
        pause = min(float(poll_interval), remaining)
        if cancel_event is None:
            time.sleep(pause)
        elif cancel_event.wait(pause):
            return WaitResult("cancelled", reason="cancel_requested")
