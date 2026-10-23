"""Feature-off model for projecting broker-backed panel presence.

This is a pure contract fixture. It performs no socket, auth-store, panel, or
clock I/O. The caller supplies synthetic evidence objects; production callers
must derive peer credentials and session verification out of band.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}\Z")


@dataclass(frozen=True)
class PeerEvidence:
    """Kernel SO_PEERCRED result, represented synthetically in this fixture."""

    pid: int
    uid: int
    gid: int
    source: str = "kernel_so_peercred"


@dataclass(frozen=True)
class PrincipalBinding:
    principal_id: str
    uid: int
    map_revision: str
    active: bool = True


@dataclass(frozen=True)
class SessionEvidence:
    """An authenticated, current, allowed session from a trusted adapter."""

    principal_id: str
    session_id: str
    peer_pid: int
    peer_uid: int
    map_revision: str
    broker_epoch: str
    scope: str
    authenticated: bool
    allowed: bool
    expires_at_monotonic: float


@dataclass(frozen=True)
class HeartbeatEvidence:
    session_id: str
    sequence: int
    observed_at_monotonic: float
    broker_epoch: str
    # This field models an untrusted body claim. It is never identity evidence.
    body_principal_claim: str | None = None


@dataclass(frozen=True)
class Projection:
    online: bool
    presence_state: str
    presence_verified: bool
    principal_id: str | None
    reason: str


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _finite(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _unknown(reason: str) -> Projection:
    return Projection(False, "unknown", False, None, reason)


def project_presence(
    peer: PeerEvidence | None,
    bindings: Mapping[int, PrincipalBinding],
    session: SessionEvidence | None,
    heartbeat: HeartbeatEvidence | None,
    *,
    now_monotonic: float,
    current_map_revision: str,
    current_broker_epoch: str,
    heartbeat_ttl: float = 60,
    feature_enabled: bool = False,
) -> Projection:
    """Return verified online only for matching current peer/session evidence.

    Every failure is `unknown`; the fixture has no evidence that can establish
    offline. `bindings`, `peer`, and `session` are trusted-boundary inputs in a
    future integration, not values that should be accepted from HTTP/body data.
    """
    if feature_enabled is not True:
        return _unknown("feature_off")
    if (not _finite(now_monotonic) or not _finite(heartbeat_ttl)
            or heartbeat_ttl <= 0 or heartbeat_ttl > 300
            or not _valid_id(current_map_revision)
            or not _valid_id(current_broker_epoch)):
        return _unknown("invalid_clock_or_current_revision")
    if not isinstance(bindings, Mapping) or not bindings:
        return _unknown("principal_map_missing")
    normalized: dict[int, PrincipalBinding] = {}
    seen: set[str] = set()
    for uid, binding in bindings.items():
        if (type(uid) is not int or uid < 0
                or not isinstance(binding, PrincipalBinding)
                or binding.uid != uid or not _valid_id(binding.principal_id)
                or not _valid_id(binding.map_revision)
                or binding.principal_id in seen):
            return _unknown("principal_map_invalid_or_ambiguous")
        normalized[uid] = binding
        seen.add(binding.principal_id)
    if (not isinstance(peer, PeerEvidence) or peer.source != "kernel_so_peercred"
            or type(peer.pid) is not int or peer.pid <= 0
            or type(peer.uid) is not int or peer.uid < 0
            or type(peer.gid) is not int or peer.gid < 0):
        return _unknown("peer_credentials_missing_or_untrusted")
    binding = normalized.get(peer.uid)
    if (binding is None or binding.active is not True
            or binding.map_revision != current_map_revision):
        return _unknown("peer_principal_unmapped_stale_or_inactive")
    if not isinstance(session, SessionEvidence):
        return _unknown("session_evidence_missing")
    if (session.authenticated is not True or session.allowed is not True
            or session.scope != "presence:read"
            or session.principal_id != binding.principal_id
            or session.peer_pid != peer.pid or session.peer_uid != peer.uid
            or session.map_revision != current_map_revision
            or session.broker_epoch != current_broker_epoch
            or not _valid_id(session.session_id)
            or not _finite(session.expires_at_monotonic)
            or now_monotonic >= session.expires_at_monotonic):
        return _unknown("session_unverified_disallowed_stale_or_unbound")
    if not isinstance(heartbeat, HeartbeatEvidence):
        return _unknown("heartbeat_missing")
    if (heartbeat.session_id != session.session_id
            or heartbeat.broker_epoch != current_broker_epoch
            or type(heartbeat.sequence) is not int or heartbeat.sequence < 1
            or not _finite(heartbeat.observed_at_monotonic)
            or not 0 <= now_monotonic - heartbeat.observed_at_monotonic <= heartbeat_ttl):
        return _unknown("heartbeat_stale_or_unbound")
    # Body claims cannot select identity. Reject a conflicting claim to make
    # spoof attempts visible, but matching text never adds trust.
    if (heartbeat.body_principal_claim is not None
            and heartbeat.body_principal_claim != binding.principal_id):
        return _unknown("body_principal_claim_conflicts")
    return Projection(True, "online", True, binding.principal_id,
                      "peer_and_allowed_current_session_verified")
