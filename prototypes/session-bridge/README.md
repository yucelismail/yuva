# Isolated session bridge sketches

These files are design prototypes only. They do not connect to Codex,
OpenCode, Yuva, JSONL, a terminal, or a live task store. No transport callback
is provided by this package.

## `outbox.py`

`EventOutbox` is an in-memory sketch for a stable event-ID outbox. Its API is:

- `enqueue(event_id, payload)` stores a canonical JSON payload once. Reusing the
  same ID and same payload returns the existing receipt; different content
  raises `IdempotencyConflict` without changing state.
- `dispatch(event_id, send)` invokes the caller-provided transport only for a
  `pending` record. The callback receives `(event_id, detached_payload)` and
  must return `SendObservation` with an explicit outcome.
- `retry_not_sent(event_id, send)` permits another call only after the prior
  callback explicitly returned `not_sent_proven`. An exception, timeout,
  malformed callback result, partial write, or lost response becomes `unknown`
  and does not permit another send.
- `record_reconciliation(event_id, outcome, external_receipt)` records a
  read-only result. Only explicit `delivered` or `rejected` evidence resolves
  the state. `not_found` remains `unknown`: an index may be stale or a request
  may still be in flight.
- `get(event_id)` returns an immutable, detached `Receipt`; `payload()` returns
  a fresh payload copy.

The state vocabulary is `pending`, `sending`, `accepted`, `delivered`,
`not_sent_proven`, `unknown`, and `rejected`. `accepted` is not `delivered`.
An explicit delivery result is evidence supplied by the transport/reconciler;
this sketch cannot verify that evidence itself.

## Bounds and assumptions

The constructor bounds record count, each canonical payload, aggregate
payload bytes, and each serialized external receipt. Nothing is evicted to
make room: capacity exhaustion raises `CapacityExceeded` before recording or
sending the new event. Event IDs remain as in-memory dedupe tombstones for the
life of the instance. Payloads must be JSON values with string object keys and
finite numbers.

`event_id` is a stable idempotency key, not authentication or authorization.
The destination must itself deduplicate by this ID for duplicate transport
attempts to be harmless. This prototype only suppresses duplicate local
enqueue/dispatch calls. The caller must persist its outbox record before any
external write in a real system.

This implementation is memory-only. Restart loses receipts and tombstones; it
provides no durability, exactly-once delivery, cross-process locking, scheduler,
retention, or Yuva task transition. A durable implementation must restore an
interrupted `sending` record as `unknown`, reconcile by stable event ID, and
never resend an unknown operation just because it is absent from one read.
Only separately proven zero-byte writes may be retried automatically. An
operator-approved new attempt is a distinct operation decision and can still
duplicate remote effects if the destination has no idempotency support.

## Open questions for a real adapter

- What is the receiver's durable dedupe window and event-ID namespace?
- Which API response or readback proves `accepted` versus `delivered`?
- Can reconciliation return an authoritative negative while an earlier send
  might still be processing?
- Who authorizes a new attempt after `unknown`, and how is that decision
  audited?
- What are the durable outbox transaction, fsync, backup, recovery, and
  tombstone-retention rules?

No tests or runtime checks were run for this sketch, as required by its task.

## `busy_state.py`

`BusyStateMachine` is a separate in-memory sketch for one logical session and
at most one unresolved task. It consumes observations supplied by a caller; it
does not bind a real session, dispatch work, query a provider, or answer an
approval. A `busy` occupancy after `prepare_dispatch` is a local reservation,
not evidence that the provider is busy. A task blocked by that reservation
stays with the caller/Yuva; this object has no queue.

### Transition table

