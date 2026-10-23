"""Offline-only initializer behind the explicit host-side ``yuva auth init``.

This module is lazily imported by the CLI command only. It is not imported by
``auth.py`` or ``server.py``. It writes only a caller-supplied, fully validated
snapshot and a stable empty lock file. It does not create keys, choose
principals/scopes, enable authentication, make backups, or provide an external
anti-rollback anchor.

The root directory must already exist and pass the auth store's secure path
checks. The caller is responsible for the offline key custody and independent
review boundary described in the operator guide.
File permissions do not isolate another process with the same UID or root.
The store generation is not an external rollback anchor: restoring an older
backup can restore revoked credentials. This draft performs no backup/restore
and cannot authorize enabling the auth gate.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any

try:  # package import and the panel/server.py execution layout
    from .auth_store_v2 import (
        LOCK_NAME,
        MAX_STORE_BYTES,
        STORE_NAME,
        AuthStateError,
        _secure_root_fd,
        encode_initial_state,
    )
except ImportError:  # pragma: no cover - exercised by direct panel imports
    from auth_store_v2 import (  # type: ignore[no-redef]
        LOCK_NAME,
        MAX_STORE_BYTES,
        STORE_NAME,
        AuthStateError,
        _secure_root_fd,
        encode_initial_state,
    )


class ProvisionError(Exception):
    """Safe provisioning failure; codes never include state or secret data."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


PROVISION_LOCK_NAME = "auth-provision-v1.lock"
PROVISION_RECEIPT_NAME = "auth-provision-v1.receipt.json"
PROVISION_RECEIPT_MAX_BYTES = 16 * 1024
_OPERATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_RECEIPT_FIELDS = {
    "schema_version", "kind", "operation_id", "instance_id", "audience",
    "state_last_wall_time", "store_sha256", "status", "result_code",
}


def empty_initial_state(instance_id: str, audience: str, *,
                        now: int | None = None) -> dict[str, Any]:
    """Prepare a valid empty v2 snapshot; no key or secret is generated."""
    if now is None:
        now = int(time.time())
    state: dict[str, Any] = {
        "version": 2,
        "instance_id": instance_id,
        "audience": audience,
        "generation": 1,
        "last_wall_time": now,
        "keys": {},
        "enrollments": {},
        "nonces": {},
        "rate_limits": {},
    }
    try:
        encode_initial_state(state)
    except (TypeError, ValueError, RecursionError):
        raise ProvisionError("invalid_initial_state") from None
    return state


