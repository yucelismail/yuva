"""Fail-closed, feature-off v2 auth state store for Yuva.

This module is intentionally not imported by ``auth.py`` or ``server.py``. It
does not create a root, state file, lock, key, or bootstrap record. An operator
must provision a complete v2 snapshot and its stable lock file before callers
can use :class:`AuthStateStore`.

The store keeps keys, enrollment-token lifecycle, nonce replay records,
rate-limit buckets, a generation, and a persisted wall-clock high-water in one
strict JSON snapshot. All reads and mutations use one persistent flock inode.
The generation detects in-store inconsistencies; it is not an external
anti-rollback anchor. Restoring a backup requires an offline, operator-managed
epoch/re-provisioning procedure unless a separate trusted generation marker is
provided by a future integration.

The same-UID/root process is inside this local trust boundary. File modes and
directory checks are not isolation from another process with the same UID.
"""

from __future__ import annotations

import base64
import binascii
import errno
import fcntl
import json
import math
import os
import re
import secrets
import stat
import time
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any


VERSION = 2
MAX_STORE_BYTES = 1024 * 1024
MAX_KEYS = 4096
MAX_ENROLLMENTS = 100_000
MAX_NONCES = 100_000
MAX_RATE_LIMITS = 10_000
MAX_SCOPES = 256
MAX_ID_BYTES = 128
STORE_NAME = "auth-state-v2.json"
LOCK_NAME = "auth-state-v2.lock"

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_HEX64_RE = re.compile(r"[0-9a-f]{64}\Z")
_B64URL_RE = re.compile(r"[A-Za-z0-9_-]+\Z")
_METHOD_RE = re.compile(r"[A-Z]{1,16}\Z")
_PATH_RE = re.compile(r"/(?:[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*)?\Z")
_KEY_FIELDS = {
    "principal_id", "audience", "scopes", "secret_b64", "not_before",
    "expires_at", "revoked", "enrollment_digest",
}
_ENROLLMENT_FIELDS = {
    "principal_id", "audience", "scopes", "issuer_key_id", "issued_at",
    "expires_at", "status", "consumed_at", "operation_id",
    "client_key_fingerprint", "key_id",
}
_RATE_LIMIT_FIELDS = {"window_start", "count"}


class AuthStateError(Exception):
    """Safe store failure. ``code`` contains no credential or path material."""

    status = 503

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CommitUnknown(AuthStateError):
    """Atomic replace completed, but directory durability was not confirmed."""

    def __init__(self):
        super().__init__("commit_unknown")


def _raise(code: str) -> None:
    raise AuthStateError(code)


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _is_id(value: object) -> bool:
    return (isinstance(value, str) and len(value.encode("utf-8")) <= MAX_ID_BYTES
            and _ID_RE.fullmatch(value) is not None)


def _is_timestamp(value: object) -> bool:
    return type(value) is int and 0 <= value <= 253402300799


def _decode_secret(value: object) -> bytes:
    if not isinstance(value, str) or len(value) != 43 or not _B64URL_RE.fullmatch(value):
        raise ValueError("invalid secret encoding")
    try:
        raw = base64.urlsafe_b64decode(value + "=")
    except (binascii.Error, ValueError):
        raise ValueError("invalid secret encoding") from None
    if len(raw) != 32 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise ValueError("invalid secret encoding")
    return raw


def _valid_scope(scope: object) -> bool:
    if not isinstance(scope, str) or len(scope) > 256 or scope.count(" ") != 1:
        return False
    method, path = scope.split(" ", 1)
    return _METHOD_RE.fullmatch(method) is not None and _PATH_RE.fullmatch(path) is not None


def _validate_scopes(value: object) -> bool:
    return (isinstance(value, list) and 0 < len(value) <= MAX_SCOPES
            and all(_valid_scope(scope) for scope in value)
            and len(set(value)) == len(value))


