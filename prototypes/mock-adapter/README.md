# Mock model adapter contract

This isolated prototype turns Yuva design task #281 into a fake-only interface
example. It does not import Yuva code, make network requests, start a process,
write to a terminal, alter a real conversation, or resolve approvals.

## Run

From the repository root:

```bash
python3 -B prototypes/mock-adapter/adapter.py --self-check
```

`attach_or_start()` maps one Yuva identity to one explicitly scoped `mock-`
session and working directory, and rejects a session ID already mapped to a
different identity. `submit()` uses `(session_id, message_id)` as an idempotency
key. An identical retry in one adapter returns its existing delivery; changed
content under that key raises `ContractError`. Multiple adapters may share one
`MockTransport`: when they submit the same session, message ID, and text, the
transport returns its original acceptance receipt and each adapter records a
local `accepted` delivery. Reusing that key with different text still raises
`ContractError` before the second adapter records local delivery state. Fake
transport admission advances state only to `accepted`. Fake lifecycle calls
expose `running`, `waiting_approval`, `completed`, and `failed` transitions.

Every operation that reads or changes a delivery takes both
`yuva_identity` and `session_id`; a mismatch is rejected before lookup or state
change. `Session` and `Delivery` values returned by the adapter are frozen
dataclasses. `read_status()` and `reconcile()` return detached dictionaries,
so changing the caller’s copy cannot mutate adapter state or logged events.

`reconcile(identity, session_id, after_seq)` returns the mapped session, current
deliveries, JSON-compatible events for only that identity/session after an
exclusive cursor, and the next global cursor. Both event and delivery lists are
scoped to the same identity/session pair. A real adapter would reconnect to
its tool and use this contract to reconcile durable history. This prototype
keeps state in memory, so a process restart loses it; it demonstrates the
reconciliation shape, not durable recovery or exactly-once delivery.
`after_seq` must be an actual non-negative Python integer (`bool`, floats,
including NaN and integral-valued floats, are rejected). It is a global
exclusive event cursor: a cursor equal to the latest sequence returns no
events and the same cursor; a cursor ahead of the latest sequence is rejected
with `ContractError`.

State scope: `queued` is emitted as a transient event during synchronous fake
submission and immediately advances to `accepted`; there is no persistent
queue worker in this prototype. `waiting_approval` is observable and remains
pending, but approval, resume, and continuation after approval are out of
scope. It can only become `failed` here. `completed` and `failed` are terminal.
The implemented transitions are `queued → accepted|failed`,
`accepted → running|waiting_approval|failed`,
`running → waiting_approval|completed|failed`, and
`waiting_approval → failed`.

Approval is observe-only: `waiting_approval` is exposed, but there is no
approval/permission-grant method. A real Yuva surface would forward the request
to the user or owning TUI.

## Limitations

- The transport stores messages in a Python dictionary; no Codex, OpenCode,
  Claude, TUI, panel, or Yuva endpoint is contacted.
- There is no persistence, event streaming, authentication, scheduler, queue
  worker, cancellation, or concurrent-writer protection.
- `accepted` means only fake transport admission, never agent receipt.
- Event payloads are a proposal for the adapter boundary, not a stable Yuva API.
- `ownership` is descriptive metadata; the prototype does not discover or
  attach to existing sessions.

## Check performed

`--self-check` exercises identity/session binding, duplicate delivery,
idempotency conflict, status progression into `waiting_approval`, isolation
between two sessions, duplicate-session rejection, delivery/event isolation,
JSON serialization of reconciled events, wrong-owner reads/mutations, immutable
returned values, equal/ahead cursor behavior, and cursor reconciliation. It
uses only the fake in-memory transport.
