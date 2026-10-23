"""Pure lease/presence decision sketch; no clock, store, or process I/O."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Lease:
    task_id: str
    lease_id: str
    owner_principal: str
    instance_id: str
    generation: str
    fencing_token: int
    clock_epoch: str
    expires_at_monotonic: float
    last_sequence: int


@dataclass(frozen=True)
class Heartbeat:
    principal: str | None
    instance_id: str | None
    generation: str | None
    clock_epoch: str | None
    sequence: int | None
    observed_at_monotonic: float | None
    authenticated: bool


@dataclass(frozen=True)
class RenewalRequest:
    task_id: str
    lease_id: str
    principal: str
    instance_id: str
    generation: str
    fencing_token: int
    sequence: int
    explicitly_requested: bool
    authenticated: bool


@dataclass(frozen=True)
class Decision:
    presence_state: str
    lease_action: str
    reason: str
    renewal_candidate: bool = False


def _finite_number(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def evaluate(
    lease: Lease,
    heartbeat: Heartbeat | None,
    renewal: RenewalRequest | None,
    *,
    now_monotonic: float,
    clock_epoch: str,
    heartbeat_ttl: float,
    active_lease_count: int = 1,
) -> Decision:
    """Recommend hold/CAS-renew/reconcile; never expire or reassign a task.

    Authentication booleans and clock/epoch values are caller-supplied claims
    in this sketch. A production broker must derive them from its verified
    principal, boot epoch, and monotonic clock before calling the reducer.
    """
    if (not _finite_number(now_monotonic) or not _finite_number(heartbeat_ttl)
            or heartbeat_ttl <= 0 or heartbeat_ttl > 300
            or not isinstance(clock_epoch, str) or not clock_epoch
            or not all(isinstance(value, str) and value for value in (
                lease.task_id, lease.lease_id, lease.owner_principal,
                lease.instance_id, lease.generation, lease.clock_epoch))
            or isinstance(lease.fencing_token, bool)
            or not isinstance(lease.fencing_token, int) or lease.fencing_token < 1
            or isinstance(lease.last_sequence, bool)
            or not isinstance(lease.last_sequence, int) or lease.last_sequence < 0
            or not _finite_number(lease.expires_at_monotonic)):
        return Decision("unknown", "reconcile_required", "invalid_lease_or_clock_evidence")
    if (isinstance(active_lease_count, bool)
            or not isinstance(active_lease_count, int) or active_lease_count != 1):
        return Decision("unknown", "reconcile_required", "lease_owner_conflict")

    lease_expired = now_monotonic >= lease.expires_at_monotonic
    hb_valid = (
        heartbeat is not None
        and heartbeat.authenticated is True
        and heartbeat.principal == lease.owner_principal
        and heartbeat.instance_id == lease.instance_id
        and heartbeat.generation == lease.generation
        and heartbeat.clock_epoch == clock_epoch == lease.clock_epoch
        and type(heartbeat.sequence) is int
        and heartbeat.sequence > lease.last_sequence
        and _finite_number(heartbeat.observed_at_monotonic)
        and 0 <= now_monotonic - heartbeat.observed_at_monotonic <= heartbeat_ttl
    )
    if not hb_valid:
        return Decision(
            "unknown",
            "reconcile_required" if lease_expired else "hold",
            "heartbeat_missing_stale_unbound_or_unverified",
        )

    # A live process observation is presence only. It never renews a task lease.
    if lease_expired:
        return Decision("online", "reconcile_required", "lease_expired_no_automatic_reclaim")
    if renewal is None:
        return Decision("online", "hold", "presence_does_not_renew_lease")

    renewal_matches = (
        renewal.authenticated is True
        and renewal.explicitly_requested is True
        and renewal.task_id == lease.task_id
        and renewal.lease_id == lease.lease_id
        and renewal.principal == lease.owner_principal
        and renewal.instance_id == lease.instance_id
        and renewal.generation == lease.generation
        and type(renewal.fencing_token) is int
        and renewal.fencing_token == lease.fencing_token
        and type(renewal.sequence) is int
        and renewal.sequence == heartbeat.sequence
    )
    if not renewal_matches:
        return Decision("online", "reconcile_required", "renewal_binding_or_fence_mismatch")
    return Decision("online", "renew_cas_candidate", "explicit_bound_renewal_pending_store_cas",
                    renewal_candidate=True)
