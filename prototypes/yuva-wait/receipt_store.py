"""Fixture-only durable observation receipts for the #688 consumer contract.

This module is disconnected from the Yuva CLI, inbox, panel, provider, and
YUVA_DIR. It stores text-free bootstrap/cursor events only in marked temp roots.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping


MARKER_NAME = ".yuva-wait-receipt-fixture"
MARKER_CONTENT = b"yuva-wait-receipt-fixture-v1\n"
STORE_NAME = "receipts.jsonl"
LOCK_NAME = "receipts.lock"
MAX_STORE_BYTES = 4 * 1024 * 1024
MAX_EVENT_BYTES = 4096
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:@-]{1,128}\Z")
_BOOTSTRAP_FIELDS = frozenset({
    "schema_version", "sequence", "event_type", "consumer_id",
    "consumer_epoch", "previous_cursor", "next_cursor", "observed_at",
    "bootstrap_basis", "trust",
})
_RECEIPT_FIELDS = frozenset({
    "schema_version", "sequence", "event_type", "receipt_type",
    "consumer_id", "consumer_epoch", "message_id", "previous_cursor",
    "next_cursor", "source_class_claim", "source_class_trust",
    "source_trust", "content_class", "observed_at",
})


@dataclass(frozen=True)
class ReceiptResult:
    status: str
    cursor: str | None
    consumer_epoch: str | None = None
    receipt: Mapping[str, Any] | None = None


class _StoreCorrupt(Exception):
    pass


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER.fullmatch(value))


def _reject_fixture():
    raise ValueError("fixture store rejected") from None


def _check_regular_private(path: Path):
    try:
        info = path.lstat()
    except OSError:
        _reject_fixture()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
        _reject_fixture()
    return info


def _fixture_root(root: str | os.PathLike[str]) -> Path:
    try:
        supplied = Path(root).absolute()
        resolved = supplied.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        root_info = resolved.lstat()
        if (supplied != resolved or resolved == temp_root
                or temp_root not in resolved.parents
                or not stat.S_ISDIR(root_info.st_mode)
                or root_info.st_uid != os.geteuid()
                or stat.S_IMODE(root_info.st_mode) != 0o700):
            _reject_fixture()
        marker_fd = os.open(
            resolved / MARKER_NAME,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0))
        try:
            marker_info = os.fstat(marker_fd)
            marker_bytes = os.read(marker_fd, len(MARKER_CONTENT) + 1)
        finally:
            os.close(marker_fd)
    except (OSError, RuntimeError, TypeError, ValueError):
        _reject_fixture()
    if (not stat.S_ISREG(marker_info.st_mode)
            or marker_info.st_uid != os.geteuid()
            or marker_info.st_nlink != 1
            or stat.S_IMODE(marker_info.st_mode) != 0o600
            or marker_info.st_size != len(MARKER_CONTENT)
            or marker_bytes != MARKER_CONTENT):
        _reject_fixture()
    return resolved


def _field(message: object, key: str, default: object = None) -> object:
    if isinstance(message, Mapping):
        return message.get(key, default)
    return getattr(message, key, default)


def _message_fields(message: object) -> tuple[str, str] | None:
    message_id = _field(message, "message_id")
    source_class = _field(message, "source_class_claim", "unknown")
    if (not _safe_identifier(message_id)
            or _field(message, "source_trust") != "unverified"
            or _field(message, "content_class") != "data_only"
            or _field(message, "source_class_trust") != "unverified"
            or not isinstance(source_class, str)
            or source_class not in {"operator", "agent", "unknown"}):
        return None
    return message_id, source_class


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _timestamp_valid(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z")


def _event_is_valid(event: object, sequence: int) -> bool:
    if (type(event) is not dict or type(event.get("schema_version")) is not int
            or event["schema_version"] != 1
            or type(event.get("sequence")) is not int
            or event["sequence"] != sequence
            or not _safe_identifier(event.get("consumer_id"))
            or not _safe_identifier(event.get("consumer_epoch"))
            or not _timestamp_valid(event.get("observed_at"))):
        return False
    kind = event.get("event_type")
    if kind == "cursor_bootstrap":
        return (
            set(event) == _BOOTSTRAP_FIELDS
            and event.get("previous_cursor") is None
            and _safe_identifier(event.get("next_cursor"))
            and event.get("bootstrap_basis") == "explicit_fixture_approval"
            and event.get("trust") == "unverified"
        )
    if kind == "read_observed":
        return (
            set(event) == _RECEIPT_FIELDS
            and event.get("receipt_type") == "read_observed"
            and _safe_identifier(event.get("message_id"))
            and _safe_identifier(event.get("previous_cursor"))
            and event.get("next_cursor") == event.get("message_id")
            and isinstance(event.get("source_class_claim"), str)
            and event.get("source_class_claim") in {"operator", "agent", "unknown"}
            and event.get("source_class_trust") == "unverified"
            and event.get("source_trust") == "unverified"
            and event.get("content_class") == "data_only"
        )
    return False


def _read_events(root: Path) -> list[dict[str, Any]]:
    path = root / STORE_NAME
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0))
    except FileNotFoundError:
        return []
    except OSError:
        raise _StoreCorrupt from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_size > MAX_STORE_BYTES):
            raise _StoreCorrupt
        chunks = []
        remaining = MAX_STORE_BYTES + 1
        while remaining:
            part = os.read(fd, min(65536, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        raw = b"".join(chunks)
        if len(raw) > MAX_STORE_BYTES:
            raise _StoreCorrupt
    except OSError:
        raise _StoreCorrupt from None
    finally:
        os.close(fd)

    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise _StoreCorrupt

    events: list[dict[str, Any]] = []
    states: dict[str, dict[str, Any]] = {}
    seen_epochs: set[tuple[str, str]] = set()
    for sequence, line in enumerate(raw.splitlines(), start=1):
        if not line or len(line) + 1 > MAX_EVENT_BYTES:
            raise _StoreCorrupt
        try:
            event = json.loads(line.decode("utf-8", errors="strict"),
                               object_pairs_hook=_unique_object)
        except Exception:
            raise _StoreCorrupt from None
        if not _event_is_valid(event, sequence):
            raise _StoreCorrupt
        consumer = event["consumer_id"]
        epoch = event["consumer_epoch"]
        epoch_key = (consumer, epoch)
        state = states.get(consumer)
        if event["event_type"] == "cursor_bootstrap":
            if epoch_key in seen_epochs:
                raise _StoreCorrupt
            seen_epochs.add(epoch_key)
            states[consumer] = {
                "epoch": epoch, "cursor": event["next_cursor"], "seen": set(),
            }
        else:
            if (state is None or state["epoch"] != epoch
                    or event["previous_cursor"] != state["cursor"]
                    or event["message_id"] in state["seen"]):
                raise _StoreCorrupt
            state["seen"].add(event["message_id"])
            state["cursor"] = event["next_cursor"]
        events.append(event)
    return events


@contextmanager
def _locked_root(root: Path):
    flags = (os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
             | getattr(os, "O_CLOEXEC", 0))
    lock_fd = None
    lock_acquired = False
    try:
        try:
            lock_fd = os.open(root / LOCK_NAME, flags, 0o600)
            info = os.fstat(lock_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                _reject_fixture()
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            lock_acquired = True
            current = os.stat(root / LOCK_NAME, follow_symlinks=False)
            locked = os.fstat(lock_fd)
            if ((current.st_dev, current.st_ino) != (locked.st_dev, locked.st_ino)
                    or not stat.S_ISREG(current.st_mode)
                    or current.st_uid != os.geteuid()
                    or current.st_nlink != 1
                    or stat.S_IMODE(current.st_mode) != 0o600):
                _reject_fixture()
        except OSError:
            _reject_fixture()
        yield
    finally:
        if lock_fd is not None:
            try:
                if lock_acquired:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)


class FixtureReceiptStore:
    """Append-only text-free receipt/cursor store for synthetic observations."""

    def __init__(self, fixture_root: str | os.PathLike[str]):
        self.root = _fixture_root(fixture_root)

    @staticmethod
    def _states(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        states = {}
        for event in events:
            if event["event_type"] == "cursor_bootstrap":
                states[event["consumer_id"]] = {
                    "epoch": event["consumer_epoch"],
                    "cursor": event["next_cursor"],
                }
            else:
                states[event["consumer_id"]]["cursor"] = event["next_cursor"]
        return states

    def _append_event(self, event: dict[str, Any], *, cursor: str | None,
                      epoch: str) -> ReceiptResult:
        payload = (json.dumps(event, sort_keys=True, separators=(",", ":"),
                              allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > MAX_EVENT_BYTES:
            return ReceiptResult("store_full", cursor, epoch)
        path = self.root / STORE_NAME
        try:
            before = path.lstat()
            created = False
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) != 0o600):
                return ReceiptResult("store_corrupt", cursor, epoch)
            current_size = before.st_size
        except FileNotFoundError:
            created = True
            current_size = 0
        except OSError:
            return ReceiptResult("store_unavailable", cursor, epoch)
        if current_size + len(payload) > MAX_STORE_BYTES:
            return ReceiptResult("store_full", cursor, epoch)

        flags = (os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL
                 | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        if not created:
            flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            # A file appeared after the missing check; resolve it on next call.
            return ReceiptResult("store_unavailable", cursor, epoch)
        except OSError:
            return ReceiptResult("store_unavailable", cursor, epoch)

        wrote_any = False
        status = "store_unavailable"
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size != current_size
                    or info.st_size + len(payload) > MAX_STORE_BYTES):
                status = "store_corrupt"
            else:
                view = memoryview(payload)
                while view:
                    try:
                        written = os.write(fd, view)
                    except InterruptedError:
                        continue
                    if written <= 0:
                        status = ("commit_unknown" if wrote_any
                                  else "store_unavailable")
                        break
                    wrote_any = True
                    view = view[written:]
                if not view:
                    os.fsync(fd)
                    if created:
                        dir_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY
                                         | getattr(os, "O_CLOEXEC", 0))
                        try:
                            os.fsync(dir_fd)
                        finally:
                            os.close(dir_fd)
                    status = "recorded"
        except OSError:
            status = "commit_unknown" if wrote_any else "store_unavailable"

        try:
            os.close(fd)
        except OSError:
            # close() errors are ambiguous: the descriptor may already be
            # closed, so do not retry a descriptor number that could be reused.
            status = "commit_unknown" if wrote_any else "store_unavailable"

        if status != "recorded":
            return ReceiptResult(status, cursor, epoch)
        return ReceiptResult("recorded", event.get("next_cursor"), epoch, event)

    def bootstrap_consumer(self, consumer_id: str, consumer_epoch: str,
                           initial_cursor: str, *, approved: bool) -> ReceiptResult:
        """Set an explicit fixture baseline; no implicit None/tail bootstrap."""
        if not _safe_identifier(consumer_id) or not _safe_identifier(consumer_epoch):
            return ReceiptResult("invalid_consumer", None)
        if not _safe_identifier(initial_cursor):
            return ReceiptResult("cursor_unavailable", None, consumer_epoch)
        if approved is not True:
            return ReceiptResult("bootstrap_required", None, consumer_epoch)
        with _locked_root(self.root):
            try:
                events = _read_events(self.root)
            except _StoreCorrupt:
                return ReceiptResult("store_corrupt", None, consumer_epoch)
            states = self._states(events)
            current = states.get(consumer_id)
            if current is not None:
                if (current["epoch"] == consumer_epoch
                        and current["cursor"] == initial_cursor):
                    return ReceiptResult("duplicate_bootstrap", current["cursor"],
                                         consumer_epoch)
                if current["epoch"] == consumer_epoch:
                    return ReceiptResult("cursor_conflict", current["cursor"],
                                         consumer_epoch)
            event = {
                "schema_version": 1,
                "sequence": len(events) + 1,
                "event_type": "cursor_bootstrap",
                "consumer_id": consumer_id,
                "consumer_epoch": consumer_epoch,
                "previous_cursor": None,
                "next_cursor": initial_cursor,
                "observed_at": _now(),
                "bootstrap_basis": "explicit_fixture_approval",
                "trust": "unverified",
            }
            return self._append_event(event, cursor=initial_cursor, epoch=consumer_epoch)

    def cursor(self, consumer_id: str) -> ReceiptResult:
        if not _safe_identifier(consumer_id):
            return ReceiptResult("invalid_consumer", None)
        with _locked_root(self.root):
            try:
                states = self._states(_read_events(self.root))
            except _StoreCorrupt:
                return ReceiptResult("store_corrupt", None)
            state = states.get(consumer_id)
            if state is None:
                return ReceiptResult("cursor_unavailable", None)
            return ReceiptResult("ok", state["cursor"], state["epoch"])

    def observe(self, consumer_id: str, message: object, *,
                expected_cursor: str | None, expected_epoch: str | None) -> ReceiptResult:
        """CAS a text-free read_observed receipt against store-owned cursor."""
        if not _safe_identifier(consumer_id):
            return ReceiptResult("invalid_consumer", None)
        if (not _safe_identifier(expected_cursor)
                or not _safe_identifier(expected_epoch)):
            return ReceiptResult("cursor_unavailable", None)
        fields = _message_fields(message)
        if fields is None:
            return ReceiptResult("invalid_envelope", None, expected_epoch)
        message_id, source_class = fields

        with _locked_root(self.root):
            try:
                events = _read_events(self.root)
            except _StoreCorrupt:
                return ReceiptResult("store_corrupt", None, expected_epoch)
            states = self._states(events)
            state = states.get(consumer_id)
            if state is None:
                return ReceiptResult("cursor_unavailable", None, expected_epoch)
            prior_receipt = next((event for event in events
                                  if event["event_type"] == "read_observed"
                                  and event["consumer_id"] == consumer_id
                                  and event["message_id"] == message_id), None)
            if prior_receipt is not None:
                if (state["epoch"] != expected_epoch
                        or prior_receipt["consumer_epoch"] != expected_epoch
                        or prior_receipt["previous_cursor"] != expected_cursor):
                    return ReceiptResult("store_conflict", state["cursor"],
                                         state["epoch"], prior_receipt)
                return ReceiptResult("duplicate_observation", state["cursor"],
                                     state["epoch"], prior_receipt)
            if (state["epoch"] != expected_epoch
                    or state["cursor"] != expected_cursor):
                return ReceiptResult("cursor_conflict", state["cursor"], state["epoch"])

            event = {
                "schema_version": 1,
                "sequence": len(events) + 1,
                "event_type": "read_observed",
                "receipt_type": "read_observed",
                "consumer_id": consumer_id,
                "consumer_epoch": expected_epoch,
                "message_id": message_id,
                "previous_cursor": expected_cursor,
                "next_cursor": message_id,
                "source_class_claim": source_class,
                "source_class_trust": "unverified",
                "source_trust": "unverified",
                "content_class": "data_only",
                "observed_at": _now(),
            }
            return self._append_event(event, cursor=expected_cursor,
                                      epoch=expected_epoch)
