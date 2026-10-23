#!/usr/bin/env python3
"""Observe JSON-RPC messages from a Codex app-server stdio stream.

This is an isolated protocol sketch. It does not launch or connect to Codex,
send requests, answer server requests, or write Yuva state.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, TextIO


APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "applyPatchApproval",
    "execCommandApproval",
}

INTERACTION_METHODS = {
    "item/tool/requestUserInput",
    "mcpServer/elicitation/request",
}

CLIENT_REQUEST_METHODS = {
    "initialize",
    "thread/start",
    "thread/resume",
    "turn/start",
    "turn/steer",
    "turn/interrupt",
}

KNOWN_NOTIFICATIONS = {
    "thread/started",
    "thread/status/changed",
    "turn/started",
    "turn/completed",
    "item/started",
    "item/completed",
    "item/agentMessage/delta",
    "turn/diff/updated",
    "item/fileChange/patchUpdated",
    "item/fileChange/outputDelta",
    "item/commandExecution/outputDelta",
    "serverRequest/resolved",
}

TURN_STATUSES = {"completed", "failed", "interrupted", "inProgress"}
ERROR_MESSAGE_INPUT_LIMIT = 2048
ERROR_MESSAGE_OUTPUT_LIMIT = 512
_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|authorization)"
    r"(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^,;\r\n]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_URL_CREDENTIALS_RE = re.compile(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@")


def _id_key(value: Any) -> str:
    """Encode JSON-RPC IDs without conflating integer and string IDs."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _text_id(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_error_message(value: Any) -> str:
    """Bound and redact untrusted server error text before projecting it."""
    if not isinstance(value, str):
        return "[non-text error message omitted]"
    if len(value) > ERROR_MESSAGE_INPUT_LIMIT:
        return "[error message omitted: input limit exceeded]"
    safe = _URL_CREDENTIALS_RE.sub(r"\1[REDACTED]@", value)
    safe = _BEARER_RE.sub("Bearer [REDACTED]", safe)
    safe = _SECRET_VALUE_RE.sub(r"\1\2[REDACTED]", safe)
    safe = re.sub(r"/home/[^/\s]+", "/home/[REDACTED]", safe)
    safe = re.sub(r"[\x00-\x1f\x7f]", " ", safe)
    if len(safe) > ERROR_MESSAGE_OUTPUT_LIMIT:
        safe = safe[:ERROR_MESSAGE_OUTPUT_LIMIT] + "…"
    return safe


@dataclass
class TrackedRequest:
    request_id: Any
    method: str
    context: dict[str, Any] = field(default_factory=dict)


