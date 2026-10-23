# Yuva #661 — Nested outbox schema and bounds fixture

## Scope

Added an isolated nested-schema validator at
`prototypes/task-outbox/outbox_schema.py` and connected it to the existing
temporary-ledger prototype. Validation runs when a fixture ledger is read and
again before any fixture snapshot replacement. A violation raises
`LedgerCompatibilityError` before the snapshot is changed.

## Fixture contract

- `operations` is an object with at most 256 entries; `outbox` is a list with
  at most 256 events.
- Each canonical JSON receipt or event is limited to 4096 UTF-8 bytes.
- IDs are non-empty printable strings up to 128 UTF-8 bytes; notification
  bodies are strings up to 2048 UTF-8 bytes.
- Receipt fields and event fields are required and exact. Receipt operation
  and event kind are `task.status`; receipt status is `committed`; notification
  and delivery state are `pending`, `delivered`, or `delivery_unknown`.
- Task IDs must be positive integers (`bool` is rejected). SHA-256 request
  digests must be lowercase 64-character hex.
- Duplicate JSON object keys, event IDs, transition event IDs, or multiple
  events for one operation are rejected. Receipt/event IDs, task IDs, and
  delivery states must agree one-to-one.
- Unknown root extensions remain opaque and preserved. Unknown nested receipt,
  event, or result fields fail closed. Reaching a cap blocks writes; nothing is
  automatically evicted. Retention/cleanup remains undecided.

The limits are explicit prototype values, not production sizing advice. There
is no production writer support, schema migration, live-ledger access, worker,
or canonical CLI/panel change in this task.

## Verification

- `python3 -m unittest tests.test_task_outbox_nested_schema_fixture -v` — 6
  focused tests passed for acceptance, count/byte caps, duplicate IDs/keys,
  unknown nested fields, type rejection, and unchanged bytes after rejected
  mutation.
- `python3 prototypes/task-outbox/run_fixture.py` — all 7 existing crash,
  duplicate-operation, schema compatibility, and delivery-readback scenarios
  passed.
