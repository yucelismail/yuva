"""Linux UDS peer-credential gate used by the isolated #615 fixture.

This helper is a contract prototype, not a running signer or broker service.
It derives the connecting process identity only from SO_PEERCRED.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
import socket
import struct
import sys


_PRINCIPAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}\Z")


@dataclass(frozen=True)
class PeerCredentials:
    pid: int
    uid: int
    gid: int


@dataclass(frozen=True)
class PeerAuthorization:
    accepted: bool
    principal_id: str | None
    reason: str
    credentials: PeerCredentials | None = None


class PeerCredentialError(ValueError):
    pass


def read_peer_credentials(peer: socket.socket) -> PeerCredentials:
    """Read the kernel-reported credentials of a connected Linux AF_UNIX peer."""
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise PeerCredentialError("peer_credentials_unavailable")
    if not isinstance(peer, socket.socket) or peer.family != socket.AF_UNIX:
        raise PeerCredentialError("peer_socket_invalid")
    try:
        if peer.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM:
            raise PeerCredentialError("peer_socket_invalid")
        raw = peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("=iII"))
    except OSError:
        raise PeerCredentialError("peer_credentials_unavailable") from None
    if not isinstance(raw, bytes) or len(raw) != struct.calcsize("=iII"):
        raise PeerCredentialError("peer_credentials_malformed")
    pid, uid, gid = struct.unpack("=iII", raw)
    if pid <= 0:
        raise PeerCredentialError("peer_credentials_malformed")
    return PeerCredentials(pid=pid, uid=uid, gid=gid)


def _validate_uid_map(uid_to_principal: object) -> dict[int, str] | None:
    if not isinstance(uid_to_principal, Mapping) or not uid_to_principal:
        return None
    normalized: dict[int, str] = {}
    seen_principals: set[str] = set()
    try:
        for uid, principal in uid_to_principal.items():
            if (type(uid) is not int or uid < 0
                    or not isinstance(principal, str)
                    or not _PRINCIPAL_ID.fullmatch(principal)
                    or principal in seen_principals):
                return None
            normalized[uid] = principal
            seen_principals.add(principal)
    except Exception:
        return None
    return normalized


def authorize_socket_peer(peer: socket.socket, uid_to_principal: object) -> PeerAuthorization:
    """Fail closed unless the kernel UID has one exact enabled map entry."""
    mapping = _validate_uid_map(uid_to_principal)
    if mapping is None:
        return PeerAuthorization(False, None, "uid_mapping_invalid")
    try:
        credentials = read_peer_credentials(peer)
    except PeerCredentialError as error:
        return PeerAuthorization(False, None, str(error))
    principal = mapping.get(credentials.uid)
    if principal is None:
        return PeerAuthorization(False, None, "peer_uid_not_allowlisted", credentials)
    return PeerAuthorization(True, principal, "peer_uid_allowlisted", credentials)