def validate_state(state: object) -> dict[str, Any]:
    """Validate and return a detached mutable v2 snapshot.

    The schema is exact at every object boundary. This rejects unknown fields,
    duplicate JSON keys (during parsing), booleans masquerading as integers,
    invalid key/enrollment relationships, and unbounded collections.
    """
    if not isinstance(state, dict) or set(state) != {
        "version", "instance_id", "audience", "generation", "last_wall_time",
        "keys", "enrollments", "nonces", "rate_limits",
    }:
        raise ValueError("invalid top-level schema")
    if (type(state["version"]) is not int or state["version"] != VERSION
            or not _is_id(state["instance_id"]) or not _is_id(state["audience"])
            or type(state["generation"]) is not int or state["generation"] < 1
            or not _is_timestamp(state["last_wall_time"])):
        raise ValueError("invalid top-level values")

    keys = state["keys"]
    enrollments = state["enrollments"]
    nonces = state["nonces"]
    rate_limits = state["rate_limits"]
    if (not isinstance(keys, dict) or len(keys) > MAX_KEYS
            or not isinstance(enrollments, dict) or len(enrollments) > MAX_ENROLLMENTS
            or not isinstance(nonces, dict) or len(nonces) > MAX_NONCES
            or not isinstance(rate_limits, dict) or len(rate_limits) > MAX_RATE_LIMITS):
        raise ValueError("invalid collection")

    for key_id, item in keys.items():
        if (not _is_id(key_id) or not isinstance(item, dict)
                or set(item) != _KEY_FIELDS):
            raise ValueError("invalid key record")
        if (not _is_id(item["principal_id"]) or item["audience"] != state["audience"]
                or not _validate_scopes(item["scopes"])
                or type(item["not_before"]) is not int
                or type(item["expires_at"]) is not int
                or item["not_before"] < 0 or item["not_before"] > 253402300799
                or item["expires_at"] <= item["not_before"]
                or item["expires_at"] > 253402300799
                or type(item["revoked"]) is not bool):
            raise ValueError("invalid key values")
        _decode_secret(item["secret_b64"])
        digest = item["enrollment_digest"]
        if digest is not None and (not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest)):
            raise ValueError("invalid key enrollment link")

    consumed_operations: set[tuple[str, str]] = set()
    for digest, item in enrollments.items():
        if (not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest)
                or not isinstance(item, dict) or set(item) != _ENROLLMENT_FIELDS):
            raise ValueError("invalid enrollment record")
        if (not _is_id(item["principal_id"]) or item["audience"] != state["audience"]
                or not _validate_scopes(item["scopes"])
                or not _is_id(item["issuer_key_id"])
                or not _is_timestamp(item["issued_at"])
                or not _is_timestamp(item["expires_at"])
                or item["expires_at"] <= item["issued_at"]
                or not isinstance(item["status"], str)
                or item["status"] not in {"pending", "consumed", "revoked"}):
            raise ValueError("invalid enrollment values")
        consumed_fields = (item["consumed_at"], item["operation_id"],
                           item["client_key_fingerprint"], item["key_id"])
        if item["status"] == "pending":
            if any(value is not None for value in consumed_fields):
                raise ValueError("pending enrollment has consumption data")
        elif all(value is None for value in consumed_fields):
            if item["status"] == "consumed":
                raise ValueError("consumed enrollment lacks key link")
        else:
            consumed_at, operation_id, fingerprint, key_id = consumed_fields
            if (not _is_timestamp(consumed_at) or not _is_id(operation_id)
                    or not isinstance(fingerprint, str) or not _HEX64_RE.fullmatch(fingerprint)
                    or not _is_id(key_id)):
                raise ValueError("invalid enrollment consumption data")
            key = keys.get(key_id)
            if (key is None or key["enrollment_digest"] != digest
                    or key["principal_id"] != item["principal_id"]
                    or key["audience"] != item["audience"]):
                raise ValueError("enrollment/key link mismatch")
        if item["issuer_key_id"] not in keys:
            raise ValueError("unknown enrollment issuer")
        issuer = keys[item["issuer_key_id"]]
        if issuer["revoked"] and item["status"] == "pending":
            raise ValueError("revoked issuer has pending enrollment")
        if item["status"] in {"consumed", "revoked"} and item["key_id"] is not None:
            key = keys[item["key_id"]]
            if (key["scopes"] != item["scopes"]
                    or key["not_before"] < item["issued_at"]
                    or key["expires_at"] > item["expires_at"]
                    or item["consumed_at"] < item["issued_at"]
                    or item["consumed_at"] >= item["expires_at"]):
                raise ValueError("enrollment/key scope or validity mismatch")
            operation = (item["principal_id"], item["operation_id"])
            if operation in consumed_operations:
                raise ValueError("duplicate enrollment operation")
            consumed_operations.add(operation)

    for key_id, item in keys.items():
        digest = item["enrollment_digest"]
        if digest is not None:
            enrollment = enrollments.get(digest)
            if (enrollment is None or enrollment["key_id"] != key_id
                    or enrollment["status"] not in {"consumed", "revoked"}):
                raise ValueError("orphan verifier key")

    for digest, expiry in nonces.items():
        if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest) or not _is_timestamp(expiry):
            raise ValueError("invalid nonce record")

    for bucket, item in rate_limits.items():
        if (not _is_id(bucket) or not isinstance(item, dict)
                or set(item) != _RATE_LIMIT_FIELDS
                or not _is_timestamp(item["window_start"])
                or type(item["count"]) is not int or item["count"] < 0
                or item["count"] > 2**31 - 1):
            raise ValueError("invalid rate limit record")

    # Do not hand state owned by a caller to transaction code; JSON types are
    # already constrained, so a round trip is a simple deep copy.
    return json.loads(json.dumps(state, separators=(",", ":")))


