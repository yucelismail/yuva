# Yuva #612 — Task receipt/outbox fixture with ledger v1 compatibility gate

The isolated `prototypes/task-outbox` prototype now uses the same task-root
shape as `gorevler.json` v1: optional `schema_version` (missing means legacy
v1), `siradaki`, `gorevler[]`, integer task IDs, `durum`, and `gecmis[]`.
Operation receipts and pending outbox entries are additive top-level
`operations` and `outbox` fields. Unknown fields are preserved. The fixture
does not import or call the canonical CLI/panel and does not touch a live
ledger.

## Fixture boundaries exercised

- **Compatibility:** schema-less legacy v1 is accepted and stamped as v1 only
  on a successful write. A v2/unknown root version is rejected without
  changing the original ledger bytes. Invalid task roots and task IDs fail
  closed.
- **One locked snapshot:** the task status/history transition, operation
  receipt and outbox record are assembled in one in-memory v1 ledger and
  atomically replaced while the shared fixture `.kilit` is held. Concurrent
  duplicate requests yield one transition/history row/receipt/outbox event.
- **Duplicate operation:** same ID and same request returns the stored receipt;
  same ID with a different request conflicts without another write.
- **`commit_unknown`:** injected directory `fsync` uncertainty after
  `os.replace` leaves a complete visible snapshot. Reopening and looking up the
  same operation ID finds the receipt and confirms task/history/outbox were
  committed together. No notification is emitted by the mutation call.
- **Event readback:** a crash after message append is recovered by full JSONL
  readback and does not append a second line. Append `fsync` uncertainty can be
  resolved only by finding the exact event. Incomplete tails, conflicting
  event content, and duplicate event IDs remain `delivery_unknown`; retries
  append nothing.

Run only the standalone fixture:

```sh
python3 prototypes/task-outbox/run_fixture.py
```

Each case owns a child directory of one temporary root and uses only that
fixture's `YUVA_DIR`. The output omits fixture paths and data. This validates
the modeled v1 compatibility and recovery contract; it is not canonical
writer/API acceptance, filesystem power-loss proof, or permission to enable a
live outbox worker.