| Event / method | Required state or evidence | Result |
|---|---|---|
| `begin_connect(generation)` | Disconnected or unbound; generation ID is fresh | `connecting`, occupancy `unknown`; clears prior idle evidence |
| `observe_bound(...)` | Current generation; identity and binding both verified; stable session ID | `bound`, occupancy `unknown`; reconnect never implies idle |
| `observe_idle(generation, evidence)` | Bound current generation; no active or unresolved task | Occupancy `idle` with fresh evidence |
| `prepare_dispatch(task, operation)` | Bound and idle with no active task | Reserves one task as `dispatch_ready`; occupancy becomes locally `busy`; returns `prepared_only` |
| `mark_write_started(...)` | Matching reserved task in `dispatch_ready` | `write_started`; occupancy `unknown` until the caller reports the write result |
| `observe_write_result(...)` | Matching task in `write_started` | Proven zero bytes → `not_sent_proven` / idle; full frame plus successful flush → `sent_observed` / busy; every ambiguous result → `unknown` |
| `retry_proven_not_sent(...)` | Same task and operation; zero bytes proven | Re-arms that operation as `dispatch_ready`; local occupancy becomes busy |
| `observe_accepted(...)` / `observe_running(...)` | Correlated task and operation plus evidence ID | `accepted` or `running`; occupancy busy |
| `observe_approval_request(...)` | Correlated active operation and observed approval ID | `approval_pending`; decision is still pending; occupancy busy |
| `observe_approval_response(...)` | Same approval ID and observed `approved` or `denied` response | `approval_resolved_waiting`; still busy until a later task observation |
| `observe_terminal(..., receipt_durable=False)` | Correlated known terminal outcome and evidence | `terminal_observed`; occupancy unknown; reservation is retained |
| `observe_terminal(..., receipt_durable=True)` | Correlated terminal outcome and durable receipt asserted by caller | `terminal_durable`; releases local task slot and records idle evidence |
| `disconnect(...)` | Current generation | Connection disconnected; unresolved work becomes unknown (pending approval becomes `approval_pending_unknown`) |
| `begin_connect(new_generation)` + `observe_bound(...)` | Fresh generation; caller externally verifies identity and same session binding | Bound but still unknown; unresolved task remains reserved for reconciliation |
| `reconcile(...)` | Fresh bound generation and a retained unresolved task | Read-only running evidence keeps busy; durable terminal evidence releases slot; inconclusive/not-found stays unknown |

### Assumptions and limits

- Evidence IDs and booleans are caller assertions. The prototype cannot
  authenticate, validate freshness, or prove that a receipt is durable.
- A generation ID is unique only within this object instance. The caller must
  create a fresh one for each reconnect and correlate every event to the same
  task and operation IDs.
- A zero-byte retry is safe only if the transport caller can prove no bytes
  were sent. Partial writes, lost responses, failed flushes, and absent lookup
  results remain unknown and must not be automatically resent.
- Approval requests are observations, not authorization. The state machine
  never chooses or sends an approval decision; observing a response does not
  prove the task resumed.
- Only a durable terminal receipt releases the local slot. This is a modeled
  caller-provided claim, not a durability guarantee. Yuva task delivery and
  review are outside this prototype.
- All state is volatile and process-local. Restart loses generations, task
  history, and reservations; no provider integration, persistence, concurrency
  control, or production safety claim is included.
- No tests or runtime checks were run for this sketch, as required by its task.

## `trust_policy.py`

`classify_origin()` is a pure source-label sketch. It separates direct user
requests, externally verified operator context, a verified canonical Yuva task,
Yuva chat, worker messages, tool output, and unknown input. It accepts no body
text, so quoted claims such as “the user approved this” cannot change a
worker/tool classification. Worker, tool, and chat content are always
data-only; they cannot supply instructions or authorize external actions.

Operator verification remains a caller assertion. Canonical task
classification has a stricter shape: the caller must supply a positive
canonical numeric Yuva task ID and `TaskBindingEvidence` that explicitly says
the task record lookup, session binding, workspace binding, and assignee
binding were verified. The lookup task ID must match the source task ID.
Successful `TASK_SCOPE` results carry a `VerifiedTaskBinding` with all four
IDs. Consumers may use task-scoped instructions only while retaining that
binding; if it is dropped or no longer matches the active session/workspace/
assignee, the context must be classified again and treated as data-only or
unknown. Missing or invalid task context is data-only here.

These booleans and IDs are still caller assertions, not cryptographic proof.
This module does not authenticate them, perform the task-record lookup, check
a user's approval of an exact action, or enforce policy. Even a user request,
verified operator, or task classification does not itself grant external-
action authority here; a separate outer policy must check the exact action,
target, scope, and approval evidence. No Yuva CLI/panel or provider is
connected. No tests or runtime checks were run for this sketch, as required by
its task.