def _encode_state(state: object) -> bytes:
    validated = validate_state(state)
    payload = json.dumps(validated, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    if not payload or len(payload) + 1 > MAX_STORE_BYTES:
        raise ValueError("state exceeds byte limit")
    return payload + b"\n"


def _secure_root_fd(root: Path) -> int:
    if not root.is_absolute() or ".." in root.parts:
        _raise("unsafe_root")
    parts = [part for part in root.parts if part not in ("/", "")]
    flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open("/", flags)
    except OSError:
        _raise("secure_root_unavailable")
    try:
        for index, part in enumerate(parts):
            child = os.open(part, flags, dir_fd=fd)
            info = os.fstat(child)
            if not stat.S_ISDIR(info.st_mode):
                os.close(child)
                _raise("unsafe_root")
            is_root = index == len(parts) - 1
            if is_root:
                if (info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o700):
                    os.close(child)
                    _raise("unsafe_root")
            else:
                writable_by_others = stat.S_IMODE(info.st_mode) & 0o022
                sticky = bool(info.st_mode & stat.S_ISVTX)
                foreign_owner_without_sticky = (
                    info.st_uid not in (0, os.geteuid()) and not sticky)
                if foreign_owner_without_sticky or writable_by_others and not sticky:
                    os.close(child)
                    _raise("unsafe_root_path")
            os.close(fd)
            fd = child
        if not parts:
            _raise("unsafe_root")
        return fd
    except AuthStateError:
        os.close(fd)
        raise
    except OSError:
        os.close(fd)
        _raise("secure_root_unavailable")


def _open_private_file(root_fd: int, name: str, *, writable: bool = False) -> int:
    flags = (os.O_RDWR if writable else os.O_RDONLY)
    flags |= (getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
              | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(name, flags, dir_fd=root_fd)
    except FileNotFoundError:
        _raise("initialized_store_required")
    except OSError:
        _raise("unsafe_store_file")
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1):
            _raise("unsafe_store_file")
        # O_NONBLOCK prevents opening a FIFO from waiting for a peer. Once the
        # descriptor is proven to be a regular file, restore ordinary flags.
        open_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, open_flags & ~getattr(os, "O_NONBLOCK", 0))
        return fd
    except OSError:
        os.close(fd)
        _raise("unsafe_store_file")
    except Exception:
        os.close(fd)
        raise


