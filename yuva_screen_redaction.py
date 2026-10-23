"""Shared fail-closed redaction for newly written screen JSONL records."""

import json
import re
from datetime import datetime


MAX_SCREEN_RECORD_BYTES = 16 * 1024
REDACTED = "[REDACTED:credential]"

_BEARER = re.compile(r"(?i)\b(Bearer|Basic)(\s+)[A-Za-z0-9._~+/=-]{8,}")
_COOKIE_HEADER = re.compile(r"(?im)(\b(?:cookie|set-cookie)\s*:\s*)[^\r\n]*")
_ASSIGNED_CREDENTIAL = re.compile(
    r"(?i)(\b(?:authorization|proxy-authorization|x-api-key|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|"
    r"client[_-]?secret|password|passwd|pwd|cookie|set-cookie)\b\s*[:=]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_URL_CREDENTIAL = re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@")
_KNOWN_TOKEN = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AKIA[0-9A-Z]{16})\b"
)


class ScreenRedactionError(ValueError):
    """Content-free rejection for a screen record that cannot be made safe."""


def redact_text(value, *, max_bytes=MAX_SCREEN_RECORD_BYTES):
    """Redact high-confidence credential forms; reject malformed text."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise ScreenRedactionError("screen record rejected")
    if type(value) is not str:
        raise ScreenRedactionError("screen record rejected")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except (UnicodeError, ValueError):
        raise ScreenRedactionError("screen record rejected") from None
    if len(encoded) > max_bytes or "\x00" in value:
        raise ScreenRedactionError("screen record rejected")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise ScreenRedactionError("screen record rejected")

    try:
        value = _BEARER.sub(lambda match: match.group(1) + match.group(2) + REDACTED,
                            value)
        value = _COOKIE_HEADER.sub(lambda match: match.group(1) + REDACTED, value)
        value = _ASSIGNED_CREDENTIAL.sub(
            lambda match: match.group(1) + REDACTED, value)
        value = _URL_CREDENTIAL.sub(lambda match: match.group(1) + REDACTED + "@",
                                    value)
        value = _KNOWN_TOKEN.sub(REDACTED, value)
        value.encode("utf-8", errors="strict")
        return value
    except Exception:
        # Never include the input, regex match, or exception text in the error.
        raise ScreenRedactionError("screen record rejected") from None


def redact_screen_record(record):
    """Validate and redact a complete screen record before JSON serialization."""
    try:
        if type(record) is not dict or set(record) != {
                "ts", "kimlik", "ad", "tur", "satir"}:
            raise ScreenRedactionError("screen record rejected")
        ts = record["ts"]
        identity = record["kimlik"]
        name = record["ad"]
        kind = record["tur"]
        line = record["satir"]
        if type(ts) is not str or len(ts) > 64:
            raise ScreenRedactionError("screen record rejected")
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            raise ScreenRedactionError("screen record rejected")
        if (type(identity) is not str or not 1 <= len(identity) <= 64
                or identity.startswith(".")
                or not all(char.isalnum() or char in "-_." for char in identity)):
            raise ScreenRedactionError("screen record rejected")
        if type(kind) is not str or kind not in {"ekran", "komut", "sonuc", "baslik"}:
            raise ScreenRedactionError("screen record rejected")
        clean = dict(record)
        clean["ad"] = redact_text(name)
        clean["satir"] = redact_text(line)
        encoded = (json.dumps(clean, ensure_ascii=False) + "\n").encode(
            "utf-8", errors="strict")
        if len(encoded) > MAX_SCREEN_RECORD_BYTES:
            raise ScreenRedactionError("screen record rejected")
        return clean
    except ScreenRedactionError:
        raise
    except Exception:
        # Includes malformed fields and unexpected redactor/serializer failures.
        raise ScreenRedactionError("screen record rejected") from None
