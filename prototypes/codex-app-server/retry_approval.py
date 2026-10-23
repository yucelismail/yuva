#!/usr/bin/env python3
"""In-memory sketch of safe retries and approval waiting for Codex JSON-RPC.

This module records caller-observed I/O facts. It has no transport, Yuva
imports, subprocess, daemon, or approval-response implementation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any


APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "applyPatchApproval",
    "execCommandApproval",
}


class RetryConflict(ValueError):
    """An operation or request ID was reused with conflicting data."""


def _id_key(request_id: str | int) -> str:
    if not (isinstance(request_id, str) or
            isinstance(request_id, int) and not isinstance(request_id, bool)):
        raise ValueError("request ID must be a JSON-RPC string or integer")
    return json.dumps(request_id, ensure_ascii=False, separators=(",", ":"))


def _fingerprint(method: str, params: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"method": method, "params": params},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass
class Operation:
    operation_id: str
    request_id: str | int
    method: str
    fingerprint: str
    state: str = "prepared"
    attempt: int = 1
    write_outcome: str = "not_attempted"
    thread_id: str | None = None
    turn_id: str | None = None
    last_known_state: str | None = None
    error_code: int | str | None = None


@dataclass
class PendingApproval:
    request_id: str | int
    method: str
    thread_id: str | None
    turn_id: str | None
    item_id: str | None
    state: str = "pending"
    decision: Any = "unknown"
    fingerprint: str = ""
    connection: str = "connected"


class RetryApprovalLedger:
    """A local deduplication and observation ledger; never sends a frame."""

    def __init__(self) -> None:
        self.operations: dict[str, Operation] = {}
        self.request_to_operation: dict[str, str] = {}
        self.approvals: dict[str, PendingApproval] = {}

    def prepare(
        self,
        operation_id: str,
        request_id: str | int,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an operation once; identical retries reuse its original ID."""
        if not operation_id or not method or not isinstance(params, dict):
            raise ValueError("operation_id, method, and object params are required")
        key = _id_key(request_id)
        digest = _fingerprint(method, params)
        previous = self.operations.get(operation_id)
        if previous:
            if (previous.request_id != request_id or previous.method != method
                    or previous.fingerprint != digest):
                raise RetryConflict("operation_id was reused with different request data")
            return {"action": "suppress_duplicate", "operation": asdict(previous)}

        owner = self.request_to_operation.get(key)
        if owner is not None and owner != operation_id:
            raise RetryConflict("request_id is already bound to another operation")
        record = Operation(operation_id, request_id, method, digest)
        if method == "turn/start":
            thread_id = params.get("threadId")
            if isinstance(thread_id, str) and thread_id:
                record.thread_id = thread_id
        self.operations[operation_id] = record
        self.request_to_operation[key] = operation_id
        return {"action": "send_once", "operation": asdict(record)}

    def retry(
        self,
        operation_id: str,
        request_id: str | int,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Retry only when the ledger proves zero request bytes were written."""
        record = self._operation(operation_id)
        if (record.request_id != request_id or record.method != method
                or record.fingerprint != _fingerprint(method, params)):
            raise RetryConflict("retry differs from the original operation/request")
        if record.write_outcome != "known_not_sent":
            return {
                "action": "reconcile_only",
                "reason": "write may have reached app-server; do not resend",
                "operation": asdict(record),
            }
        record.attempt += 1
        record.state = "prepared"
        record.write_outcome = "not_attempted"
        return {"action": "send_once", "operation": asdict(record)}

    def record_write(
        self,
        operation_id: str,
        *,
        bytes_written: int,
        frame_bytes: int,
        flush_succeeded: bool,
    ) -> dict[str, Any]:
        """Record a future transport's outcome without performing the write."""
        record = self._operation(operation_id)
        if record.write_outcome != "not_attempted":
            raise RetryConflict("write outcome was already recorded for this attempt")
        if (type(bytes_written) is not int or type(frame_bytes) is not int
                or bytes_written < 0 or frame_bytes < 1 or bytes_written > frame_bytes):
            raise ValueError("write byte counts are invalid")
        if bytes_written == 0:
            record.write_outcome = "known_not_sent"
            record.state = "not_sent"
        elif bytes_written == frame_bytes and flush_succeeded:
            record.write_outcome = "fully_written"
            record.state = "sent"
        else:
            record.write_outcome = "partial_or_flush_unknown"
            record.state = "unknown"
        return asdict(record)

    def record_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Apply an already-observed JSON-RPC response by its request ID."""
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise ValueError("expected a JSON-RPC 2.0 response object")
        request_id = response.get("id")
        key = _id_key(request_id)
        operation_id = self.request_to_operation.get(key)
        if operation_id is None:
            return {"state": "unknown", "reason": "unmatched_response", "request_id": request_id}
        record = self.operations[operation_id]
        if "error" in response and "result" not in response:
            error = response["error"]
            if (not isinstance(error, dict)
                    or type(error.get("code")) is not int
                    or not isinstance(error.get("message"), str)):
                record.state = "unknown"
                return asdict(record)
            record.state = "rejected"
            record.last_known_state = "rejected"
            record.error_code = error["code"]
            return asdict(record)
        if "result" not in response or "error" in response:
            record.state = "unknown"
            return asdict(record)
        result = response["result"]
        turn = result.get("turn") if isinstance(result, dict) else None
        turn_id = turn.get("id") if isinstance(turn, dict) else None
        if record.method == "turn/start" and isinstance(turn_id, str) and turn_id:
            record.turn_id = turn_id
            record.state = "accepted"
            record.last_known_state = "accepted"
        else:
            record.state = "unknown"
        return asdict(record)

    def record_turn_event(
        self,
        *,
        turn_id: str,
        thread_id: str,
        event: str,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Apply an observed event only when its turn maps to one operation."""
        matches = [x for x in self.operations.values() if x.turn_id == turn_id]
        if len(matches) != 1:
            return {"state": "unknown", "reason": "unmatched_or_ambiguous_turn", "turn_id": turn_id}
        record = matches[0]
        if record.state in {"completed", "failed", "interrupted", "rejected"}:
            return {"state": record.state, "reason": "terminal_state_is_immutable", "turn_id": turn_id}
        if record.thread_id and record.thread_id != thread_id:
            return {"state": "unknown", "reason": "thread_id_conflict", "turn_id": turn_id}
        record.thread_id = thread_id
        if event == "turn/started":
            record.state = "running"
            record.last_known_state = "running"
        elif event == "turn/completed" and status == "completed":
            record.state = "completed"
            record.last_known_state = "completed"
        elif event == "turn/completed" and status in {"failed", "interrupted"}:
            record.state = status
            record.last_known_state = status
        else:
            record.state = "unknown"
        return asdict(record)

    def disconnect(self) -> list[dict[str, Any]]:
        """Mark nonterminal sent work unknown; never retry it automatically."""
        changed = []
        for record in self.operations.values():
            if record.state in {"sent", "accepted", "running"}:
                record.last_known_state = record.state
                record.state = "unknown"
                changed.append(asdict(record))
        for approval in self.approvals.values():
            if approval.state == "pending":
                approval.connection = "disconnected"
        return changed

    def observe_approval_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Remember an observed approval request; never reply to it."""
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            raise ValueError("expected a JSON-RPC 2.0 request")
        method = request.get("method")
        if method not in APPROVAL_METHODS:
            raise ValueError("method is not a schema-listed approval request")
        request_id = request.get("id")
        key = _id_key(request_id)
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}
        fields = (
            request_id, method, params.get("threadId"),
            params.get("turnId"), params.get("itemId"),
        )
        existing = self.approvals.get(key)
        if existing:
            if (fields != (existing.request_id, existing.method, existing.thread_id,
                           existing.turn_id, existing.item_id)
                    or _fingerprint(method, params) != existing.fingerprint):
                raise RetryConflict("approval request ID was reused with conflicting context")
            return {"action": "keep_pending_duplicate", "approval": asdict(existing)}
        approval = PendingApproval(
            request_id=request_id,
            method=method,
            thread_id=params.get("threadId") if isinstance(params.get("threadId"), str) else None,
            turn_id=params.get("turnId") if isinstance(params.get("turnId"), str) else None,
            item_id=params.get("itemId") if isinstance(params.get("itemId"), str) else None,
            fingerprint=_fingerprint(method, params),
        )
        self.approvals[key] = approval
        return {"action": "approval_pending", "approval": asdict(approval)}

    def observe_approval_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """Record a captured client response; this method does not send it."""
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise ValueError("expected a JSON-RPC 2.0 response")
        key = _id_key(response.get("id"))
        approval = self.approvals.get(key)
        if approval is None:
            return {"state": "unknown", "reason": "unmatched_approval_response"}
        if ("result" in response) == ("error" in response):
            return {"state": "unknown", "reason": "malformed_approval_response"}
        if "error" in response:
            approval.state = "response_error"
            approval.decision = "unknown"
            return asdict(approval)
        result = response.get("result")
        decision = result.get("decision") if isinstance(result, dict) else None
        approval.decision = decision if isinstance(decision, (str, dict)) else "unknown"
        approval.state = "response_observed"
        return asdict(approval)

    def observe_request_resolved(self, request_id: str | int) -> dict[str, Any]:
        """A resolved notification carries no decision, so preserve unknown."""
        approval = self.approvals.get(_id_key(request_id))
        if approval is None:
            return {"state": "unknown", "reason": "unmatched_request_resolution"}
        if approval.decision == "unknown":
            approval.state = "resolved_unknown"
        else:
            approval.state = "resolved"
        return asdict(approval)

    def pending_approvals(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.approvals.values() if x.state == "pending"]

    def _operation(self, operation_id: str) -> Operation:
        try:
            return self.operations[operation_id]
        except KeyError as exc:
            raise KeyError(f"unknown operation_id: {operation_id}") from exc
