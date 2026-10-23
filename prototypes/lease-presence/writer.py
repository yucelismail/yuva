"""Fixture-only atomic lease claim writer; never points at the live Yuva store."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
from typing import Iterator


FIXTURE_MARKER = ".lease-writer-fixture"
FIXTURE_MARKER_VALUE = "yuva-isolated-lease-writer-fixture/v1\n"
ATTEMPT_LOG = "lease-attempts.jsonl"


class LeaseWriterError(ValueError):
    """The requested claim is invalid or conflicts with the current task."""


class LeaseCommitUnknown(OSError):
    """The atomic replacement happened, but directory durability is unknown."""


@contextmanager
def _task_lock(root: Path) -> Iterator[None]:
    """Use the task ledger's shared `.kilit` lock for read/modify/write."""
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root / ".kilit", flags, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise LeaseWriterError("shared .kilit must be a private regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _read_ledger(path: Path) -> dict:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return {"schema_version": 1, "siradaki": 1, "gorevler": []}
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        try:
            ledger = json.load(stream)
        except (json.JSONDecodeError, UnicodeError) as error:
            raise LeaseWriterError("task ledger is malformed; no claim written") from error
    version = ledger.get("schema_version", 1) if isinstance(ledger, dict) else None
    if (not isinstance(ledger, dict) or type(version) is not int or version != 1
            or not isinstance(ledger.get("gorevler"), list)):
        raise LeaseWriterError("task ledger shape/version is unsupported")
    return ledger


def _atomic_write(path: Path, ledger: dict) -> None:
    payload = (json.dumps(ledger, ensure_ascii=False, separators=(",", ":"))
               + "\n").encode("utf-8")
    temp_fd, temp_name = tempfile.mkstemp(prefix=".gorevler.lease-", dir=path.parent)
    replaced = False
    try:
        os.fchmod(temp_fd, 0o600)
        with os.fdopen(temp_fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        replaced = True
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            raise LeaseCommitUnknown("ledger replaced; directory fsync outcome unknown") from error
    finally:
        if not replaced:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def _append_attempt(root: Path, event: dict) -> None:
    """Append rejected completion evidence outside the task snapshot."""
    path = root / ATTEMPT_LOG
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise LeaseWriterError("attempt log must be a private regular file")
        payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                   + "\n").encode("utf-8")
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("attempt log append made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def claim_task(root: str | os.PathLike[str], task_id: int, owner_claim: str,
               *, operation_id: str, claimed_at: str) -> dict:
    """Claim one pending task and return its fencing token.

    `owner_claim` is an unverified label supplied by the caller. Presence,
    display name, role, and any other external observation are intentionally
    not accepted as inputs to the ownership decision.
    """
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id <= 0:
        raise LeaseWriterError("task ID must be a canonical positive integer")
    if not isinstance(owner_claim, str) or not owner_claim.strip():
        raise LeaseWriterError("owner_claim must be a non-empty string claim")
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise LeaseWriterError("stable operation_id is required")
    if not isinstance(claimed_at, str) or not claimed_at.strip():
        raise LeaseWriterError("claimed_at must be supplied by the caller")

    store = Path(root)
    marker = store / FIXTURE_MARKER
    if (not store.is_dir() or marker.is_symlink() or not marker.is_file()
            or marker.read_text(encoding="utf-8") != FIXTURE_MARKER_VALUE):
        raise LeaseWriterError("fixture marker required; live stores are not supported")
    ledger_path = store / "gorevler.json"
    with _task_lock(store):
        ledger = _read_ledger(ledger_path)
        matches = [task for task in ledger["gorevler"]
                   if isinstance(task, dict) and task.get("id") == task_id
                   and type(task.get("id")) is int]
        if len(matches) != 1:
            raise LeaseWriterError("task ID is missing, ambiguous, or noncanonical")
        task = matches[0]
        prior = task.get("execution")
        if isinstance(prior, dict) and prior.get("claim_operation_id") == operation_id:
            if (task.get("durum") == "assigned"
                    and prior.get("lease_state") == "active"
                    and prior.get("owner_claim") == owner_claim
                    and prior.get("owner_trust") == "unverified"
                    and isinstance(prior.get("lease_id"), str)
                    and type(prior.get("lease_epoch")) is int):
                return dict(prior)
            raise LeaseWriterError("operation_id conflicts with existing claim")

        status = task.get("durum")
        if status not in {"pending", "pending_revision"}:
            raise LeaseWriterError("task is not claimable in its current state")
        if status == "pending_revision" and task.get("assignee") != owner_claim:
            raise LeaseWriterError("revision can only be claimed by its recorded assignee")
        if prior is not None:
            if not isinstance(prior, dict):
                raise LeaseWriterError("existing execution record is malformed")
            prior_epoch = prior.get("lease_epoch", 0)
            if isinstance(prior_epoch, bool) or not isinstance(prior_epoch, int) or prior_epoch < 0:
                raise LeaseWriterError("existing lease epoch is invalid")
            if prior.get("lease_state") not in {"closed", "revoked"}:
                raise LeaseWriterError("existing lease is active or requires reconciliation")
        else:
            prior_epoch = 0

        claim = {
            "lease_state": "active",
            "owner_claim": owner_claim,
            "owner_trust": "unverified",
            "lease_epoch": prior_epoch + 1,
            "lease_id": secrets.token_urlsafe(24),
            "claim_operation_id": operation_id,
            "claimed_at": claimed_at,
        }
        task["execution"] = claim
        task["assignee"] = owner_claim
        task["durum"] = "assigned"
        _atomic_write(ledger_path, ledger)
        return dict(claim)


def complete_task(root: str | os.PathLike[str], task_id: int, owner_claim: str,
                  lease_epoch: int, *, operation_id: str,
                  completed_at: str, note: str = "") -> dict:
    """Complete a task only under its current fencing epoch.

    Epoch conflicts are logged to ``lease-attempts.jsonl`` under the shared
    ledger lock; they do not rewrite the task snapshot or its history.
    """
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id <= 0:
        raise LeaseWriterError("task ID must be a canonical positive integer")
    if not isinstance(owner_claim, str) or not owner_claim.strip():
        raise LeaseWriterError("owner_claim must be a non-empty string claim")
    if isinstance(lease_epoch, bool) or not isinstance(lease_epoch, int) or lease_epoch < 1:
        raise LeaseWriterError("lease_epoch must be a positive integer")
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise LeaseWriterError("stable operation_id is required")
    if not isinstance(completed_at, str) or not completed_at.strip():
        raise LeaseWriterError("completed_at must be supplied by the caller")
    if not isinstance(note, str):
        raise LeaseWriterError("completion note must be a string")

    store = Path(root)
    marker = store / FIXTURE_MARKER
    if (not store.is_dir() or marker.is_symlink() or not marker.is_file()
            or marker.read_text(encoding="utf-8") != FIXTURE_MARKER_VALUE):
        raise LeaseWriterError("fixture marker required; live stores are not supported")
    ledger_path = store / "gorevler.json"
    with _task_lock(store):
        ledger = _read_ledger(ledger_path)
        matches = [task for task in ledger["gorevler"]
                   if isinstance(task, dict) and task.get("id") == task_id
                   and type(task.get("id")) is int]
        if len(matches) != 1:
            raise LeaseWriterError("task ID is missing, ambiguous, or noncanonical")
        task = matches[0]
        execution = task.get("execution")
        if not isinstance(execution, dict):
            raise LeaseWriterError("current execution record is missing or malformed")

        if (execution.get("completion_operation_id") == operation_id
                and execution.get("lease_epoch") == lease_epoch
                and execution.get("owner_claim") == owner_claim
                and execution.get("lease_state") == "closed"):
            return {"accepted": True, "result": "already_completed",
                    "task_id": task_id, "lease_epoch": lease_epoch}

        current_epoch = execution.get("lease_epoch")
        if isinstance(current_epoch, bool) or not isinstance(current_epoch, int):
            raise LeaseWriterError("current lease epoch is invalid")
        if lease_epoch != current_epoch:
            result = {"accepted": False, "result": "lease_epoch_mismatch",
                      "task_id": task_id, "submitted_epoch": lease_epoch,
                      "current_epoch": current_epoch}
            _append_attempt(store, {
                "attempt_id": secrets.token_urlsafe(18), "operation_id": operation_id,
                "task_id": task_id, "owner_claim": owner_claim,
                "submitted_epoch": lease_epoch, "current_epoch": current_epoch,
                "result": result["result"], "attempted_at": completed_at,
            })
            return result

        if (execution.get("lease_state") != "active"
                or execution.get("owner_claim") != owner_claim
                or task.get("durum") != "assigned"):
            result = {"accepted": False, "result": "lease_owner_or_state_mismatch",
                      "task_id": task_id, "submitted_epoch": lease_epoch,
                      "current_epoch": current_epoch}
            _append_attempt(store, {
                "attempt_id": secrets.token_urlsafe(18), "operation_id": operation_id,
                "task_id": task_id, "owner_claim": owner_claim,
                "submitted_epoch": lease_epoch, "current_epoch": current_epoch,
                "result": result["result"], "attempted_at": completed_at,
            })
            return result

        execution["lease_state"] = "closed"
        execution["completion_operation_id"] = operation_id
        execution["completed_at"] = completed_at
        task["durum"] = "pending_verification"
        history = task.setdefault("gecmis", [])
        if not isinstance(history, list):
            raise LeaseWriterError("task history is malformed")
        history.append({"ts": completed_at, "kimden": owner_claim,
                        "olay": "teslim", "actor_trust": "unverified",
                        "not": note})
        _atomic_write(ledger_path, ledger)
        return {"accepted": True, "result": "completed", "task_id": task_id,
                "lease_epoch": lease_epoch}
