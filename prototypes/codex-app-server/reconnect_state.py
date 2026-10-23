#!/usr/bin/env python3
"""In-memory sketch of reconnect and restart ambiguity for JSON-RPC IDs.

No socket, process, Yuva state, turn creation, or approval response is used.
Callers provide observed connection IDs and protocol facts explicitly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any


class ReconnectConflict(ValueError):
    """Conflicting reuse of a local operation or connection-scoped ID."""


def _id_key(value: str | int) -> str:
    if not (isinstance(value, str) or
            isinstance(value, int) and not isinstance(value, bool)):
        raise ValueError("JSON-RPC ID must be a string or integer")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _fingerprint(method: str, params: dict[str, Any]) -> str:
    body = json.dumps(
        {"method": method, "params": params},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


@dataclass
class RequestRecord:
    connection_id: str
    request_id: str | int
    operation_id: str
    method: str
    fingerprint: str
    state: str = "sent"
    last_known_state: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    error_code: int | str | None = None


@dataclass
class ApprovalRecord:
    connection_id: str
    request_id: str | int
    method: str
    fingerprint: str
    thread_id: str | None = None
    turn_id: str | None = None
    item_id: str | None = None
    state: str = "pending"
    decision: Any = "unknown"
    collision_with: str | None = None


class ReconnectLedger:
    """Keep old connection outcomes separate from IDs observed after reconnect."""

    SNAPSHOT_VERSION = 1

    def __init__(self) -> None:
        self.connections: dict[str, str] = {}
        self.active_connection: str | None = None
        self.requests: dict[tuple[str, str], RequestRecord] = {}
        self.approvals: dict[tuple[str, str], ApprovalRecord] = {}

    def start_connection(self, connection_id: str) -> dict[str, Any]:
        """Start a logical generation; this performs no connection or I/O."""
        if not connection_id:
            raise ValueError("connection_id is required")
        if self.active_connection and self.connections.get(self.active_connection) == "connected":
            raise ReconnectConflict("disconnect the current connection generation first")
        if connection_id in self.connections:
            raise ReconnectConflict("connection_id must identify a new generation")
        self.connections[connection_id] = "connected"
        self.active_connection = connection_id
        return {"state": "connected", "connection_id": connection_id}

    def disconnect(self, connection_id: str) -> dict[str, Any]:
        if self.connections.get(connection_id) != "connected":
            return {"state": "unknown", "reason": "connection_not_active", "connection_id": connection_id}
        self.connections[connection_id] = "disconnected"
        if self.active_connection == connection_id:
            self.active_connection = None

        changed = []
        for record in self.requests.values():
            if record.connection_id == connection_id and record.state in {"sent", "accepted", "running"}:
                record.last_known_state = record.state
                record.state = "unknown"
                changed.append(asdict(record))
        pending = []
        for approval in self.approvals.values():
            if approval.connection_id == connection_id and approval.state == "pending":
                approval.state = "pending_unknown"
                pending.append(asdict(approval))
        return {
            "state": "disconnected",
            "connection_id": connection_id,
            "unknown_requests": changed,
            "pending_approvals": pending,
        }

    def register_outbound(
        self,
        connection_id: str,
        request_id: str | int,
        operation_id: str,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Record an already-written request; never writes a JSON-RPC frame."""
        if self.connections.get(connection_id) != "connected":
            raise ReconnectConflict("outbound request requires the active connection generation")
        if connection_id != self.active_connection:
            raise ReconnectConflict("outbound request belongs to a stale connection generation")
        if not operation_id or not method or not isinstance(params, dict):
            raise ValueError("operation_id, method, and object params are required")
        key_id = _id_key(request_id)
        digest = _fingerprint(method, params)

        prior_operation = next((r for r in self.requests.values()
                                if r.operation_id == operation_id), None)
        if prior_operation:
            if (prior_operation.request_id != request_id
                    or prior_operation.method != method
                    or prior_operation.fingerprint != digest):
                raise ReconnectConflict("operation_id was reused with different request data")
            return {
                "action": "reconcile_only",
                "reason": "operation already exists; do not create another turn",
                "operation": asdict(prior_operation),
            }

        previous_ids = [r for r in self.requests.values()
                        if _id_key(r.request_id) == key_id]
        unresolved = [r for r in previous_ids
                      if r.state in {"sent", "accepted", "running", "unknown"}]
        if unresolved:
            return {
                "action": "reconcile_only",
                "state": "unknown",
                "reason": "request_id reappeared after reconnect; JSON-RPC ID is not a remote idempotency key",
                "previous": [asdict(r) for r in unresolved],
            }

        key = (connection_id, key_id)
        if key in self.requests:
            raise ReconnectConflict("request ID already exists in this connection generation")
        record = RequestRecord(
            connection_id=connection_id,
            request_id=request_id,
            operation_id=operation_id,
            method=method,
            fingerprint=digest,
            thread_id=params.get("threadId") if isinstance(params.get("threadId"), str) else None,
        )
        self.requests[key] = record
        return {"action": "recorded_observed_request", "request": asdict(record)}

    def observe_response(
        self,
        connection_id: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Correlate only within the exact connection generation."""
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise ValueError("expected a JSON-RPC 2.0 response")
        request_id = response.get("id")
        key = (connection_id, _id_key(request_id))
        record = self.requests.get(key)
        if record is None:
            return {
                "state": "unknown",
                "reason": "unmatched_in_this_connection_generation",
                "connection_id": connection_id,
                "request_id": request_id,
            }
        if "error" in response and "result" not in response:
            error = response.get("error")
            if isinstance(error, dict) and type(error.get("code")) is int:
                record.state = "rejected"
                record.last_known_state = "rejected"
                record.error_code = error["code"]
            else:
                record.state = "unknown"
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

    def observe_approval(
        self,
        connection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep approval requests pending; collisions across generations stay unknown."""
        if self.connections.get(connection_id) != "connected":
            raise ReconnectConflict("approval request is not on an active connection")
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            raise ValueError("expected a JSON-RPC 2.0 server request")
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params")
        if method not in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
            "applyPatchApproval",
            "execCommandApproval",
        } or not isinstance(params, dict):
            raise ValueError("expected a schema-listed approval request with object params")

        key_id = _id_key(request_id)
        key = (connection_id, key_id)
        digest = _fingerprint(method, params)
        existing = self.approvals.get(key)
        if existing:
            if existing.fingerprint != digest:
                raise ReconnectConflict("approval ID was reused with conflicting request data")
            return {"action": "keep_pending_duplicate", "approval": asdict(existing)}

        older = [a for a in self.approvals.values()
                 if _id_key(a.request_id) == key_id
                 and a.connection_id != connection_id
                 and a.state in {"pending", "pending_unknown"}]
        collision = older[-1] if older else None
        approval = ApprovalRecord(
            connection_id=connection_id,
            request_id=request_id,
            method=method,
            fingerprint=digest,
            thread_id=params.get("threadId") if isinstance(params.get("threadId"), str) else None,
            turn_id=params.get("turnId") if isinstance(params.get("turnId"), str) else None,
            item_id=params.get("itemId") if isinstance(params.get("itemId"), str) else None,
            state="pending_unknown" if collision else "pending",
            collision_with=collision.connection_id if collision else None,
        )
        self.approvals[key] = approval
        action = "pending_id_collision" if collision else "approval_pending"
        return {"action": action, "approval": asdict(approval)}

    def observe_approval_response(
        self,
        connection_id: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Record an already-observed response, scoped to its connection ID."""
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise ValueError("expected a JSON-RPC 2.0 response")
        key = (connection_id, _id_key(response.get("id")))
        approval = self.approvals.get(key)
        if approval is None:
            return {"state": "unknown", "reason": "unmatched_approval_response"}
        if ("result" in response) == ("error" in response):
            return {"state": "unknown", "reason": "malformed_approval_response"}
        if "error" in response:
            approval.state = "response_error_unknown"
            return asdict(approval)
        result = response.get("result")
        decision = result.get("decision") if isinstance(result, dict) else None
        approval.decision = decision if isinstance(decision, (str, dict)) else "unknown"
        approval.state = "response_observed"
        return asdict(approval)

    def observe_resolved(self, connection_id: str, request_id: str | int) -> dict[str, Any]:
        approval = self.approvals.get((connection_id, _id_key(request_id)))
        if approval is None:
            return {"state": "unknown", "reason": "unmatched_resolution"}
        approval.state = "resolved" if approval.decision != "unknown" else "resolved_unknown"
        return asdict(approval)

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-compatible snapshot; no file is written."""
        return {
            "version": self.SNAPSHOT_VERSION,
            "connections": dict(self.connections),
            "requests": [asdict(x) for x in self.requests.values()],
            "approvals": [asdict(x) for x in self.approvals.values()],
        }

    @classmethod
    def restore_unknown(cls, snapshot: dict[str, Any]) -> "ReconnectLedger":
        """Rebuild from a supplied snapshot and fail uncertain work closed."""
        if not isinstance(snapshot, dict) or snapshot.get("version") != cls.SNAPSHOT_VERSION:
            raise ValueError("unsupported snapshot version")
        ledger = cls()
        connections = snapshot.get("connections", {})
        if not isinstance(connections, dict):
            raise ValueError("snapshot connections must be an object")
        ledger.connections = {str(k): "disconnected" for k in connections}
        for raw in snapshot.get("requests", []):
            record = RequestRecord(**raw)
            if record.state in {"sent", "accepted", "running"}:
                record.last_known_state = record.state
                record.state = "unknown"
            ledger.requests[(record.connection_id, _id_key(record.request_id))] = record
        for raw in snapshot.get("approvals", []):
            approval = ApprovalRecord(**raw)
            if approval.state in {"pending", "response_observed"}:
                approval.state = "pending_unknown"
                approval.decision = "unknown"
            ledger.approvals[(approval.connection_id, _id_key(approval.request_id))] = approval
        return ledger

    def pending_approvals(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.approvals.values()
                if x.state in {"pending", "pending_unknown"}]