class JsonRpcAdapter:
    """Correlate a caller's requests with observed app-server responses/events."""

    def __init__(self) -> None:
        self.outstanding: dict[str, TrackedRequest] = {}
        self.pending_server_requests: dict[str, dict[str, Any]] = {}
        self.thread_context: dict[str, dict[str, Any]] = {}
        self.turn_context: dict[str, dict[str, Any]] = {}
        self.item_context: dict[str, dict[str, Any]] = {}
        self.item_links: dict[str, dict[str, str | None]] = {}
        self.resolved_server_requests: list[dict[str, Any]] = []

    def track_outbound_request(
        self,
        request_id: str | int,
        method: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Register a request before its response arrives; send nothing."""
        if not _valid_id(request_id):
            raise ValueError("request_id must be a JSON-RPC string or integer")
        if not isinstance(method, str) or not method:
            raise ValueError("method is required")
        key = _id_key(request_id)
        if key in self.outstanding:
            raise ValueError("request ID is already outstanding")
        self.outstanding[key] = TrackedRequest(request_id, method, dict(context or {}))

    def consume(self, message: Any) -> dict[str, Any]:
        """Project one decoded JSON-RPC message into a non-authoritative event."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return {"type": "protocol_error", "reason": "expected a JSON-RPC 2.0 object"}

        has_method = isinstance(message.get("method"), str)
        has_id = "id" in message
        if has_method and has_id:
            if message["method"] in CLIENT_REQUEST_METHODS:
                params = message.get("params")
                params = params if isinstance(params, dict) else {}
                context = {}
                thread_id = _text_id(params.get("threadId"))
                if thread_id:
                    context["thread_id"] = thread_id
                try:
                    self.track_outbound_request(message["id"], message["method"], context=context)
                except ValueError as exc:
                    return {"type": "protocol_error", "reason": str(exc)}
                return {
                    "type": "client_request_tracked",
                    "request_id": message["id"],
                    "method": message["method"],
                    "context": context,
                }
            return self._server_request(message)
        if has_method:
            return self._notification(message)
        if has_id:
            return self._response(message)
        return {"type": "protocol_error", "reason": "message is neither request, notification, nor response"}

    def _response(self, message: dict[str, Any]) -> dict[str, Any]:
        request_id = message["id"]
        if not _valid_id(request_id):
            return {"type": "protocol_error", "reason": "invalid response ID"}
        has_result = "result" in message
        has_error = "error" in message
        if has_result == has_error:
            return {"type": "protocol_error", "reason": "response must contain result or error"}

        tracked = self.outstanding.pop(_id_key(request_id), None)
        if tracked is None:
            return {"type": "unmatched_response", "request_id": request_id}

        result = message.get("result")
        event: dict[str, Any] = {
            "type": "rpc_response",
            "request_id": request_id,
            "method": tracked.method,
            "ok": has_result,
            "context": dict(tracked.context),
            "authority": "observed_unverified",
        }
        if has_error:
            error = message.get("error")
            event["error"] = {
                "code": (error.get("code") if isinstance(error, dict)
                         and isinstance(error.get("code"), int)
                         and not isinstance(error.get("code"), bool) else None),
                "message": _safe_error_message(
                    error.get("message") if isinstance(error, dict) else None),
            }
            return event

        if tracked.method in {"thread/start", "thread/resume"} and isinstance(result, dict):
            thread = result.get("thread")
            thread_id = _text_id(thread.get("id")) if isinstance(thread, dict) else None
            if thread_id:
                context = dict(tracked.context)
                context["thread_id"] = thread_id
                self.thread_context[thread_id] = context
                event["thread_id"] = thread_id
        elif tracked.method == "turn/start" and isinstance(result, dict):
            turn = result.get("turn")
            turn_id = _text_id(turn.get("id")) if isinstance(turn, dict) else None
            if turn_id:
                thread_id = _text_id(tracked.context.get("thread_id"))
                context = dict(self.thread_context.get(thread_id or "", tracked.context))
                context.update({"thread_id": thread_id, "turn_id": turn_id})
                self.turn_context[turn_id] = context
                event.update({"thread_id": thread_id, "turn_id": turn_id})
        return event

    def _server_request(self, message: dict[str, Any]) -> dict[str, Any]:
        request_id = message.get("id")
        if not _valid_id(request_id):
            return {"type": "protocol_error", "reason": "invalid server request ID"}
        method = message["method"]
        key = _id_key(request_id)
        if key in self.pending_server_requests:
            return {"type": "protocol_error", "reason": "server request ID is already pending"}
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        entry = {
            "request_id": request_id,
            "method": method,
            "thread_id": _text_id(params.get("threadId")),
            "turn_id": _text_id(params.get("turnId")),
            "item_id": _text_id(params.get("itemId")),
            "state": "pending",
        }
        self.pending_server_requests[key] = entry
        if method in APPROVAL_METHODS:
            event_type = "approval_pending"
        elif method in INTERACTION_METHODS:
            event_type = "interaction_pending"
        else:
            event_type = "server_request_pending"
        return {"type": event_type, "authority": "observed_unverified", **entry}

    def _notification(self, message: dict[str, Any]) -> dict[str, Any]:
        method = message["method"]
        raw_params = message.get("params")
        params = raw_params if isinstance(raw_params, dict) else {}
        event: dict[str, Any] = {
            "type": "notification",
            "method": method,
            "authority": "observed_unverified",
        }
        if method not in KNOWN_NOTIFICATIONS:
            event["known"] = False
            return event

        thread_id = _text_id(params.get("threadId"))
        if method == "thread/started":
            thread = params.get("thread")
            thread_id = _text_id(thread.get("id")) if isinstance(thread, dict) else None
        turn = params.get("turn")
        turn_id = _text_id(params.get("turnId"))
        if method in {"turn/started", "turn/completed"} and isinstance(turn, dict):
            turn_id = _text_id(turn.get("id"))
        item = params.get("item")
        item_id = _text_id(item.get("id")) if isinstance(item, dict) else None
        request_id = params.get("requestId")
        if not _valid_id(request_id):
            request_id = None

        if thread_id:
            event["thread_id"] = thread_id
        if turn_id:
            event["turn_id"] = turn_id
        if item_id:
            event["item_id"] = item_id
            self.item_links[item_id] = {"thread_id": thread_id, "turn_id": turn_id}
        if request_id is not None:
            event["request_id"] = request_id

        context = dict(self.thread_context.get(thread_id or "", {}))
        if turn_id:
            context = dict(self.turn_context.get(turn_id, context))
        if context:
            event["context"] = context

        if turn_id and context:
            self.turn_context[turn_id] = context
        if item_id and context:
            self.item_context[item_id] = context

        if method == "turn/completed":
            turn = params.get("turn")
            status = turn.get("status") if isinstance(turn, dict) else None
            event["turn_status"] = (
                status if isinstance(status, str) and status in TURN_STATUSES
                else "unknown")
        if method == "serverRequest/resolved" and request_id is not None:
            pending = self.pending_server_requests.pop(_id_key(request_id), None)
            resolved = {
                "type": "server_request_resolved_unknown",
                "request_id": request_id,
                "thread_id": thread_id,
                "decision": "unknown",
            }
            if pending:
                resolved["method"] = pending["method"]
                self.resolved_server_requests.append(resolved)
            return resolved
        return event

    def pending(self) -> list[dict[str, Any]]:
        """Return detached pending server requests; no decisions are made."""
        return [dict(item) for item in self.pending_server_requests.values()]

    def unresolved_unknown(self, reason: str) -> list[dict[str, Any]]:
        """Mark stream-unresolved requests unknown; never infer success or retry."""
        events = []
        for tracked in self.outstanding.values():
            events.append({
                "type": "rpc_request_unknown",
                "state": "unknown",
                "reason": reason,
                "request_id": tracked.request_id,
                "method": tracked.method,
                "context": dict(tracked.context),
                "authority": "observed_unverified",
            })
        for pending in self.pending_server_requests.values():
            events.append({
                "type": "server_request_unknown",
                "reason": reason,
                **{**pending, "state": "unknown"},
            })
        self.outstanding.clear()
        self.pending_server_requests.clear()
        return events


def run_jsonl(source: TextIO = sys.stdin, sink: TextIO = sys.stdout) -> None:
    """Read observed JSON-RPC JSONL and emit a JSONL event projection."""
    adapter = JsonRpcAdapter()
    line_number = 0
    while True:
        try:
            line = source.readline()
        except TimeoutError:
            end_reason = "stream_read_timeout"
            break
        except Exception:
            end_reason = "stream_read_error"
            break
        if line == "":
            end_reason = "stream_eof"
            break
        line_number += 1
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            event = {"type": "protocol_error", "line": line_number, "reason": f"invalid JSON: {exc.msg}"}
        else:
            event = adapter.consume(message)
        sink.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        sink.flush()
    for event in adapter.unresolved_unknown(end_reason):
        sink.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        sink.flush()


if __name__ == "__main__":
    run_jsonl()