def _acquire_lock(root_fd: int, timeout: float) -> int:
    fd = _open_private_file(root_fd, LOCK_NAME, writable=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                os.close(fd)
                _raise("lock_unavailable")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                os.close(fd)
                _raise("lock_timeout")
            time.sleep(min(0.025, remaining))
    try:
        held = os.fstat(fd)
        current = os.stat(LOCK_NAME, dir_fd=root_fd, follow_symlinks=False)
        if ((held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
                or held.st_nlink != 1 or not stat.S_ISREG(current.st_mode)):
            _raise("lock_replaced")
    except AuthStateError:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        raise
    except OSError:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        _raise("lock_unavailable")
    return fd


def _read_snapshot(root_fd: int) -> dict[str, Any]:
    fd = _open_private_file(root_fd, STORE_NAME)
    try:
        info = os.fstat(fd)
        if info.st_size <= 0 or info.st_size > MAX_STORE_BYTES:
            _raise("store_size_invalid")
        pieces: list[bytes] = []
        remaining = MAX_STORE_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            pieces.append(chunk)
            remaining -= len(chunk)
        data = b"".join(pieces)
        if not data or len(data) > MAX_STORE_BYTES:
            _raise("store_size_invalid")
        try:
            document = json.loads(data.decode("utf-8"),
                                  object_pairs_hook=_pairs_no_duplicates,
                                  parse_constant=_reject_json_constant)
            return validate_state(document)
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
            _raise("store_invalid")
    except OSError:
        _raise("store_read_failed")
    finally:
        os.close(fd)


def _atomic_replace(root_fd: int, payload: bytes) -> None:
    """Write a complete same-directory snapshot and atomically replace state.

    Any failure before ``os.replace`` returns is a known pre-commit failure.
    Once replace returns, a parent-directory fsync failure is explicitly
    ``CommitUnknown``: callers must not retry as though nothing was committed.
    """
    temp_name: str | None = None
    replaced = False
    phase = "pre_replace"
    fd = -1
    try:
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        for _ in range(16):
            temp_name = f".auth-state-v2.{secrets.token_hex(12)}.tmp"
            try:
                fd = os.open(temp_name, flags, 0o600, dir_fd=root_fd)
                break
            except FileExistsError:
                temp_name = None
        if fd < 0 or temp_name is None:
            _raise("temporary_file_unavailable")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Refuse to overwrite a missing or unsafe initialized store.
        check_fd = _open_private_file(root_fd, STORE_NAME)
        os.close(check_fd)

        # Mark the syscall boundary before entering os.replace. An asynchronous
        # BaseException in or immediately after the syscall is ambiguous; a
        # returned OSError is a known pre-commit failure on this POSIX path.
        phase = "replace_attempt"
        try:
            os.replace(temp_name, STORE_NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd)
        except OSError:
            phase = "pre_replace"
            _raise("commit_not_started")
        except BaseException:
            raise CommitUnknown() from None
        else:
            replaced = True
            phase = "replaced"

        try:
            os.fsync(root_fd)
        except BaseException:
            raise CommitUnknown() from None
    except CommitUnknown:
        raise
    except AuthStateError:
        raise
    except OSError:
        if phase in {"replace_attempt", "replaced"}:
            raise CommitUnknown() from None
        _raise("commit_not_started")
    except BaseException:
        if phase in {"replace_attempt", "replaced"}:
            raise CommitUnknown() from None
        raise
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_name is not None and not replaced:
            try:
                os.unlink(temp_name, dir_fd=root_fd)
            except OSError:
                pass


class AuthStateStore:
    """Access one pre-initialized v2 auth-state snapshot.

    ``root`` must already exist as an owner-only directory. Both fixed file
    names must already exist as owner-only regular files in that root. The
    constructor and methods never bootstrap missing state or lock files.

    ``generation_floor`` is an optional value read from an external trusted
    anchor by the caller. It only rejects a snapshot below that floor; this
    class does not update or create an external anchor.
    """

    def __init__(self, root: str | os.PathLike[str], *,
                 lock_timeout: float = 1.0, clock: Callable[[], float] = time.time,
                 generation_floor: int | None = None):
        if (isinstance(lock_timeout, bool) or not isinstance(lock_timeout, (int, float))
                or not math.isfinite(lock_timeout) or lock_timeout <= 0):
            raise ValueError("lock_timeout must be finite and positive")
        if (generation_floor is not None
                and (type(generation_floor) is not int or generation_floor < 1)):
            raise ValueError("generation_floor must be a positive integer")
        path = Path(root)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("root must be an absolute path without parent traversal")
        self.root = path
        self.lock_timeout = float(lock_timeout)
        self.clock = clock
        self.generation_floor = generation_floor

    def _with_lock(self) -> tuple[int, int, dict[str, Any]]:
        root_fd = _secure_root_fd(self.root)
        try:
            lock_fd = _acquire_lock(root_fd, self.lock_timeout)
        except Exception:
            os.close(root_fd)
            raise
        try:
            state = _read_snapshot(root_fd)
            if (self.generation_floor is not None
                    and state["generation"] < self.generation_floor):
                _raise("generation_rollback")
            return root_fd, lock_fd, state
        except Exception:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            os.close(root_fd)
            raise

    @staticmethod
    def _release(root_fd: int, lock_fd: int) -> None:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
            os.close(root_fd)

    def read(self) -> dict[str, Any]:
        """Return a validated detached snapshot under the stable lock."""
        root_fd, lock_fd, state = self._with_lock()
        try:
            return state
        finally:
            self._release(root_fd, lock_fd)

    def transact(self, mutate: Callable[[MutableMapping[str, Any]], Any], *,
                 now: int | float | None = None) -> Any:
        """Mutate and commit exactly one validated snapshot transaction.

        The callback runs under the stable flock and must only mutate the
        supplied detached state. Callback or validation failures do not write.
        The persisted wall-clock high-water and generation are advanced in the
        same snapshot. A clock rollback is rejected before callback invocation.
        """
        if not callable(mutate):
            raise TypeError("mutate must be callable")
        if now is None:
            try:
                now = self.clock()
            except Exception:
                raise AuthStateError("clock_unavailable") from None
        try:
            valid_now = (not isinstance(now, bool) and isinstance(now, (int, float))
                         and math.isfinite(now) and 0 <= now <= 253402300799)
        except (OverflowError, TypeError, ValueError):
            valid_now = False
        if not valid_now:
            raise AuthStateError("clock_unavailable")
        wall_time = int(now)
        root_fd, lock_fd, state = self._with_lock()
        try:
            if wall_time < state["last_wall_time"]:
                _raise("clock_rollback")
            fixed = (state["version"], state["instance_id"], state["audience"],
                     state["generation"])
            result = mutate(state)
            if (state.get("version"), state.get("instance_id"), state.get("audience"),
                    state.get("generation")) != fixed:
                _raise("immutable_state_field")
            state["last_wall_time"] = wall_time
            state["generation"] = fixed[3] + 1
            try:
                payload = _encode_state(state)
            except (TypeError, ValueError, RecursionError):
                _raise("mutation_invalid")
            _atomic_replace(root_fd, payload)
            return result
        finally:
            self._release(root_fd, lock_fd)


def encode_initial_state(state: object) -> bytes:
    """Serialize a complete operator-provisioned snapshot for offline setup.

    This helper validates but writes nothing. It is deliberately not a
    bootstrap API and never creates the root, lock, or store file.
    """
    try:
        return _encode_state(state)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("invalid v2 auth state") from None
