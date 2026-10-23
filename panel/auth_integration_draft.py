"""Feature-off-by-default gate wiring ``auth.HMACAuthenticator`` to routes.

``panel/server.py`` imports this lazily only when ``YUVA_AUTH_ENABLED=1`` and
requires a pre-provisioned store. Constructing ``AuthGate`` without an explicit
verifier leaves the existing API untouched. The caller runs
``authenticate_post`` after source/size checks but before JSON decoding, then
``authorize_payload`` after decoding and before dispatch. No bootstrap,
enrollment, credential creation, or local fallback is provided. A separate
``read_enabled=False`` GET prototype authenticates only exact snapshot routes
with an empty body; it is not connected to the server's GET handler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

# Support both ``import panel.auth_integration_draft`` from the repository root
# and top-level ``import auth_integration_draft`` when panel/ is on sys.path
# (the current server.py execution layout). No sys.path mutation is needed.
if __package__:
    from .auth import AuthError, HMACAuthenticator, VerifiedPrincipal
else:
    from auth import AuthError, HMACAuthenticator, VerifiedPrincipal


# Every mutating POST route must be listed here. Scopes are the exact
# ``POST <path>`` scopes already enforced by HMACAuthenticator.verify_request().
POST_ROUTE_POLICY = {
    "/api/katil": "self",          # enrollment/provisioned identity only
    "/api/kalp": "self",           # authenticated principal, never body claim
    "/api/ayril": "self",
    "/api/ad": "self_or_admin",
    "/api/rol": "admin",
    "/api/sorumlu": "admin",
    "/api/bas-denetci": "admin",
    "/api/yaz": "principal_actor",
    "/api/ekran": "self",
    "/api/not": "closed",          # unused endpoint; deny even with a route key
    "/api/gorev": "task_operation",  # operation policy + Yuva role/ownership checks
}

# Read-only snapshot routes have their own opt-in and exact GET scopes. They do
# not inherit POST scopes or the POST route/actor policy.
GET_ROUTE_POLICY = {
    "/api/veri": "read_snapshot",
    "/veri": "read_snapshot",  # compatibility alias; separate signed path
}

_AUTH_HEADERS = {
    "key_id": "X-Yuva-Key-Id",
    "principal_id": "X-Yuva-Principal",
    "audience": "X-Yuva-Audience",
    "timestamp": "X-Yuva-Timestamp",
    "nonce": "X-Yuva-Nonce",
    "signature": "X-Yuva-Signature",
}


@dataclass(frozen=True)
class AuthenticatedRequest:
    route: str
    principal: VerifiedPrincipal


class AuthGate:
    """Explicitly configured integration draft; disabled unless verifier supplied.

    ``admin_principals`` must come from a trusted operator-managed config,
    never from request JSON, a claimed role, or an enrollment request.
    ``operator_custody_verified`` is a separate explicit trust input; the
    allowlist alone cannot produce the ``operator`` message class. It defaults
    false until provisioning establishes a distinct operator-key custody
    boundary.
    """

    def __init__(self, verifier: HMACAuthenticator | None = None, *,
                 admin_principals: frozenset[str] = frozenset(),
                 operator_custody_verified: bool = False,
                 read_enabled: bool = False):
        if type(read_enabled) is not bool:
            raise ValueError("read_enabled must be an explicit boolean")
        if type(operator_custody_verified) is not bool:
            raise ValueError("operator_custody_verified must be an explicit boolean")
        if read_enabled and verifier is None:
            raise ValueError("read scope requires an explicit HMAC verifier")
        self._verifier = verifier
        self._admin_principals = admin_principals
        self._operator_custody_verified = operator_custody_verified
        self._read_enabled = read_enabled

    @property
    def enabled(self) -> bool:
        return self._verifier is not None

    @property
    def read_enabled(self) -> bool:
        """Whether the separate, exact GET read-scope prototype is enabled."""
        return self._read_enabled

    def authenticate_post(self, request_target: str, headers,
                          raw_body: bytes) -> AuthenticatedRequest | None:
        """Authenticate exact dispatch path before JSON parsing.

        Disabled means the caller preserves legacy behavior. When enabled,
        any query, fragment, trailing slash, alias, duplicate auth header, or
        unknown path is rejected; the exact signed target must be the route
        key that dispatch will use. AuthError must be returned as an error,
        never treated as transport failure or permission to use a fallback.
        """
        if not self.enabled:
            return None

        try:
            parsed = urlsplit(request_target)
        except ValueError:
            raise AuthError(400, "invalid_path") from None
        route = parsed.path
        if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
                or route not in POST_ROUTE_POLICY or request_target != route):
            raise AuthError(404, "unknown_or_noncanonical_route")

        values: dict[str, str] = {}
        for field, header in _AUTH_HEADERS.items():
            found = headers.get_all(header, [])
            if len(found) != 1 or not found[0].strip():
                raise AuthError(401, "missing_or_duplicate_auth_header")
            values[field] = found[0].strip()

        assert self._verifier is not None
        principal = self._verifier.verify_request(
            method="POST", path=route, audience=values["audience"],
            body=raw_body, timestamp=values["timestamp"],
            nonce=values["nonce"], key_id=values["key_id"],
            principal_id=values["principal_id"], signature=values["signature"],
        )
        return AuthenticatedRequest(route=route, principal=principal)

    def authenticate_get(self, request_target: str, headers,
                         raw_body: bytes) -> AuthenticatedRequest | None:
        """Authenticate an exact snapshot GET with an empty signed body.

        The read gate is opt-in independently of POST. Disabled means the
        caller may retain its existing behavior. When enabled, only exact
        ``/api/veri`` or ``/veri`` targets are accepted; each has its own
        ``GET <path>`` HMAC scope. This method does not authorize HTML/browser
        requests and is not wired into ``server.py``.
        """
        if not self.read_enabled:
            return None

        if not isinstance(raw_body, bytes) or raw_body:
            raise AuthError(400, "get_body_not_supported")

        try:
            parsed = urlsplit(request_target)
        except (TypeError, ValueError):
            raise AuthError(400, "invalid_path") from None
        route = parsed.path
        if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
                or route not in GET_ROUTE_POLICY or request_target != route):
            raise AuthError(404, "unknown_or_noncanonical_route")

        values: dict[str, str] = {}
        for field, header in _AUTH_HEADERS.items():
            found = headers.get_all(header, [])
            if len(found) != 1 or not found[0].strip():
                raise AuthError(401, "missing_or_duplicate_auth_header")
            values[field] = found[0].strip()

        # read_enabled can only be constructed with an explicit verifier.
        assert self._verifier is not None
        principal = self._verifier.verify_request(
            method="GET", path=route, audience=values["audience"], body=raw_body,
            timestamp=values["timestamp"], nonce=values["nonce"],
            key_id=values["key_id"], principal_id=values["principal_id"],
            signature=values["signature"],
        )
        return AuthenticatedRequest(route=route, principal=principal)

    def authorize_get(self, authn: AuthenticatedRequest | None) -> str | None:
        """Confirm the verified principal has the exact configured GET scope.

        Returns ``read_snapshot`` when enabled and authorized. A disabled gate
        returns ``None`` for legacy behavior; callers must not interpret that
        as an authenticated request. This prototype does not dispatch routes.
        """
        if not self.read_enabled:
            return None
        if authn is None:
            raise AuthError(401, "authentication_required")
        policy = GET_ROUTE_POLICY.get(authn.route)
        if policy != "read_snapshot" or authn.principal.scope != f"GET {authn.route}":
            raise AuthError(403, "route_scope_required")
        return policy

    def authorize_payload(self, authn: AuthenticatedRequest | None,
                          payload: Mapping[str, object]) -> str | None:
        """Apply principal/body binding after parse and before route dispatch.

        Returns the trusted actor for ``/api/yaz``. The integration must pass
        it separately to the message writer; copying it into a client field
        and trusting that field is not equivalent.
        """
        if not self.enabled:
            return None
        if authn is None:
            raise AuthError(401, "authentication_required")
        policy = POST_ROUTE_POLICY.get(authn.route)
        if policy is None or authn.principal.scope != f"POST {authn.route}":
            raise AuthError(403, "route_scope_required")
        principal_id = authn.principal.principal_id
        if policy == "closed":
            raise AuthError(403, "route_closed")
        if policy == "task_operation":
            operation = payload.get("islem")
            task_policy = {
                "ekle": "task_admin", "ata": "task_admin",
                "iptal": "task_admin", "al": "task_worker",
                "sonraki": "task_worker", "teslim": "task_worker",
                "ilk-kontrol": "task_reviewer",
                "denetle": "task_reviewer",
            }.get(operation)
            if task_policy is None:
                raise AuthError(403, "task_operation_forbidden")
            if task_policy == "task_admin" and principal_id not in self._admin_principals:
                raise AuthError(403, "admin_required")
            return task_policy
        if policy == "admin":
            if principal_id not in self._admin_principals:
                raise AuthError(403, "admin_required")
        elif policy == "self_or_admin":
            target = payload.get("kimlik")
            if target != principal_id and principal_id not in self._admin_principals:
                raise AuthError(403, "self_or_admin_required")
        elif policy == "self":
            if payload.get("kimlik") != principal_id:
                raise AuthError(403, "principal_binding_required")
            if (authn.route == "/api/katil"
                    and principal_id not in self._admin_principals
                    and payload.get("rol") not in (None, "isci")):
                # api_katil also writes a role. Self-binding alone must not
                # turn a valid identity credential into a role-assignment key.
                raise AuthError(403, "admin_required_for_role_assignment")
        elif policy == "principal_actor":
            return message_source_class(
                principal=authn.principal,
                admin_principals=self._admin_principals,
                operator_custody_verified=self._operator_custody_verified,
            )[0]
        else:
            raise AuthError(403, "route_policy_invalid")
        return None


def message_source_class(*, principal: VerifiedPrincipal | None,
                         admin_principals: frozenset[str],
                         operator_custody_verified: bool = False
                         ) -> tuple[str, str]:
    """Return the only trusted message source classification decision.

    Caller/body identity claims are intentionally not inputs. A verified HMAC
    principal outside the operator allowlist is an agent. An allowlisted
    principal is an operator only when a separate, operator-controlled custody
    boundary is explicitly verified; its absence fails closed to unknown.
    """
    if (not isinstance(principal, VerifiedPrincipal)
            or principal.scope != "POST /api/yaz"
            or type(operator_custody_verified) is not bool):
        return "unknown", "unverified"
    if principal.principal_id in admin_principals:
        if operator_custody_verified:
            return "operator", "verified"
        return "unknown", "unverified"
    return "agent", "verified"
