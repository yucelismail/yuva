"""Feature-off-by-default HMAC authentication core for the Yuva API.

``panel/server.py`` imports this lazily only when its explicit auth setting is
enabled. It creates no credentials and has no default store path. Callers must
supply an explicitly provisioned ``AuthStateStore`` from ``auth_store_v2``. Key records live in that
store's ``keys`` map and nonce replay state in its ``nonces`` map; there is no
version-1 file reader, automatic migration, or fallback. Provisioning,
rotation, and revocation remain trusted operator actions.

The HMAC key is a shared secret. Keep the v2 auth-state root and lock owner-only
and never log key material. Integrators must reject duplicate/conflicting HTTP
auth headers before calling ``verify_request``. Call it after existing request
size/source checks but before JSON decoding, subprocess calls, local fallbacks,
or endpoint mutations. Use only the returned ``VerifiedPrincipal`` as actor;
never authorize from body identity fields. An integration must not reinterpret
an ``AuthError`` as a transport failure.

The canonical HMAC input is ``YUVA-HMAC-AUTH\\0v1`` followed by each field in
this fixed order, each encoded as a 4-byte unsigned big-endian length and the
field bytes: audience, principal_id, key_id, method, exact path, SHA-256 digest
of raw body bytes, canonical decimal timestamp, nonce. The signature is
unpadded canonical base64url of the 32-byte HMAC-SHA-256 result.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import math
import re
import struct
import time
from dataclasses import dataclass

if __package__:
    from .auth_store_v2 import MAX_NONCES, AuthStateError, AuthStateStore
else:
    from auth_store_v2 import MAX_NONCES, AuthStateError, AuthStateStore


_MAGIC = b"YUVA-HMAC-AUTH\x00v1"
_MAX_FIELD_BYTES = 4096
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_METHOD_RE = re.compile(r"[A-Z]{1,16}\Z")
_PATH_RE = re.compile(r"/(?:[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*)?\Z")
_NONCE_RE = re.compile(r"[A-Za-z0-9_-]{22,128}\Z")
_B64URL_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


class AuthError(Exception):
    """Safe failure for an integrator; messages never contain secret values."""

    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class VerifiedPrincipal:
    """Identity and scope established from a provisioned verifier record."""

    principal_id: str
    key_id: str
    audience: str
    scope: str
    timestamp: int


def _fail(code: str, status: int = 401) -> AuthError:
    return AuthError(status, code)


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _ID_RE.fullmatch(value) is not None


def _canonical_path(value: object) -> bytes:
    if not isinstance(value, str) or _PATH_RE.fullmatch(value) is None:
        raise _fail("invalid_path", 400)
    return value.encode("ascii")


def _canonical_method(value: object) -> bytes:
    if not isinstance(value, str) or _METHOD_RE.fullmatch(value) is None:
        raise _fail("invalid_method", 400)
    return value.encode("ascii")


def _canonical_timestamp(value: object) -> tuple[int, bytes]:
    if type(value) is int:
        timestamp = value
        encoded = str(value)
    elif isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]{0,11})", value):
        timestamp = int(value)
        encoded = value
    else:
        raise _fail("invalid_timestamp", 400)
    if timestamp < 0 or timestamp > 253402300799:
        raise _fail("invalid_timestamp", 400)
    return timestamp, encoded.encode("ascii")


def _base64url_decode_canonical(value: object, *, expected_bytes: int) -> bytes:
    # Unpadded Base64URL needs ceil(n * 8 / 6) characters for n bytes.
    # Bound the input before decoding so direct callers cannot supply an
    # arbitrarily large signature or credential secret.
    expected_chars = (expected_bytes * 8 + 5) // 6
    if (not isinstance(value, str) or len(value) != expected_chars
            or not _B64URL_RE.fullmatch(value)):
        raise _fail("invalid_encoding", 400)
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError):
        raise _fail("invalid_encoding", 400) from None
    if len(decoded) != expected_bytes:
        raise _fail("invalid_encoding", 400)
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if canonical != value:
        raise _fail("invalid_encoding", 400)
    return decoded


def _frame(fields: tuple[bytes, ...]) -> bytes:
    chunks = [_MAGIC]
    for field in fields:
        if len(field) > _MAX_FIELD_BYTES:
            raise _fail("field_too_large", 400)
        chunks.append(struct.pack(">I", len(field)))
        chunks.append(field)
    return b"".join(chunks)


def canonical_request_bytes(
    *, audience: str, principal_id: str, key_id: str, method: str,
    path: str, body: bytes, timestamp: int | str, nonce: str,
) -> bytes:
    """Return the exact canonical bytes future CLI signing must reproduce."""
    for name, value in (("audience", audience), ("principal_id", principal_id),
                        ("key_id", key_id)):
        if not _valid_identifier(value):
            raise _fail(f"invalid_{name}", 400)
    if not isinstance(body, bytes):
        raise _fail("invalid_body", 400)
    _, ts_bytes = _canonical_timestamp(timestamp)
    if not isinstance(nonce, str) or _NONCE_RE.fullmatch(nonce) is None:
        raise _fail("invalid_nonce", 400)
    body_digest = hashlib.sha256(body).digest()
    return _frame((
        audience.encode("ascii"), principal_id.encode("ascii"),
        key_id.encode("ascii"), _canonical_method(method),
        _canonical_path(path), body_digest, ts_bytes, nonce.encode("ascii"),
    ))


def _nonce_digest(principal_id: str, key_id: str, audience: str,
                  scope: str, nonce: str) -> str:
    parts = tuple(x.encode("ascii") for x in
                  (principal_id, key_id, audience, scope, nonce))
    return hashlib.sha256(_frame(parts)).hexdigest()


class HMACAuthenticator:
    """Verify HMAC requests against the pre-provisioned unified v2 store.

    The former ``verifier_path``/``nonce_path``/``lock_path`` constructor is
    intentionally removed. Existing v1 files are never migrated or used as a
    fallback; callers must explicitly supply an initialized ``AuthStateStore``.
    """

    def __init__(self, *, store: AuthStateStore, audience: str,
                 window_seconds: int = 60, clock=time.time):
        if not _valid_identifier(audience):
            raise ValueError("audience must be a short ASCII identifier")
        if type(window_seconds) is not int or not 1 <= window_seconds <= 300:
            raise ValueError("window_seconds must be an integer from 1 to 300")
        if not isinstance(store, AuthStateStore):
            raise TypeError("store must be an initialized AuthStateStore")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self.store = store
        self.audience = audience
        self.window_seconds = window_seconds
        self.clock = clock

    def verify_request(self, *, method: str, path: str, audience: str,
                       body: bytes, timestamp: int | str, nonce: str,
                       key_id: str, principal_id: str,
                       signature: str) -> VerifiedPrincipal:
        """Verify a signed request; raise ``AuthError`` on any denial/failure.

        Successful verification consumes the nonce before returning. A later
        endpoint failure does not release it. Domain-operation idempotency is a
        separate concern and is deliberately not implemented here.
        """
        if audience != self.audience:
            raise _fail("wrong_audience", 403)
        request_bytes = canonical_request_bytes(
            audience=audience, principal_id=principal_id, key_id=key_id,
            method=method, path=path, body=body, timestamp=timestamp, nonce=nonce,
        )
        ts, _ = _canonical_timestamp(timestamp)
        try:
            now = self.clock()
            valid_now = (not isinstance(now, bool) and isinstance(now, (int, float))
                         and math.isfinite(now) and 0 <= now <= 253402300799)
        except (OverflowError, TypeError, ValueError):
            valid_now = False
            now = None
        if not valid_now:
            raise _fail("clock_unavailable", 503)
        if abs(float(now) - ts) > self.window_seconds:
            raise _fail("timestamp_out_of_window", 401)
        scope = f"{method} {path}"
        supplied = _base64url_decode_canonical(signature, expected_bytes=32)
        digest = _nonce_digest(principal_id, key_id, audience, scope, nonce)

        def verify_and_consume(state):
            if state["audience"] != self.audience or audience != self.audience:
                raise _fail("wrong_audience", 403)
            item = state["keys"].get(key_id)
            if (item is None or item["revoked"]
                    or item["principal_id"] != principal_id
                    or item["audience"] != audience
                    or scope not in item["scopes"]):
                raise _fail("invalid_credentials", 401)
            if (float(now) < item["not_before"] or float(now) >= item["expires_at"]
                    or ts < item["not_before"] or ts >= item["expires_at"]):
                raise _fail("credential_expired", 401)
            try:
                secret = _base64url_decode_canonical(item["secret_b64"], expected_bytes=32)
            except AuthError:
                raise _fail("credential_store_invalid", 503) from None
            expected = hmac.digest(secret, request_bytes, "sha256")
            if not hmac.compare_digest(expected, supplied):
                raise _fail("invalid_credentials", 401)

            nonces = state["nonces"]
            for old_digest, expiry in tuple(nonces.items()):
                if expiry < int(now):
                    del nonces[old_digest]
            if digest in nonces:
                raise _fail("nonce_reused", 401)
            if len(nonces) >= MAX_NONCES:
                raise _fail("nonce_store_full", 503)
            nonces[digest] = ts + self.window_seconds + 1

        try:
            self.store.transact(verify_and_consume, now=now)
        except AuthError:
            raise
        except AuthStateError as e:
            # Includes CommitUnknown: never authorize the request if nonce
            # persistence may or may not have completed.
            raise _fail(e.code, e.status) from None

        return VerifiedPrincipal(
            principal_id=principal_id, key_id=key_id, audience=audience,
            scope=scope, timestamp=ts,
        )