def _private_regular_file(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ProvisionError("unsafe_provision_file")
    return info


def _open_stable_lock(root_fd: int) -> int:
    flags = (os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        try:
            fd = os.open(LOCK_NAME, flags, 0o600, dir_fd=root_fd)
            created = True
        except FileExistsError:
            fd = os.open(
                LOCK_NAME,
                os.O_RDWR | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=root_fd,
            )
            created = False
    except OSError:
        raise ProvisionError("lock_unavailable") from None

    try:
        if created:
            os.fchmod(fd, 0o600)
            try:
                os.fsync(fd)
                os.fsync(root_fd)
            except OSError:
                raise ProvisionError("lock_durability_unknown") from None
        held = _private_regular_file(fd)
        if held.st_size != 0:
            raise ProvisionError("unsafe_provision_file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise ProvisionError("lock_busy") from None
            raise ProvisionError("lock_unavailable") from None
        current = os.stat(LOCK_NAME, dir_fd=root_fd, follow_symlinks=False)
        if ((held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
                or current.st_nlink != 1 or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o600):
            raise ProvisionError("lock_replaced")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        try:
            written = os.write(fd, view)
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _require_store_absent(root_fd: int) -> None:
    try:
        os.stat(STORE_NAME, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        raise ProvisionError("unsafe_or_existing_store") from None
    raise ProvisionError("store_already_exists")


def write_initial_state(root: str | os.PathLike[str],
                        state: object) -> Path:
    """Install one initial snapshot without replacing an existing store.

    ``root`` must be an existing owner-only directory. An existing stable lock
    is reused; the snapshot must be absent. The snapshot is validated before
    filesystem mutation, staged with mode 0600, fsynced, and linked into place
    without overwriting a concurrently-created destination. A directory fsync
    failure after installation is reported as ``commit_unknown``; inspect the
    root offline before retrying.
    """
    try:
        payload = encode_initial_state(state)
    except (TypeError, ValueError, RecursionError):
        raise ProvisionError("invalid_initial_state") from None

    try:
        root_path = Path(root)
        root_fd = _secure_root_fd(root_path)
    except (TypeError, ValueError, AuthStateError, OSError):
        raise ProvisionError("unsafe_root") from None

    lock_fd = -1
    temp_name: str | None = None
    commit_phase = "not_started"
    try:
        # Avoid even creating the lock when this root already contains state.
        # Recheck under the lock to close the concurrent-init race.
        _require_store_absent(root_fd)
        lock_fd = _open_stable_lock(root_fd)
        _require_store_absent(root_fd)

        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                 | getattr(os, "O_CLOEXEC", 0))
        for _ in range(16):
            candidate = f".auth-state-v2.{secrets.token_hex(12)}.tmp"
            try:
                temp_fd = os.open(candidate, flags, 0o600, dir_fd=root_fd)
                temp_name = candidate
                break
            except FileExistsError:
                continue
        else:
            raise ProvisionError("temporary_file_unavailable")

        try:
            os.fchmod(temp_fd, 0o600)
            _private_regular_file(temp_fd)
            _write_all(temp_fd, payload)
            os.fsync(temp_fd)
        except OSError:
            raise ProvisionError("snapshot_write_failed") from None
        finally:
            os.close(temp_fd)

        try:
            # Same-directory hard-link is atomic and fails if STORE_NAME exists.
            # Mark the syscall boundary *before* entering os.link: an async
            # BaseException after the kernel installs the link but before the
            # next Python assignment must be reported as commit_unknown.
            commit_phase = "link_attempting"
            try:
                os.link(temp_name, STORE_NAME, src_dir_fd=root_fd,
                        dst_dir_fd=root_fd, follow_symlinks=False)
            except FileExistsError:
                # Atomic no-replace semantics prove this call did not install
                # the destination; it already exists and must remain untouched.
                commit_phase = "not_started"
                raise ProvisionError("store_already_exists") from None
            except OSError:
                # The root may be on a remote filesystem where a failed reply
                # does not prove the server did not install the link. Preserve
                # the conservative phase and require offline reconciliation.
                raise ProvisionError("commit_unknown") from None
            # This assignment is the explicit successful-syscall transition.
            # If interruption lands just before it, link_attempting is unknown.
            commit_phase = "installed"
            os.unlink(temp_name, dir_fd=root_fd)
            temp_name = None
            os.fsync(root_fd)
        except ProvisionError:
            raise
        except BaseException:
            if commit_phase in {"link_attempting", "installed"}:
                raise ProvisionError("commit_unknown") from None
            raise
        return root_path / STORE_NAME
    finally:
        cleanup_error: BaseException | None = None
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=root_fd)
            except OSError:
                pass
            except BaseException as error:
                cleanup_error = error
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except BaseException as error:
                cleanup_error = cleanup_error or error
            finally:
                try:
                    os.close(lock_fd)
                except BaseException as error:
                    cleanup_error = cleanup_error or error
        try:
            os.close(root_fd)
        except BaseException as error:
            cleanup_error = cleanup_error or error
        if cleanup_error is not None:
            if commit_phase in {"link_attempting", "installed"}:
                raise ProvisionError("commit_unknown") from None
            raise cleanup_error


def _open_provision_lock(root_fd: int) -> int:
    flags = (os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(PROVISION_LOCK_NAME, flags, 0o600, dir_fd=root_fd)
    except OSError:
        raise ProvisionError("provision_lock_unavailable") from None
    try:
        info = _private_regular_file(fd)
        if info.st_size != 0:
            raise ProvisionError("provision_lock_unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise ProvisionError("provision_lock_busy") from None
            raise ProvisionError("provision_lock_unavailable") from None
        current = os.stat(PROVISION_LOCK_NAME, dir_fd=root_fd,
                          follow_symlinks=False)
        if ((info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
                or current.st_nlink != 1 or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o600):
            raise ProvisionError("provision_lock_replaced")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_private_at(root_fd: int, name: str, limit: int) -> bytes | None:
    flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
             | getattr(os, "O_CLOEXEC", 0))
    try:
        fd = os.open(name, flags, dir_fd=root_fd)
    except FileNotFoundError:
        return None
    except OSError:
        raise ProvisionError("provision_file_unsafe") from None
    try:
        before = _private_regular_file(fd)
        chunks = bytearray()
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.extend(chunk)
            remaining -= len(chunk)
        if len(chunks) > limit:
            raise ProvisionError("provision_file_oversized")
        after = _private_regular_file(fd)
        if ((before.st_dev, before.st_ino, before.st_size,
             before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)):
            raise ProvisionError("provision_file_changed")
        return bytes(chunks)
    except OSError:
        raise ProvisionError("provision_file_read_failed") from None
    finally:
        os.close(fd)


def _receipt_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate receipt field")
        result[key] = value
    return result


def _decode_receipt(payload: bytes) -> dict[str, Any]:
    try:
        receipt = json.loads(payload.decode("ascii"), object_pairs_hook=_receipt_pairs,
                             parse_constant=lambda _value: (_ for _ in ()).throw(
                                 ValueError("invalid receipt constant")))
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError):
        raise ProvisionError("provision_receipt_invalid") from None
    if (not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS
            or type(receipt.get("schema_version")) is not int
            or receipt["schema_version"] != 1
            or receipt.get("kind") != "auth.empty_store.initialize"
            or not isinstance(receipt.get("operation_id"), str)
            or _OPERATION_ID_RE.fullmatch(receipt["operation_id"]) is None
            or not isinstance(receipt.get("instance_id"), str)
            or not isinstance(receipt.get("audience"), str)
            or type(receipt.get("state_last_wall_time")) is not int
            or not 0 <= receipt["state_last_wall_time"] <= 253402300799
            or not isinstance(receipt.get("store_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["store_sha256"])
            or receipt.get("status") not in {
                "prepared", "committed", "not_committed", "commit_unknown"}
            or (receipt.get("result_code") is not None
                and (not isinstance(receipt["result_code"], str)
                     or re.fullmatch(r"[a-z0-9_]{1,64}", receipt["result_code"]) is None))):
        raise ProvisionError("provision_receipt_invalid")
    if ((receipt["status"] in {"prepared", "committed"}
         and receipt["result_code"] is not None)
            or (receipt["status"] == "not_committed"
                and receipt["result_code"] is None)
            or (receipt["status"] == "commit_unknown"
                and receipt["result_code"] != "commit_unknown")):
        raise ProvisionError("provision_receipt_invalid")
    return receipt


def _write_receipt(root_fd: int, receipt: dict[str, Any]) -> None:
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"
    if len(payload) > PROVISION_RECEIPT_MAX_BYTES:
        raise ProvisionError("provision_receipt_oversized")
    temp_name = None
    temp_fd = -1
    replaced = False
    try:
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                 | getattr(os, "O_CLOEXEC", 0))
        for _ in range(16):
            candidate = f".auth-provision-v1.{secrets.token_hex(12)}.tmp"
            try:
                temp_fd = os.open(candidate, flags, 0o600, dir_fd=root_fd)
                temp_name = candidate
                break
            except FileExistsError:
                continue
        if temp_fd < 0 or temp_name is None:
            raise ProvisionError("provision_receipt_temp_unavailable")
        os.fchmod(temp_fd, 0o600)
        _private_regular_file(temp_fd)
        _write_all(temp_fd, payload)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = -1
        os.replace(temp_name, PROVISION_RECEIPT_NAME,
                   src_dir_fd=root_fd, dst_dir_fd=root_fd)
        replaced = True
        temp_name = None
        try:
            os.fsync(root_fd)
        except BaseException:
            raise ProvisionError("commit_unknown") from None
    except ProvisionError:
        raise
    except OSError:
        if replaced:
            raise ProvisionError("commit_unknown") from None
        raise ProvisionError("provision_receipt_write_failed") from None
    except BaseException:
        if replaced:
            raise ProvisionError("commit_unknown") from None
        raise
    finally:
        if temp_fd >= 0:
            try:
                os.close(temp_fd)
            except OSError:
                pass
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=root_fd)
            except OSError:
                pass


def _store_payload_digest(root_fd: int) -> str | None:
    payload = _read_private_at(root_fd, STORE_NAME, MAX_STORE_BYTES)
    return None if payload is None else hashlib.sha256(payload).hexdigest()


def provision_empty_store_with_receipt(
        root: str | os.PathLike[str], *, operation_id: str,
        instance_id: str, audience: str, now: int | None = None) -> tuple[str, dict[str, Any]]:
    """Initialize an empty store once and persist a secret-free idempotency receipt.

    This operation never creates keys or enrollment records. Replays require an
    exact receipt/store digest match. A prepared or uncertain receipt is never
    blindly retried; it returns ``commit_unknown`` for offline reconciliation.
    """
    if (not isinstance(operation_id, str)
            or _OPERATION_ID_RE.fullmatch(operation_id) is None):
        raise ProvisionError("invalid_operation_id")
    initial_time = int(time.time()) if now is None else now
    state = empty_initial_state(instance_id, audience, now=initial_time)
    state_payload = encode_initial_state(state)
    expected_digest = hashlib.sha256(state_payload).hexdigest()
    request = {
        "schema_version": 1,
        "kind": "auth.empty_store.initialize",
        "operation_id": operation_id,
        "instance_id": instance_id,
        "audience": audience,
        "state_last_wall_time": state["last_wall_time"],
        "store_sha256": expected_digest,
        "status": "prepared",
        "result_code": None,
    }
    root_path = Path(root)
    try:
        root_fd = _secure_root_fd(root_path)
    except (AuthStateError, OSError, TypeError, ValueError):
        raise ProvisionError("unsafe_root") from None
    lock_fd = -1
    try:
        # Do not add a provisioning sidecar lock to a pre-existing store that
        # was initialized by another workflow and has no matching receipt.
        prior_receipt = _read_private_at(
            root_fd, PROVISION_RECEIPT_NAME, PROVISION_RECEIPT_MAX_BYTES)
        prior_store_digest = _store_payload_digest(root_fd)
        if prior_receipt is None and prior_store_digest is not None:
            raise ProvisionError("store_already_exists")
        lock_fd = _open_provision_lock(root_fd)
        receipt_bytes = _read_private_at(
            root_fd, PROVISION_RECEIPT_NAME, PROVISION_RECEIPT_MAX_BYTES)
        receipt = _decode_receipt(receipt_bytes) if receipt_bytes is not None else None
        current_digest = _store_payload_digest(root_fd)

        if receipt is not None:
            if now is None:
                initial_time = receipt["state_last_wall_time"]
                state = empty_initial_state(instance_id, audience, now=initial_time)
                state_payload = encode_initial_state(state)
                expected_digest = hashlib.sha256(state_payload).hexdigest()
                request["state_last_wall_time"] = initial_time
                request["store_sha256"] = expected_digest
            elif initial_time != receipt["state_last_wall_time"]:
                raise ProvisionError("operation_id_conflict")
            for field in ("kind", "operation_id", "instance_id", "audience"):
                if receipt[field] != request[field]:
                    raise ProvisionError("operation_id_conflict")
            if receipt["store_sha256"] != expected_digest:
                raise ProvisionError("operation_id_conflict")
            if receipt["status"] == "committed":
                if current_digest != receipt["store_sha256"]:
                    raise ProvisionError("commit_unknown")
                return "replayed", receipt
            if receipt["status"] in {"prepared", "commit_unknown"}:
                raise ProvisionError("commit_unknown")
            if current_digest is not None:
                raise ProvisionError("commit_unknown")
            request["status"] = "prepared"
            request["result_code"] = None
            _write_receipt(root_fd, request)
        else:
            if current_digest is not None:
                raise ProvisionError("store_already_exists")
            _write_receipt(root_fd, request)

        try:
            write_initial_state(root_path, state)
        except ProvisionError as error:
            code = error.code
            current_digest = _store_payload_digest(root_fd)
            if code == "commit_unknown" or current_digest == expected_digest:
                request["status"] = "commit_unknown"
                request["result_code"] = "commit_unknown"
                try:
                    _write_receipt(root_fd, request)
                except ProvisionError:
                    pass
                raise ProvisionError("commit_unknown") from None
            request["status"] = "not_committed"
            request["result_code"] = code
            _write_receipt(root_fd, request)
            raise

        current_digest = _store_payload_digest(root_fd)
        if current_digest != expected_digest:
            request["status"] = "commit_unknown"
            request["result_code"] = "commit_unknown"
            try:
                _write_receipt(root_fd, request)
            except ProvisionError:
                pass
            raise ProvisionError("commit_unknown")
        request["status"] = "committed"
        request["result_code"] = None
        _write_receipt(root_fd, request)
        return "created", request
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        os.close(root_fd)
