"""Small, inert OpenCode HTTP/SSE adapter prototype.

No connection is made until a method is called. This module does not integrate
with Yuva and deliberately exposes no permission-response operation.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_SSE_LINE_BYTES = 64 * 1024


class AdapterError(Exception):
    """Transport or response error without URL, headers, or credential values."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: Any = field(repr=False)
    raw_body: bytes = field(repr=False)


@dataclass(frozen=True)
class SendResult:
    """Observed HTTP response or an ambiguous attempt; never implies safe retry."""

    outcome: str
    http_status: Optional[int] = None
    reason: Optional[str] = None
    response: Optional[HttpResult] = field(default=None, repr=False)


@dataclass(frozen=True)
class SseEvent:
    event: Optional[str]
    event_id: Optional[str]
    data: Any
    retry_ms: Optional[int] = None


@dataclass(frozen=True)
class SseBatch:
    events: Tuple[SseEvent, ...]
    complete: bool
    reason: str


def _loopback_url(base_url: str) -> str:
    if not isinstance(base_url, str) or len(base_url) > 2048:
        raise ValueError("base_url geçerli ve en fazla 2048 karakter olmalı")
    parsed = urllib.parse.urlsplit(base_url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("base_url http(s) loopback adresi olmalı; userinfo/query/fragment kabul edilmez")
    host = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("base_url yalnız loopback IP literal kabul eder; hostname kullanmayın") from None
    if not address.is_loopback:
        raise ValueError("base_url yalnız loopback IP literal kabul eder")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("base_url port'u geçersiz") from None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc += f":{port}"
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, netloc, path, "", ""))


def _sse_events(response, max_events: int, max_total_bytes: int):
    """Yield parsed SSE events; enforce finite event, line, and byte limits."""
    fields: Dict[str, Any] = {}
    consumed = 0
    produced = 0

    def finish():
        nonlocal fields, produced
        data_lines = fields.get("data")
        if not data_lines:
            fields = {}
            return None
        raw_data = "\n".join(data_lines)
        data: Any = raw_data
        if raw_data:
            try:
                data = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                pass
        event = SseEvent(fields.get("event"), fields.get("id"), data,
                         fields.get("retry"))
        fields = {}
        produced += 1
        return event

    while produced < max_events:
        line = response.readline(_MAX_SSE_LINE_BYTES + 1)
        if not line:
            incomplete = bool(fields)
            fields = {}
            return "eof_incomplete" if incomplete else "eof"
        consumed += len(line)
        if len(line) > _MAX_SSE_LINE_BYTES or consumed > max_total_bytes:
            raise AdapterError("SSE stream size limit exceeded")
        try:
            text = line.decode("utf-8").rstrip("\r\n")
        except UnicodeDecodeError:
            raise AdapterError("SSE stream is not valid UTF-8") from None
        if text == "":
            event = finish()
            if event is not None:
                yield event
            continue
        if text.startswith(":"):
            continue
        field, sep, value = text.partition(":")
        if not sep:
            value = ""
        elif value.startswith(" "):
            value = value[1:]
        if field == "data":
            fields.setdefault("data", []).append(value)
        elif field == "event":
            fields["event"] = value
        elif field == "id" and "\x00" not in value:
            fields["id"] = value
        elif field == "retry" and value.isascii() and value.isdecimal():
            fields["retry"] = int(value)
    return "event_limit"


async def _run_blocking(function, *args, **kwargs):
    loop = asyncio.get_running_loop()
    call = functools.partial(function, *args, **kwargs)
    return await loop.run_in_executor(None, call)


