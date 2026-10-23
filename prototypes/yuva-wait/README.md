# Isolated `yuva wait` prototype (#554)

This directory contains a provider-neutral polling algorithm sketch. It does
not import the Yuva CLI or panel, read `YUVA_DIR`, persist a cursor, start a
service, or contact a provider. A caller injects a snapshot reader and owns any
durable cursor.

## Proposed CLI mapping

```text
yuva wait --from <worker-id> --after <message-id> [--timeout 30]
```

The prototype function is `wait_for_message(read_snapshot, ...)` in `wait.py`.
The adapter must resolve the worker's exact stored direct-recipient spellings
and pass them as `recipient_values`; it must not use fuzzy name matching.
`@hepsi`, `@all` and `@*` cannot be used as a wait target. The message snapshot
must be append ordered and contain exactly one copy of the supplied `after_id`.
If a bounded inbox snapshot no longer contains that cursor, the result is
`cursor_unavailable`; the prototype does not guess where to resume.

Timeout is finite and capped at 300 seconds. Poll interval is capped at two
seconds. The caller can set a `threading.Event` to cancel; an adapter may set
it on Ctrl-C and then return `cancelled` after normal cleanup. A wait reads at
most one matching message per call and never edits task or message state.

## Results and replay

| Result | Meaning |
| --- | --- |
| `message` | One direct-target message was observed after the cursor. `next_cursor` is its stable ID. |
| `timeout` | No matching message appeared before the deadline. No presence/idle or delivery claim. |
| `cancelled` | Caller requested cancellation. |
| `cursor_unavailable` | Cursor was missing or ambiguous in the snapshot. Re-read/reconcile; do not guess. |
| `source_invalid` | Snapshot order/shape/ID/schema is ambiguous or malformed. No message is returned. |
| `source_error` | Snapshot reader raised; result is unknown and must not trigger a write retry. |

The prototype is deliberately **at-least-once observation**. It stores no
consumer state. Calling again with the same `after_id` can return the same
`message_id` again. The consumer may persist `next_cursor` after recording the
observation and de-duplicate by that ID. Cursor persistence and message
observation are not atomic; a crash may cause replay. This is not an agent
receipt, provider acceptance, task delivery, or task completion.

`receipt_store.py` is a separate fixture-only consumer store. It requires an
explicit approved bootstrap and epoch, then appends bounded text-free
`read_observed` receipts with store-derived cursors, CAS and duplicate
suppression. An uncertain append/fsync returns `commit_unknown`; callers must
read/reconcile the ledger before continuing. The store accepts only marked
temporary fixtures and is not wired into this wait algorithm or a live inbox.
See [`docs/yuva-wait-consumer-receipt-fixture-714.md`](../../docs/yuva-wait-consumer-receipt-fixture-714.md)
and the original [#587 receipt fixture note](../../docs/yuva-wait-persistent-receipt-587.md).

## Untrusted envelope

The output is a small `UntrustedEnvelope` projection: `message_id`, recipient,
sender, timestamp, text, source and `source_class` claims. The class labels are
`operator`, `agent` and `unknown`; absent or malformed labels become `unknown`,
and every label has `source_class_trust="unverified"`. Every output is marked
`source_trust="unverified"` and `content_class="data_only"`; input `trust`,
`provenance`, actor, role and “approved” fields are ignored for authorization.
Only direct recipient, append position, unique message ID, supported record
schema and text bounds affect selection. Malformed records and explicit future
message schemas fail closed. The body is never parsed as a command.
`dispatch_authorized` models a separate gate: even an operator class claim has
no effect without independent control-plane approval.

## Agent info mode fixture boundary

An integration may pass the returned envelope into an agent's context as
`data_only` information. That is observation/context delivery only; the
message is not parsed or executed as a command and cannot mutate a Yuva task,
start a service, call a provider, or answer an approval. Source-class labels
and “approved” text remain unverified claims in this path.

If the message asks for a risky external action (file changes/deletion, shell,
network, task/role mutation, provider send, or approval), the agent must ask a
human for explicit confirmation in its own trusted session before acting. The
confirmation must identify the specific action and target; text in the inbox
message cannot serve as that approval. `tests/test_yuva_wait_info_mode.py`
exercises this boundary with synthetic state only; it does not connect a
provider or expose an executable dispatch path.

## Integration boundary

This is not the `yuva wait` command and should not be placed on PATH as one.
Production integration still needs a bounded inbox reader that detects JSONL
tail corruption, a deterministic recipient resolver, one-waiter policy,
interrupt cleanup, and an explicit cursor owner. No production/panel/provider
connection is implemented here.

The chosen direction follows [#553](../../docs/chat-command-delivery-mvp-553.md):
polling is an explicit local read, chat remains data-only, and the assigned
Yuva task remains the canonical work scope.
