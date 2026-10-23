"""Isolated durable task/outbox sketch; never connects to Yuva's live store."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from outbox_schema import OutboxSchemaError, validate_extensions


class TaskOutboxError(RuntimeError):
    pass


class IdempotencyConflict(TaskOutboxError):
    pass


class CommitUnknown(TaskOutboxError):
    """Snapshot replacement may have happened; caller must reconcile by ID."""


class LedgerCompatibilityError(TaskOutboxError):
    """Fixture ledger is malformed or uses an unsupported root schema."""


class DeliveryUnknown(TaskOutboxError):
    """Message log is malformed or append outcome cannot be safely resolved."""


class SimulatedCrash(BaseException):
    """Fixture-only abrupt stop; deliberately bypasses normal error handlers."""


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise TaskOutboxError("value is not canonical JSON") from exc


class TaskOutbox:
    """Single-lock snapshot+receipt+outbox commit and duplicate-safe JSONL delivery.

    ``root`` must be a disposable fixture directory. The implementation is an
    executable contract prototype, not a drop-in writer for Yuva's canonical
    CLI, panel, or live data.
    """

    def __init__(self, root: str | Path, *, faults: set[str] | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.root / "gorevler.json"
        self.messages_path = self.root / "mesaj.jsonl"
        self.lock_path = self.root / ".kilit"
        self.faults = faults if faults is not None else set()
        if not self.snapshot_path.exists():
            self._atomic_create({"schema_version": 1, "siradaki": 1,
                                 "gorevler": [], "operations": {}, "outbox": []})
        self.messages_path.touch(exist_ok=True)
        self.lock_path.touch(exist_ok=True)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self.lock_path.open("rb") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.snapshot_path.read_text(encoding="utf-8"),
                               object_pairs_hook=_unique_json_object)
        except (OSError, UnicodeError, ValueError) as exc:
            raise LedgerCompatibilityError("task ledger cannot be read safely") from exc
        if not isinstance(value, dict):
            raise LedgerCompatibilityError("task ledger root must be an object")
        schema_version = value.get("schema_version", 1)
        if type(schema_version) is not int or schema_version != 1:
            raise LedgerCompatibilityError("unsupported task ledger schema_version")
        value.setdefault("siradaki", 1)
        value.setdefault("gorevler", [])
        next_id = value.get("siradaki")
        tasks = value.get("gorevler")
        if type(next_id) is not int or next_id < 1 or not isinstance(tasks, list):
            raise LedgerCompatibilityError("task ledger v1 root shape is invalid")
        seen_ids = set()
        for task in tasks:
            if not isinstance(task, dict):
                raise LedgerCompatibilityError("task ledger entry must be an object")
            task_id = task.get("id")
            if type(task_id) is not int or task_id < 1 or task_id in seen_ids:
                raise LedgerCompatibilityError("task ledger IDs must be unique positive integers")
            seen_ids.add(task_id)
            if (not isinstance(task.get("baslik"), str)
                    or not isinstance(task.get("kimden"), str)
                    or not isinstance(task.get("durum"), str)
                    or not isinstance(task.get("gecmis", []), list)):
                raise LedgerCompatibilityError("task ledger v1 task shape is invalid")
        value.setdefault("schema_version", 1)
        value.setdefault("operations", {})
        value.setdefault("outbox", [])
        try:
            validate_extensions(value)
        except OutboxSchemaError as exc:
            raise LedgerCompatibilityError("operation/outbox extension is invalid") from exc
        return value

    def _replace(self, state: dict[str, Any]) -> None:
        try:
            validate_extensions(state)
        except OutboxSchemaError as exc:
            raise LedgerCompatibilityError("operation/outbox extension is invalid") from exc
        data = _canonical(state)
        fd, temp_name = tempfile.mkstemp(prefix=".gorevler.", suffix=".tmp",
                                         dir=self.root)
        replaced = False
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.snapshot_path)
            replaced = True
            if "directory_fsync" in self.faults:
                self.faults.remove("directory_fsync")
                raise OSError("injected directory fsync uncertainty")
            dir_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError as exc:
            if not replaced:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                raise TaskOutboxError("snapshot write failed before replace") from exc
            raise CommitUnknown("snapshot replaced; directory durability is unknown") from exc

    def _atomic_create(self, state: dict[str, Any]) -> None:
        # Constructor-only initialization before a competing writer exists.
        self._replace(state)

    def apply_operation(self, operation_id: str, task_id: int,
                        new_status: str, event_id: str,
                        notification: str) -> dict[str, Any]:
        request = {"task_id": task_id, "new_status": new_status,
                   "event_id": event_id, "notification": notification}
        digest = hashlib.sha256(_canonical(request)).hexdigest()
        if (not isinstance(operation_id, str) or not operation_id
                or type(task_id) is not int or task_id < 1
                or not all(isinstance(item, str) and item for item in
                           (new_status, event_id, notification))):
            raise TaskOutboxError("operation, task, status, event ID and notification are required")
        with self._locked():
            state = self._read_state()
            previous = state["operations"].get(operation_id)
            if previous is not None:
                if previous.get("request_digest") != digest:
                    raise IdempotencyConflict("operation_id reused with different request")
                return dict(previous)
            task = next((item for item in state["gorevler"]
                         if item["id"] == task_id), None)
            if task is None:
                raise TaskOutboxError("task ID is not present in the v1 ledger")
            transition_event_id = f"task:{operation_id}"
            task["durum"] = new_status
            task.setdefault("gecmis", []).append({
                "ts": "fixture:committed", "kimden": "fixture",
                "olay": f"durum:{new_status}", "actor_trust": "local_unverified",
                "not": "", "event_id": transition_event_id,
                "operation_id": operation_id,
            })
            record = {"request_digest": digest, "operation": "task.status",
                      "task_id": task_id, "status": "committed",
                      "result": {"task_id": task_id, "task_status": new_status},
                      "transition_event_id": transition_event_id,
                      "notification_event_id": event_id, "notification": "pending"}
            outbox_event = {"event_id": event_id, "operation_id": operation_id,
                            "task_id": task_id, "kind": "task.status",
                            "message": notification, "delivery": "pending"}
            state["operations"][operation_id] = record
            state["outbox"].append(outbox_event)
            self._replace(state)
            return dict(record)

    def lookup(self, operation_id: str) -> dict[str, Any] | None:
        with self._locked():
            record = self._read_state()["operations"].get(operation_id)
            return dict(record) if record is not None else None

    def deliver_pending(self) -> list[dict[str, str]]:
        results = []
        with self._locked():
            state = self._read_state()
            for event in state["outbox"]:
                delivery_state = event.get("delivery")
                if delivery_state not in {"pending", "delivery_unknown"}:
                    continue
                event_id = event["event_id"]
                matching, malformed = self._find_event(event_id)
                if malformed:
                    if delivery_state != "delivery_unknown":
                        self._set_delivery(state, event, "delivery_unknown")
                        self._replace(state)
                    results.append({"event_id": event_id, "state": "delivery_unknown"})
                    continue
                expected = self._message_record(event)
                if matching is not None:
                    if _canonical(matching) != _canonical(expected):
                        if delivery_state != "delivery_unknown":
                            self._set_delivery(state, event, "delivery_unknown")
                            self._replace(state)
                        results.append({"event_id": event_id, "state": "delivery_unknown"})
                        continue
                    self._set_delivery(state, event, "delivered")
                    self._replace(state)
                    results.append({"event_id": event_id, "state": "delivered_readback"})
                    continue
                if delivery_state == "delivery_unknown":
                    # Absence from a read is not proof that a prior append had
                    # no effect. Reconcile only; never turn unknown into retry.
                    results.append({"event_id": event_id, "state": "delivery_unknown"})
                    continue
                try:
                    self._append_event(expected)
                except DeliveryUnknown:
                    self._set_delivery(state, event, "delivery_unknown")
                    self._replace(state)
                    results.append({"event_id": event_id, "state": "delivery_unknown"})
                    continue
                if "after_append" in self.faults:
                    self.faults.remove("after_append")
                    raise SimulatedCrash("crash after message fsync before delivered marker")
                self._set_delivery(state, event, "delivered")
                self._replace(state)
                results.append({"event_id": event_id, "state": "delivered"})
        return results

    @staticmethod
    def _set_delivery(state: dict[str, Any], event: dict[str, Any], delivery: str) -> None:
        event["delivery"] = delivery
        receipt = state["operations"].get(event.get("operation_id"))
        if receipt is not None:
            receipt["notification"] = delivery

    def _message_record(self, event: dict[str, Any]) -> dict[str, Any]:
        return {"id": event["event_id"], "operation_id": event["operation_id"],
                "task_id": event["task_id"], "tur": event["kind"],
                "metin": event["message"]}

    def _find_event(self, event_id: str) -> tuple[dict[str, Any] | None, bool]:
        found = None
        if "readback_error" in self.faults:
            self.faults.remove("readback_error")
            return None, True
        try:
            with self.messages_path.open("rb") as stream:
                for raw_line in stream:
                    if not raw_line.endswith(b"\n"):
                        return None, True
                    try:
                        record = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        return None, True
                    if not isinstance(record, dict):
                        return None, True
                    if record.get("id") == event_id:
                        if found is not None:
                            return None, True
                        found = record
        except OSError:
            return None, True
        return found, False

    def _append_event(self, record: dict[str, Any]) -> None:
        data = _canonical(record) + b"\n"
        if "append_before_write" in self.faults:
            self.faults.remove("append_before_write")
            raise DeliveryUnknown("injected uncertain append before fixture write")
        try:
            with self.messages_path.open("ab") as stream:
                stream.write(data)
                stream.flush()
                if "append_fsync" in self.faults:
                    self.faults.remove("append_fsync")
                    raise OSError("injected append fsync uncertainty")
                os.fsync(stream.fileno())
        except OSError as exc:
            # A partial write may exist. Future calls scan the complete log and
            # refuse an unsafe retry if its tail is malformed.
            raise DeliveryUnknown("message append outcome is unknown") from exc

    def snapshot(self) -> dict[str, Any]:
        with self._locked():
            return self._read_state()

    def message_records(self) -> list[dict[str, Any]]:
        records = []
        with self._locked():
            try:
                for line in self.messages_path.read_bytes().splitlines(keepends=True):
                    if not line.endswith(b"\n"):
                        raise DeliveryUnknown("message tail is incomplete")
                    value = json.loads(line.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise DeliveryUnknown("message line is not an object")
                    records.append(value)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise DeliveryUnknown("message log is malformed") from exc
        return records