class OpenCodeAdapter:
    """Async facade for documented, version-dependent OpenCode API paths."""

    def __init__(self, base_url: str, session_id: str, *, username: Optional[str] = None,
                 password: Optional[str] = None, timeout: float = 10.0):
        self.base_url = _loopback_url(base_url)
        if (not isinstance(session_id, str) or not session_id
                or len(session_id) > 256 or any(ord(c) < 0x20 for c in session_id)):
            raise ValueError("session_id must be a non-empty, bounded string")
        if (username is None) != (password is None):
            raise ValueError("Basic Auth username and password must be provided together")
        if not 0 < timeout <= 120:
            raise ValueError("timeout must be in (0, 120]")
        self.session_id = session_id
        self._username = username
        self._password = password
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _url(self, path: str) -> str:
        return self.base_url + path

    def _request_sync(self, path: str, *, method: str = "GET", payload: Any = None,
                      accept: str = "application/json") -> HttpResult:
        headers = {"Accept": accept}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=True,
                              separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._username is not None:
            token = base64.b64encode(
                f"{self._username}:{self._password}".encode("utf-8")
            ).decode("ascii")
            headers["Authorization"] = "Basic " + token
        request = urllib.request.Request(self._url(path), data=body,
                                         headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            raise AdapterError(f"OpenCode HTTP request failed (status {exc.code})") from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
            raise AdapterError("OpenCode transport failed or timed out") from None
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise AdapterError("OpenCode response size limit exceeded")
        if not raw:
            parsed: Any = None
        else:
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
        return HttpResult(status=status, body=parsed, raw_body=raw)

    async def send_message(self, text: str) -> SendResult:
        """Submit once; ambiguous transport/response failures return unknown."""
        if not isinstance(text, str) or not text:
            raise ValueError("text must be a non-empty string")
        path = "/session/" + urllib.parse.quote(self.session_id, safe="") + "/prompt_async"
        payload = {"parts": [{"type": "text", "text": text}]}
        try:
            response = await _run_blocking(self._request_sync, path, method="POST",
                                           payload=payload)
        except AdapterError:
            # The request may have reached the provider before transport or
            # response failure. Do not retry or represent this as not-sent.
            return SendResult(outcome="unknown", reason="transport_or_response_error")
        return SendResult(outcome="response_observed", http_status=response.status,
                          response=response)

    async def status(self) -> HttpResult:
        """Read the provider's current session status snapshot."""
        return await _run_blocking(self._request_sync, "/session/status")

    async def messages(self, *, limit: int = 100) -> HttpResult:
        """Read bounded message history for this session; no replay is implied."""
        if not 1 <= limit <= 1000:
            raise ValueError("message history limit must be between 1 and 1000")
        path = "/session/" + urllib.parse.quote(self.session_id, safe="") + "/message"
        path += "?limit=" + str(limit)
        return await _run_blocking(self._request_sync, path)

    async def read_events(self, *, max_events: int = 100,
                          max_bytes: int = 1024 * 1024) -> SseBatch:
        """Read a bounded batch from /event; reconnect replay is not implied."""
        if not 1 <= max_events <= 1000 or not 1 <= max_bytes <= _MAX_RESPONSE_BYTES:
            raise ValueError("SSE limits are outside the supported range")

        def read_sync() -> SseBatch:
            headers = {"Accept": "text/event-stream"}
            if self._username is not None:
                token = base64.b64encode(
                    f"{self._username}:{self._password}".encode("utf-8")
                ).decode("ascii")
                headers["Authorization"] = "Basic " + token
            request = urllib.request.Request(self._url("/event"), headers=headers)
            events: List[SseEvent] = []
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    content_type = response.headers.get("Content-Type", "")
                    if not content_type.lower().startswith("text/event-stream"):
                        raise AdapterError("OpenCode event endpoint did not return SSE")
                    iterator = _sse_events(response, max_events, max_bytes)
                    try:
                        while True:
                            events.append(next(iterator))
                    except StopIteration as done:
                        reason = done.value or "eof"
                    except (TimeoutError, socket.timeout):
                        reason = "read_timeout"
                    # EOF closes a live SSE stream; it does not prove stream
                    # completeness, even when it lands between events.
                    return SseBatch(tuple(events), False, reason)
            except urllib.error.HTTPError as exc:
                raise AdapterError(f"OpenCode SSE request failed (status {exc.code})") from None
            except AdapterError:
                raise
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
                raise AdapterError("OpenCode SSE transport failed or timed out") from None

        return await _run_blocking(read_sync)
