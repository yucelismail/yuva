"""Synthetic-only auth lifecycle transactions over the real v2 store API.

This fixture is not a key generator, enrollment service, CLI, or auth route.
It uses a fixed non-secret test byte string and a private marked temp store.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Iterable


MARKER_NAME = ".yuva-auth-lifecycle-fixture"
MARKER_CONTENT = b"yuva-auth-lifecycle-fixture-v1\n"
SYNTHETIC_ISSUER_BYTES = bytes([0x31]) * 32
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class LifecycleError(ValueError):
    """Fixture policy rejection with a constant content-free code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _load_auth_store():
    path = Path(__file__).resolve().parents[2] / "panel" / "auth_store_v2.py"
    spec = importlib.util.spec_from_file_location("yuva_auth_store_lifecycle_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture store module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth_store = _load_auth_store()


def _safe_root(root: str | os.PathLike[str]) -> Path:
    try:
        supplied = Path(root).absolute()
        resolved = supplied.resolve(strict=False)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise LifecycleError("fixture_root_rejected") from None
    if (supplied != resolved or resolved == temp_root or temp_root not in resolved.parents):
        raise LifecycleError("fixture_root_rejected")
    return resolved


def initial_state():
    """Return a fixture-only v2 snapshot containing one synthetic issuer."""
    secret = base64.urlsafe_b64encode(SYNTHETIC_ISSUER_BYTES).rstrip(b"=").decode("ascii")
    return {
        "version": 2,
        "instance_id": "fixture-instance",
        "audience": "fixture-audience",
        "generation": 1,
        "last_wall_time": 100,
        "keys": {
            "fixture-issuer": {
                "principal_id": "fixture-admin",
                "audience": "fixture-audience",
                "scopes": ["POST /api/auth/enrollments", "POST /api/auth/redeem",
                           "POST /api/yaz", "POST /api/gorev"],
                "secret_b64": secret,
                "not_before": 100,
                "expires_at": 10000,
                "revoked": False,
                "enrollment_digest": None,
            },
        },
        "enrollments": {},
        "nonces": {},
        "rate_limits": {},
    }


def initialize_fixture_store(root: str | os.PathLike[str]):
    """Create a marked temp-only auth store with deterministic synthetic data."""
    path = _safe_root(root)
    try:
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        marker_fd = os.open(path / MARKER_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(marker_fd, "wb") as marker:
            marker.write(MARKER_CONTENT)
            marker.flush()
            os.fsync(marker.fileno())
        payload = auth_store.encode_initial_state(initial_state())
        state_fd = os.open(path / auth_store.STORE_NAME,
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(state_fd, "wb") as state_file:
            state_file.write(payload)
            state_file.flush()
            os.fsync(state_file.fileno())
        lock_fd = os.open(path / auth_store.LOCK_NAME,
                          os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(lock_fd)
        dir_fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        # This initializer is used only with a fresh TemporaryDirectory child.
        # Never clean up or overwrite a partially initialized path implicitly.
        raise LifecycleError("fixture_initialization_failed") from None
    return auth_store.AuthStateStore(path, clock=lambda: 100)


def _check_id(value: object, code: str):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise LifecycleError(code)


def create_enrollment(store, *, token_digest: str, principal_id: str,
                      issuer_key_id: str, scopes: Iterable[str],
                      expires_at: int, now: int,
                      admin_principals: Iterable[str],
                      allowed_principals: Iterable[str]):
    """Commit one pending enrollment after allowlist, scope and expiry checks."""
    if not isinstance(token_digest, str) or not _HEX64.fullmatch(token_digest):
        raise LifecycleError("enrollment_digest_invalid")
    _check_id(principal_id, "principal_invalid")
    _check_id(issuer_key_id, "issuer_invalid")
    if type(now) is not int or type(expires_at) is not int or expires_at <= now:
        raise LifecycleError("enrollment_expired_or_invalid")
    admin_set = set(admin_principals)
    principal_set = set(allowed_principals)
    if principal_id not in principal_set:
        raise LifecycleError("principal_not_allowed")
    requested = list(scopes)
    if not requested or len(requested) != len(set(requested)):
        raise LifecycleError("scope_invalid")

    def mutate(state):
        issuer = state["keys"].get(issuer_key_id)
        if issuer is None or issuer["revoked"] or issuer["expires_at"] <= now:
            raise LifecycleError("issuer_inactive")
        if issuer["principal_id"] not in admin_set:
            raise LifecycleError("issuer_not_allowlisted_admin")
        if (any(not auth_store._valid_scope(scope) for scope in requested)
                or not set(requested).issubset(set(issuer["scopes"]))):
            raise LifecycleError("scope_exceeds_issuer")
        if expires_at > issuer["expires_at"]:
            raise LifecycleError("enrollment_expiry_exceeds_issuer")
        if token_digest in state["enrollments"]:
            existing = state["enrollments"][token_digest]
            if (existing["principal_id"] == principal_id
                    and existing["issuer_key_id"] == issuer_key_id
                    and existing["scopes"] == requested
                    and existing["expires_at"] == expires_at
                    and existing["status"] == "pending"):
                # The schema has no generic create-operation receipt. Returning
                # a matching record is a state read, not proof of operation ID.
                raise LifecycleError("matching_enrollment_exists")
            raise LifecycleError("enrollment_conflict")
        state["enrollments"][token_digest] = {
            "principal_id": principal_id,
            "audience": state["audience"],
            "scopes": requested,
            "issuer_key_id": issuer_key_id,
            "issued_at": now,
            "expires_at": expires_at,
            "status": "pending",
            "consumed_at": None,
            "operation_id": None,
            "client_key_fingerprint": None,
            "key_id": None,
        }
        return "enrollment_created"

    return store.transact(mutate, now=now)


def redeem_enrollment(store, *, token_digest: str, key_id: str,
                      synthetic_client_key: bytes, operation_id: str, now: int):
    """Consume one enrollment and add a fixed synthetic verifier key."""
    if not isinstance(token_digest, str) or not _HEX64.fullmatch(token_digest):
        raise LifecycleError("enrollment_digest_invalid")
    _check_id(key_id, "key_id_invalid")
    _check_id(operation_id, "operation_id_invalid")
    if type(synthetic_client_key) is not bytes or len(synthetic_client_key) != 32:
        raise LifecycleError("fixture_key_invalid")
    fingerprint = hashlib.sha256(synthetic_client_key).hexdigest()
    encoded_secret = base64.urlsafe_b64encode(synthetic_client_key).rstrip(b"=").decode("ascii")
    before = store.read()
    existing = before["enrollments"].get(token_digest)
    if existing is not None and existing["status"] == "consumed":
        if (existing["operation_id"] == operation_id
                and existing["client_key_fingerprint"] == fingerprint
                and existing["key_id"] == key_id):
            return "already_redeemed"
        raise LifecycleError("enrollment_already_consumed")

    def mutate(state):
        enrollment = state["enrollments"].get(token_digest)
        if enrollment is None:
            raise LifecycleError("enrollment_not_found")
        if enrollment["status"] == "consumed":
            if (enrollment["operation_id"] == operation_id
                    and enrollment["client_key_fingerprint"] == fingerprint
                    and enrollment["key_id"] == key_id):
                raise LifecycleError("matching_redeem_exists")
            raise LifecycleError("enrollment_already_consumed")
        if enrollment["status"] != "pending":
            raise LifecycleError("enrollment_not_pending")
        if type(now) is not int or now < enrollment["issued_at"] or now >= enrollment["expires_at"]:
            raise LifecycleError("enrollment_expired")
        issuer = state["keys"].get(enrollment["issuer_key_id"])
        if issuer is None or issuer["revoked"] or issuer["expires_at"] <= now:
            raise LifecycleError("issuer_inactive")
        if key_id in state["keys"]:
            raise LifecycleError("key_id_conflict")
        state["keys"][key_id] = {
            "principal_id": enrollment["principal_id"],
            "audience": enrollment["audience"],
            "scopes": list(enrollment["scopes"]),
            "secret_b64": encoded_secret,
            "not_before": now,
            "expires_at": enrollment["expires_at"],
            "revoked": False,
            "enrollment_digest": token_digest,
        }
        enrollment.update({
            "status": "consumed",
            "consumed_at": now,
            "operation_id": operation_id,
            "client_key_fingerprint": fingerprint,
            "key_id": key_id,
        })
        return "enrollment_redeemed"

    try:
        return store.transact(mutate, now=now)
    except LifecycleError as error:
        if error.code == "matching_redeem_exists":
            return "already_redeemed"
        raise


def reconcile_redeem(store, *, token_digest: str, key_id: str,
                     operation_id: str, synthetic_client_key: bytes):
    """Read back a redeem operation; never retries or returns secret material."""
    fingerprint = hashlib.sha256(synthetic_client_key).hexdigest()
    state = store.read()
    enrollment = state["enrollments"].get(token_digest)
    if (enrollment is not None and enrollment["status"] == "consumed"
            and enrollment["key_id"] == key_id
            and enrollment["operation_id"] == operation_id
            and enrollment["client_key_fingerprint"] == fingerprint):
        return "committed"
    return "unresolved"


def revoke_key(store, *, key_id: str, now: int):
    """Revoke key and pending enrollments it issued in one store transaction."""
    _check_id(key_id, "key_id_invalid")
    before = store.read()
    existing = before["keys"].get(key_id)
    if existing is None:
        raise LifecycleError("key_not_found")
    if existing["revoked"]:
        return "already_revoked"

    def mutate(state):
        key = state["keys"].get(key_id)
        if key is None:
            raise LifecycleError("key_not_found")
        if key["revoked"]:
            raise LifecycleError("already_revoked")
        key["revoked"] = True
        for enrollment in state["enrollments"].values():
            if enrollment["issuer_key_id"] == key_id and enrollment["status"] == "pending":
                enrollment["status"] = "revoked"
            if enrollment.get("key_id") == key_id and enrollment["status"] == "consumed":
                enrollment["status"] = "revoked"
        return "key_revoked"

    try:
        return store.transact(mutate, now=now)
    except LifecycleError as error:
        if error.code == "already_revoked":
            return "already_revoked"
        raise
