# Codex app-server JSON-RPC adapter sketch

This is a stdlib-only, isolated observer prototype based on the local app-server
v2 schema inspected for Yuva task #391. It reads newline-delimited JSON-RPC
messages supplied on stdin and emits a small JSONL event projection on stdout.
It never starts or connects to Codex, sends a request, answers a server request,
imports Yuva modules, or writes Yuva task/run/artifact state.

`JsonRpcAdapter.track_outbound_request()` records a request ID and optional
local context before a future caller sends a request. The JSONL reader also
recognizes the schema-confirmed client methods `initialize`, `thread/start`,
`thread/resume`, `turn/start`, `turn/steer`, and `turn/interrupt` in a captured
bidirectional trace. Matching responses are correlated by JSON-RPC ID. Thread,
turn, item, and server request IDs are retained as in-memory links. Context is
observational metadata and every projected event is marked
`observed_unverified` where applicable.

Approval and interaction server requests are retained in `pending()` with their
request, thread, turn, and item IDs. `serverRequest/resolved` only clears the
pending entry and records the decision as unknown. The adapter deliberately
has no response-writing API, so it cannot auto-approve. A completed Codex turn
is emitted as an observed protocol status and is never persisted as a Yuva
verified task state or delivery receipt.

The projection is intentionally partial. Unknown methods remain unknown,
state is memory-only, and it provides no reconnect, durability, authentication,
artifact storage, or exactly-once guarantee. The prototype was not executed for
task #396, as required.

## Retry and approval sketch

`retry_approval.py` is a second, pure in-memory sketch. A caller can stage a
`turn/start` operation under a stable local `operation_id` (for Yuva, a future
implementation could use the persisted message ID) and a JSON-RPC `request_id`.
An identical repeat is suppressed; changed method/params or a changed request
ID under the same operation ID raises `RetryConflict`. The first `prepare()`
result says `send_once`, but this module has no writer and sends nothing.

`record_write()` accepts an observed byte count. `retry()` permits another
attempt with the same ID only after the caller records exactly zero bytes
written. A complete write followed by a lost response, partial write, or
flush uncertainty is `unknown` and returns `reconcile_only`; it is never
automatically resent. A matching successful `turn/start` response records
`accepted`, a matching `turn/started` event records `running`, and a matching
completed event records its Codex terminal state. These are observations, not
Yuva task verification or authenticated receipts. JSON-RPC request IDs are not
remote idempotency keys. State is memory-only, so restart-safe retries require
a future durable outbox and reconciliation design.

Schema-listed approval requests are deduplicated by request ID and kept in
`pending_approvals()`. The prototype has no method that creates or sends an
approval response. `observe_approval_response()` can record a response that an
external caller already observed; `observe_request_resolved()` keeps the
decision unknown when the protocol notification omits it. A pending approval
stays pending through a connection loss, marked `disconnected` for review.
This file was not executed for task #402; no test was run.

## Reconnect and reused-ID sketch

`reconnect_state.py` models logical connection generations in memory. The caller
supplies a fresh `connection_id` for each generation and explicitly reports
observed outbound requests, responses, approval requests, and approval
responses. It opens no connection and writes no JSON-RPC frame. A disconnect
moves requests with unresolved outcomes to `unknown` and pending approvals to
`pending_unknown`. A matching response is correlated only within the exact
connection generation.

If an unresolved request ID appears again after reconnect, `register_outbound()`
returns `reconcile_only`; the JSON-RPC ID is not treated as a remote idempotency
key and no second turn is created. An approval ID reused across generations
with an unresolved earlier approval is retained as `pending_unknown`. The
in-memory snapshot/restore sketch also fails unresolved work closed, but does
not write or read files and gives no durability or exactly-once guarantee.
There is no network reconnect, turn start, approval response writer, Yuva import,
or Yuva verified-state update. This prototype was not executed for task #404;
no test was run.
