"""Bounded nested receipt/outbox schema for the disposable task fixture.

This is an executable fixture contract only; it is not canonical Yuva support.
"""

from __future__ import annotations

import re
from typing import Any


MAX_OPERATIONS = 256
MAX_OUTBOX_EVENTS = 256
MAX_ENTRY_BYTES = 4096
MAX_ID_BYTES = 128
MAX_MESSAGE_BYTES = 2048
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class OutboxSchemaError(ValueError):
    """Nested operations/outbox data violates the fixture schema or bounds."""


def _object(value: Any, *, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OutboxSchemaError(f"{label} must be an object")
    if set(value) != keys:
        raise OutboxSchemaError(f"{label} has missing or unknown fields")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise OutboxSchemaError(f"{label} must be a bounded printable string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise OutboxSchemaError(f"{label} must be valid UTF-8") from exc
    if size > MAX_ID_BYTES or any(ord(char) < 0x20 or ord(char) == 0x7f for char in value):
        raise OutboxSchemaError(f"{label} must be a bounded printable string")
    return value


def _task_id(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise OutboxSchemaError(f"{label} must be a positive integer")
    return value


def _entry_size(value: Any, label: str) -> None:
    import json

    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise OutboxSchemaError(f"{label} must be canonical JSON data") from exc
    if len(encoded) > MAX_ENTRY_BYTES:
        raise OutboxSchemaError(f"{label} exceeds {MAX_ENTRY_BYTES} canonical bytes")


def validate_extensions(state: dict[str, Any]) -> None:
    """Validate optional operations/outbox extensions in-place without mutation.

    Unknown top-level ledger extensions remain opaque and are preserved by the
    fixture. Nested receipt and event objects are strict: unknown fields reject
    the snapshot so their meaning cannot be silently discarded or misread.
    """
    operations = state.get("operations", {})
    outbox = state.get("outbox", [])
    if not isinstance(operations, dict) or not isinstance(outbox, list):
        raise OutboxSchemaError("operations/outbox root extension shape is invalid")
    if len(operations) > MAX_OPERATIONS:
        raise OutboxSchemaError(f"operations exceeds {MAX_OPERATIONS} entries")
    if len(outbox) > MAX_OUTBOX_EVENTS:
        raise OutboxSchemaError(f"outbox exceeds {MAX_OUTBOX_EVENTS} events")

    receipt_keys = {
        "request_digest", "operation", "task_id", "status", "result",
        "transition_event_id", "notification_event_id", "notification",
    }
    operation_ids: set[str] = set()
    transition_event_ids: set[str] = set()
    for operation_id, raw_receipt in operations.items():
        operation_id = _identifier(operation_id, "operation_id")
        receipt = _object(raw_receipt, keys=receipt_keys, label="receipt")
        if not isinstance(receipt["request_digest"], str) or not _DIGEST_RE.fullmatch(receipt["request_digest"]):
            raise OutboxSchemaError("receipt request_digest must be lowercase SHA-256 hex")
        if receipt["operation"] != "task.status" or receipt["status"] != "committed":
            raise OutboxSchemaError("receipt operation/status is unsupported")
        task_id = _task_id(receipt["task_id"], "receipt task_id")
        result = _object(receipt["result"], keys={"task_id", "task_status"}, label="receipt result")
        if (_task_id(result["task_id"], "result task_id") != task_id
                or not isinstance(result["task_status"], str) or not result["task_status"]):
            raise OutboxSchemaError("receipt result does not match task/status")
        transition_event_id = _identifier(receipt["transition_event_id"], "transition_event_id")
        if transition_event_id in transition_event_ids:
            raise OutboxSchemaError("duplicate transition_event_id")
        transition_event_ids.add(transition_event_id)
        _identifier(receipt["notification_event_id"], "notification_event_id")
        if (not isinstance(receipt["notification"], str)
                or receipt["notification"] not in {"pending", "delivered", "delivery_unknown"}):
            raise OutboxSchemaError("receipt notification state is unsupported")
        _entry_size(receipt, "receipt")
        operation_ids.add(operation_id)

    event_keys = {"event_id", "operation_id", "task_id", "kind", "message", "delivery"}
    seen_event_ids: set[str] = set()
    seen_event_operations: set[str] = set()
    for raw_event in outbox:
        event = _object(raw_event, keys=event_keys, label="outbox event")
        event_id = _identifier(event["event_id"], "event_id")
        operation_id = _identifier(event["operation_id"], "outbox operation_id")
        if event_id in seen_event_ids:
            raise OutboxSchemaError("duplicate outbox event_id")
        if operation_id in seen_event_operations:
            raise OutboxSchemaError("duplicate outbox operation_id")
        if operation_id not in operation_ids:
            raise OutboxSchemaError("outbox event has no matching receipt")
        receipt = operations[operation_id]
        if (event_id != receipt["notification_event_id"]
                or type(event["task_id"]) is not int
                or event["task_id"] != receipt["task_id"]):
            raise OutboxSchemaError("outbox event does not match its receipt")
        if event["kind"] != "task.status":
            raise OutboxSchemaError("outbox event kind is unsupported")
        if not isinstance(event["message"], str):
            raise OutboxSchemaError("outbox message must be a string")
        try:
            message_bytes = len(event["message"].encode("utf-8"))
        except UnicodeError as exc:
            raise OutboxSchemaError("outbox message must be valid UTF-8") from exc
        if message_bytes > MAX_MESSAGE_BYTES:
            raise OutboxSchemaError(f"outbox message exceeds {MAX_MESSAGE_BYTES} UTF-8 bytes")
        if (not isinstance(event["delivery"], str)
                or event["delivery"] not in {"pending", "delivered", "delivery_unknown"}):
            raise OutboxSchemaError("outbox delivery state is unsupported")
        if event["delivery"] != receipt["notification"]:
            raise OutboxSchemaError("outbox delivery state does not match receipt")
        _entry_size(event, "outbox event")
        seen_event_ids.add(event_id)
        seen_event_operations.add(operation_id)

    for operation_id, receipt in operations.items():
        if receipt["notification_event_id"] not in seen_event_ids:
            raise OutboxSchemaError(f"receipt {operation_id} has no matching outbox event")
