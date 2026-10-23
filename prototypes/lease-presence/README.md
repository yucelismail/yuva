# Lease and presence binding sketch (#556)

`decision.py` is a pure decision prototype. It receives detached lease,
heartbeat and renewal evidence and returns a recommendation. It has no Yuva
store, heartbeat sender, lease writer, wall-clock read, process probe, or
automatic task requeue.

## Contract

- `online` is possible only for an authenticated, fresh heartbeat bound to the
  exact lease owner principal, process instance, generation, broker clock
  epoch and a sequence newer than the last accepted lease sequence.
- Missing, old, future-dated, replayed, unverified, conflicting or
  generation-mismatched heartbeat is `unknown`. Absence never produces
  `offline`; the prototype has no offline evidence source.
- Heartbeat presence alone returns `hold`. A separate explicit renewal request
  must match the task, lease ID, owner, instance, generation, fencing token and
  heartbeat sequence to yield `renew_cas_candidate`.
- That candidate is not a commit. A single authoritative lease writer must
  compare-and-swap the current lease/fencing token and persist the extension
  before reporting a renewal. No process may extend a lease from a heartbeat
  that merely says it is alive.
- Unknown presence before lease expiry keeps the current lease reserved and
  unrenewed. At/after expiry, the decision is `reconcile_required`; it never
  reassigns/reclaims the task. A late owner or competing writer requires
  fencing at every task mutation boundary.
- Broker restart/boot epoch change invalidates old heartbeat evidence. Use a
  monotonic clock scoped to a broker boot epoch, not an agent wall-clock
  timestamp. Clock, epoch or lease conflicts fail closed.
- `authenticated`, the epoch and clock values are inputs in this sketch, not
  verified here. Same-UID `--from`, a PID, unit state or a client-written
  boolean is not sufficient authentication or process isolation.

## Failure fixtures to carry into implementation tests

| Fixture | Presence | Lease action | Safety property |
| --- | --- | --- | --- |
| Fresh signed heartbeat, matching instance/generation, no renew request | online | hold | Presence does not silently extend ownership. |
| Fresh matching heartbeat plus explicit request and matching fence | online | renew CAS candidate | Store must still win a single-writer CAS before extension. |
| Missing/legacy/unverified heartbeat, lease not expired | unknown | hold | No false online/offline and no reclaim. |
| Old heartbeat beyond TTL, lease not expired | unknown | hold | Staleness does not release the task. |
| Network partition; lease deadline passes | unknown | reconcile required | Expiry is not proof that owner stopped; no automatic reassignment. |
| Agent suspended past deadline, then resumes with old generation | unknown or stale | reconcile required | Old process cannot commit after a new fence; no blind late delivery. |
| Two same-UID processes claim the same worker label | unknown unless a broker binds distinct verified instances | reconcile required on lease conflict | `--from`/PID labels do not elect an owner. |
| Replay, sequence rollback, generation mismatch or broker reboot epoch mismatch | unknown | hold/reconcile by expiry | Old evidence cannot renew a current lease. |
| Two active lease records for one task | unknown | reconcile required | No “newest heartbeat wins” rule. |
| Lease expired with no fencing-capable task writer | unknown/online may remain process-level only | reconcile required | Do not requeue until old writer is fenced or human recovery is approved. |

The contract is complementary to the task lifecycle design in #555. The
prototype does not choose task states, persist lease records, coordinate
multiple writers, or make recovery decisions for an operator.

## Isolated claim writer (#570)

`writer.py` is a fixture-only writer prototype. It takes an explicit store
directory and updates only its `gorevler.json`; it is not imported by the CLI
or panel and has no production adapter. It requires a fixture marker file
before it can create a lock or touch a ledger. Tests pass temporary directories.

- The read/modify/write runs under the task ledger's `.kilit` file and replaces
  the complete JSON snapshot atomically, followed by file and directory fsync.
- One task record receives `execution` and the matching `assignee`/`assigned`
  transition in that same snapshot. `execution.owner_claim` is always paired
  with `owner_trust="unverified"`; it is a caller label, not proof of identity.
- A successful new claim increments `lease_epoch`; a repeated stable
  `operation_id` returns the same lease without incrementing it again.
- `pending_revision` is claimable only by its recorded assignee. Active,
  expired-suspect, unknown, or otherwise unreconciled execution records block
  another claim. Only `closed` or `revoked` records permit a later claim.
- Presence, display name, role, and heartbeat are not writer inputs and cannot
  establish ownership. This prototype does not implement expiry, renewal,
  autonomous reassignment, or live Yuva integration.
- `complete_task` compares the submitted epoch and owner with the current
  active execution while holding the same ledger lock. A stale epoch appends a
  separate `lease-attempts.jsonl` audit record and leaves the task snapshot,
  status, and history byte-for-byte unchanged. A matching current epoch closes
  the lease and moves the task to `pending_verification` atomically.
- The stale-completion fixture models expiry after explicit reconciliation by
  closing epoch N and making the task claimable; it does not claim to implement
  wall-clock expiry or production recovery policy.

`tests/test_lease_writer.py` and `tests/test_lease_completion.py` cover epoch
monotonicity, idempotent same-operation retry, one-winner concurrent claims,
unreconciled lease rejection, atomic replace failure, stale completion fencing,
separate rejection audit, and current-epoch completion against temporary
fixture stores only.
