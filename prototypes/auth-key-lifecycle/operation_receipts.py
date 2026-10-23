"""Fixture-only atomic operation receipts for auth create/revoke.

This prototype wraps a strictly validated auth-state-v2 snapshot with a
bounded operation map in one temporary snapshot file. It is not a production
store format or enrollment service.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import time
from typing import Any, Callable
import fcntl


MARKER_NAME = ".yuva-auth-operation-receipt-fixture"
MARKER_CONTENT = b"yuva-auth-operation-receipt-fixture-v1\n"
SNAPSHOT_NAME = "auth-operation-receipt-fixture.json"
LOCK_NAME = ".kilit"
MAX_OPERATIONS = 256
MAX_OPERATION_BYTES = 256 * 1024
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_FIELDS = {
    "principal_id", "operation_id", "kind", "request_digest",
    "result_code", "result", "committed_generation",
}


def _load_auth_store():
    path = Path(__file__).resolve().parents[2] / "panel" / "auth_store_v2.py"
    spec = importlib.util.spec_from_file_location(
        "yuva_auth_store_operation_receipt_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("auth store module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth_store = _load_auth_store()


class FixtureError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _safe_root(root: str | os.PathLike[str]) -> Path:
    try:
        supplied = Path(root).absolute()
        resolved = supplied.resolve(strict=False)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise FixtureError("fixture_root_rejected") from None
    if supplied != resolved or resolved == temp_root or temp_root not in resolved.parents:
        raise FixtureError("fixture_root_rejected")
    return resolved


def _validate_receipt(operation_id: str, receipt: object,
                      auth_state_generation: int) -> dict[str, Any]:
    if (not isinstance(operation_id, str) or not _ID.fullmatch(operation_id)
            or not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS):
        raise ValueError("invalid operation receipt")
    if (receipt["operation_id"] != operation_id
            or not isinstance(receipt["principal_id"], str)
            or not _ID.fullmatch(receipt["principal_id"])
            or receipt["kind"] not in {"enrollment.create", "key.revoke"}
            or not isinstance(receipt["request_digest"], str)
            or not _HEX64.fullmatch(receipt["request_digest"])
            or receipt["result_code"] not in {
                "enrollment_created", "key_revoked", "already_revoked"}
            or not isinstance(receipt["result"], dict)
            or type(receipt["committed_generation"]) is not int
            or not 1 <= receipt["committed_generation"] <= auth_state_generation):
        raise ValueError("invalid operation receipt values")
    result = receipt["result"]
    if receipt["kind"] == "enrollment.create":
        if set(result) != {"enrollment_digest"}:
            raise ValueError("invalid create receipt result")
        if not isinstance(result["enrollment_digest"], str) or not _HEX64.fullmatch(
                result["enrollment_digest"]):
            raise ValueError("invalid create receipt target")
    elif set(result) != {"key_id"} or not isinstance(result["key_id"], str) \
            or not _ID.fullmatch(result["key_id"]):
        raise ValueError("invalid revoke receipt target")
    return receipt


def _validate_document(document: object) -> dict[str, Any]:
    if (not isinstance(document, dict)
            or set(document) != {"fixture_version", "auth_state", "operations"}
            or type(document["fixture_version"]) is not int
            or document["fixture_version"] != 1):
        raise ValueError("invalid fixture document")
    auth_state = auth_store.validate_state(document["auth_state"])
    operations = document["operations"]
    if not isinstance(operations, dict) or len(operations) > MAX_OPERATIONS:
        raise ValueError("invalid operation collection")
    operation_bytes = json.dumps(operations, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(operation_bytes) > MAX_OPERATION_BYTES:
        raise ValueError("operation receipt byte limit exceeded")
    clean_operations = {}
    for operation_id, receipt in operations.items():
        clean_operations[operation_id] = _validate_receipt(
            operation_id, receipt, auth_state["generation"])
    return {"fixture_version": 1, "auth_state": auth_state,
            "operations": clean_operations}


def _encode(document: object) -> bytes:
    clean = _validate_document(document)
    encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"
    if len(encoded) > auth_store.MAX_STORE_BYTES:
        raise ValueError("fixture snapshot exceeds byte limit")
    return encoded


class ReceiptFixtureStore:
    """Private temporary store with one lock and one atomic state/receipt file."""

    def __init__(self, root: str | os.PathLike[str], *, clock=time.time,
                 lock_timeout: float = 1.0):
        path = Path(root)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("fixture root must be absolute")
        self.root = path
        self.clock = clock
        self.lock_timeout = lock_timeout

    @classmethod
    def initialize(cls, root: str | os.PathLike[str], auth_state: object,
                   *, clock=time.time):
        path = _safe_root(root)
        try:
            clean_state = auth_store.validate_state(auth_state)
            path.mkdir(mode=0o700)
            path.chmod(0o700)
            marker = os.open(path / MARKER_NAME,
                             os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(marker, "wb") as stream:
                stream.write(MARKER_CONTENT)
                stream.flush()
                os.fsync(stream.fileno())
            lock_fd = os.open(path / LOCK_NAME,
                              os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(lock_fd)
            snapshot_fd = os.open(path / SNAPSHOT_NAME,
                                  os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(snapshot_fd, "wb") as stream:
                stream.write(_encode({"fixture_version": 1,
                                      "auth_state": clean_state,
                                      "operations": {}}))
                stream.flush()
                os.fsync(stream.fileno())
            root_fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(root_fd)
            finally:
                os.close(root_fd)
        except Exception:
            raise FixtureError("fixture_initialization_failed") from None
        return cls(path, clock=clock)

    def _check_root(self) -> int:
        try:
            root_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                              | getattr(os, "O_NOFOLLOW", 0))
            info = os.fstat(root_fd)
            marker = os.stat(MARKER_NAME, dir_fd=root_fd, follow_symlinks=False)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o700
                    or not stat.S_ISREG(marker.st_mode) or marker.st_uid != os.geteuid()
                    or stat.S_IMODE(marker.st_mode) != 0o600
                    or marker.st_size != len(MARKER_CONTENT)):
                raise OSError("unsafe fixture root")
            marker_fd = os.open(MARKER_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                if os.read(marker_fd, len(MARKER_CONTENT) + 1) != MARKER_CONTENT:
                    raise OSError("invalid fixture marker")
            finally:
                os.close(marker_fd)
            return root_fd
        except OSError:
            raise auth_store.AuthStateError("store_unavailable") from None

    def _locked_document(self):
        root_fd = self._check_root()
        lock_fd = -1
        try:
            lock_fd = os.open(LOCK_NAME, os.O_RDWR | os.O_NOFOLLOW
                              | getattr(os, "O_CLOEXEC", 0), dir_fd=root_fd)
            lock_info = os.fstat(lock_fd)
            lock_path = os.stat(LOCK_NAME, dir_fd=root_fd, follow_symlinks=False)
            if ((lock_info.st_dev, lock_info.st_ino) != (lock_path.st_dev, lock_path.st_ino)
                    or not stat.S_ISREG(lock_info.st_mode)
                    or lock_info.st_uid != os.geteuid()
                    or stat.S_IMODE(lock_info.st_mode) != 0o600
                    or lock_info.st_nlink != 1 or lock_info.st_size != 0):
                raise auth_store.AuthStateError("lock_unsafe")
            deadline = time.monotonic() + self.lock_timeout
            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise auth_store.AuthStateError("lock_busy") from None
                    time.sleep(0.01)
            document = self._read_document(root_fd)
            return root_fd, lock_fd, document
        except BaseException:
            if lock_fd >= 0:
                os.close(lock_fd)
            os.close(root_fd)
            raise

    def _read_document(self, root_fd: int) -> dict[str, Any]:
        fd = -1
        try:
            fd = os.open(SNAPSHOT_NAME, os.O_RDONLY | os.O_NOFOLLOW
                         | getattr(os, "O_CLOEXEC", 0), dir_fd=root_fd)
            info = os.fstat(fd)
            current = os.stat(SNAPSHOT_NAME, dir_fd=root_fd, follow_symlinks=False)
            if ((info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
                    or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size < 1 or info.st_size > auth_store.MAX_STORE_BYTES):
                raise ValueError("unsafe snapshot")
            with os.fdopen(fd, "rb") as stream:
                fd = -1
                payload = stream.read(auth_store.MAX_STORE_BYTES + 1)
            document = json.loads(payload.decode("ascii"),
                                  object_pairs_hook=auth_store._pairs_no_duplicates,
                                  parse_constant=auth_store._reject_json_constant)
            return _validate_document(document)
        except auth_store.AuthStateError:
            raise
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
            raise auth_store.AuthStateError("store_invalid") from None
        finally:
            if fd >= 0:
                os.close(fd)

    @staticmethod
    def _release(root_fd: int, lock_fd: int):
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
            os.close(root_fd)

    def read(self) -> dict[str, Any]:
        root_fd, lock_fd, document = self._locked_document()
        try:
            return document
        finally:
            self._release(root_fd, lock_fd)

    def _atomic_replace(self, root_fd: int, document: object):
        payload = _encode(document)
        temp_name = f".auth-operation-receipt.{secrets.token_hex(12)}.tmp"
        fd = -1
        replaced = False
        phase = "pre_replace"
        try:
            fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                         0o600, dir_fd=root_fd)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            phase = "replace_attempt"
            try:
                os.replace(temp_name, SNAPSHOT_NAME,
                           src_dir_fd=root_fd, dst_dir_fd=root_fd)
            except OSError:
                phase = "pre_replace"
                raise auth_store.AuthStateError("commit_not_started") from None
            except BaseException:
                raise auth_store.CommitUnknown() from None
            phase = "replaced"
            replaced = True
            try:
                os.fsync(root_fd)
            except BaseException:
                raise auth_store.CommitUnknown() from None
        except auth_store.AuthStateError:
            raise
        except OSError:
            if phase in {"replace_attempt", "replaced"}:
                raise auth_store.CommitUnknown() from None
            raise auth_store.AuthStateError("commit_not_started") from None
        except BaseException:
            if phase in {"replace_attempt", "replaced"}:
                raise auth_store.CommitUnknown() from None
            raise
        finally:
            if fd >= 0:
                os.close(fd)
            if not replaced:
                try:
                    os.unlink(temp_name, dir_fd=root_fd)
                except OSError:
                    pass

    def transact_operation(self, *, operation_id: str, principal_id: str,
                           kind: str, request_digest: str,
                           mutate: Callable[[dict[str, Any]], tuple[str, dict[str, Any]]],
                           now: int):
        if (not isinstance(operation_id, str) or not _ID.fullmatch(operation_id)
                or not isinstance(principal_id, str) or not _ID.fullmatch(principal_id)
                or kind not in {"enrollment.create", "key.revoke"}
                or not isinstance(request_digest, str) or not _HEX64.fullmatch(request_digest)
                or type(now) is not int or now < 0):
            raise FixtureError("operation_input_invalid")
        root_fd, lock_fd, document = self._locked_document()
        try:
            state = document["auth_state"]
            if now < state["last_wall_time"]:
                raise auth_store.AuthStateError("clock_rollback")
            existing = document["operations"].get(operation_id)
            if existing is not None:
                if (existing["principal_id"] == principal_id
                        and existing["kind"] == kind
                        and existing["request_digest"] == request_digest):
                    return "replayed", existing
                raise FixtureError("operation_id_conflict")
            if len(document["operations"]) >= MAX_OPERATIONS:
                raise FixtureError("operation_receipt_limit")

            updated_state = json.loads(json.dumps(state))
            result_code, result = mutate(updated_state)
            updated_state["last_wall_time"] = now
            updated_state["generation"] += 1
            clean_state = auth_store.validate_state(updated_state)
            receipt = {
                "principal_id": principal_id,
                "operation_id": operation_id,
                "kind": kind,
                "request_digest": request_digest,
                "result_code": result_code,
                "result": result,
                "committed_generation": clean_state["generation"],
            }
            next_document = {"fixture_version": 1, "auth_state": clean_state,
                             "operations": dict(document["operations"])}
            next_document["operations"][operation_id] = receipt
            operation_bytes = json.dumps(next_document["operations"], sort_keys=True,
                                         separators=(",", ":"), ensure_ascii=True,
                                         allow_nan=False).encode("ascii")
            if len(operation_bytes) > MAX_OPERATION_BYTES:
                raise FixtureError("operation_receipt_limit")
            self._atomic_replace(root_fd, next_document)
            return "committed", receipt
        finally:
            self._release(root_fd, lock_fd)


def request_fingerprint(kind: str, principal_id: str,
                        payload: dict[str, Any]) -> str:
    canonical = json.dumps({"kind": kind, "principal_id": principal_id,
                            "payload": payload}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=True,
                           allow_nan=False).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _receipt_for(store: ReceiptFixtureStore, *, operation_id: str,
                 principal_id: str, kind: str, request_digest: str):
    document = store.read()
    receipt = document["operations"].get(operation_id)
    if (receipt is None or receipt["principal_id"] != principal_id
            or receipt["kind"] != kind or receipt["request_digest"] != request_digest):
        return None, document
    return receipt, document


def create_enrollment(store: ReceiptFixtureStore, *, operation_id: str,
                      principal_id: str, token_digest: str, issuer_key_id: str,
                      scopes: list[str], expires_at: int, now: int,
                      admin_principals: list[str], allowed_principals: list[str]):
    if not isinstance(token_digest, str) or not _HEX64.fullmatch(token_digest):
        raise FixtureError("enrollment_digest_invalid")
    if not isinstance(issuer_key_id, str) or not _ID.fullmatch(issuer_key_id):
        raise FixtureError("issuer_invalid")
    if (type(expires_at) is not int or type(now) is not int or expires_at <= now
            or expires_at > 253402300799):
        raise FixtureError("enrollment_expired_or_invalid")
    if principal_id not in set(allowed_principals):
        raise FixtureError("principal_not_allowed")
    if not isinstance(scopes, list) or not scopes or len(scopes) != len(set(scopes)):
        raise FixtureError("scope_invalid")
    payload = {"token_digest": token_digest, "issuer_key_id": issuer_key_id,
               "scopes": scopes, "expires_at": expires_at}
    fingerprint = request_fingerprint("enrollment.create", principal_id, payload)

    def mutate(state):
        issuer = state["keys"].get(issuer_key_id)
        if issuer is None or issuer["revoked"] or issuer["expires_at"] <= now:
            raise FixtureError("issuer_inactive")
        if issuer["principal_id"] not in set(admin_principals):
            raise FixtureError("issuer_not_allowlisted_admin")
        if (any(not auth_store._valid_scope(scope) for scope in scopes)
                or not set(scopes).issubset(set(issuer["scopes"]))):
            raise FixtureError("scope_exceeds_issuer")
        if expires_at > issuer["expires_at"]:
            raise FixtureError("enrollment_expiry_exceeds_issuer")
        if token_digest in state["enrollments"]:
            raise FixtureError("enrollment_conflict")
        state["enrollments"][token_digest] = {
            "principal_id": principal_id,
            "audience": state["audience"],
            "scopes": list(scopes),
            "issuer_key_id": issuer_key_id,
            "issued_at": now,
            "expires_at": expires_at,
            "status": "pending",
            "consumed_at": None,
            "operation_id": None,
            "client_key_fingerprint": None,
            "key_id": None,
        }
        return "enrollment_created", {"enrollment_digest": token_digest}

    return store.transact_operation(
        operation_id=operation_id, principal_id=principal_id,
        kind="enrollment.create", request_digest=fingerprint,
        mutate=mutate, now=now)


def revoke_key(store: ReceiptFixtureStore, *, operation_id: str,
               principal_id: str, key_id: str, now: int):
    if not isinstance(key_id, str) or not _ID.fullmatch(key_id):
        raise FixtureError("key_id_invalid")
    fingerprint = request_fingerprint("key.revoke", principal_id, {"key_id": key_id})

    def mutate(state):
        key = state["keys"].get(key_id)
        if key is None:
            raise FixtureError("key_not_found")
        result_code = "already_revoked" if key["revoked"] else "key_revoked"
        key["revoked"] = True
        for enrollment in state["enrollments"].values():
            if enrollment["issuer_key_id"] == key_id and enrollment["status"] == "pending":
                enrollment["status"] = "revoked"
            if enrollment.get("key_id") == key_id and enrollment["status"] == "consumed":
                enrollment["status"] = "revoked"
        return result_code, {"key_id": key_id}

    return store.transact_operation(
        operation_id=operation_id, principal_id=principal_id,
        kind="key.revoke", request_digest=fingerprint,
        mutate=mutate, now=now)


def reconcile_create(store: ReceiptFixtureStore, *, operation_id: str,
                     principal_id: str, token_digest: str,
                     issuer_key_id: str, scopes: list[str], expires_at: int,
                     issued_at: int):
    payload = {"token_digest": token_digest, "issuer_key_id": issuer_key_id,
               "scopes": scopes, "expires_at": expires_at}
    fingerprint = request_fingerprint("enrollment.create", principal_id, payload)
    receipt, document = _receipt_for(store, operation_id=operation_id,
                                    principal_id=principal_id,
                                    kind="enrollment.create",
                                    request_digest=fingerprint)
    if receipt is None or receipt["result"].get("enrollment_digest") != token_digest:
        return "unresolved"
    enrollment = document["auth_state"]["enrollments"].get(token_digest)
    if (enrollment is None or enrollment["principal_id"] != principal_id
            or enrollment["audience"] != document["auth_state"]["audience"]
            or enrollment["issuer_key_id"] != issuer_key_id
            or enrollment["scopes"] != scopes
            or enrollment["issued_at"] != issued_at
            or enrollment["expires_at"] != expires_at
            or enrollment["consumed_at"] is not None
            or enrollment["operation_id"] is not None
            or enrollment["client_key_fingerprint"] is not None
            or enrollment["key_id"] is not None
            or enrollment["status"] != "pending"):
        return "unresolved"
    return "committed"


def reconcile_revoke(store: ReceiptFixtureStore, *, operation_id: str,
                     principal_id: str, key_id: str):
    fingerprint = request_fingerprint("key.revoke", principal_id, {"key_id": key_id})
    receipt, document = _receipt_for(store, operation_id=operation_id,
                                    principal_id=principal_id,
                                    kind="key.revoke", request_digest=fingerprint)
    if receipt is None or receipt["result"].get("key_id") != key_id:
        return "unresolved"
    state = document["auth_state"]
    key = state["keys"].get(key_id)
    if key is None or not key["revoked"]:
        return "unresolved"
    for enrollment in state["enrollments"].values():
        if (enrollment["issuer_key_id"] == key_id and enrollment["status"] == "pending"):
            return "unresolved"
        if enrollment.get("key_id") == key_id and enrollment["status"] == "consumed":
            return "unresolved"
    return "committed"
