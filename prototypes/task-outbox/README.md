# Task outbox crash/restart fixture

An isolated executable prototype for the contract in `docs/task-notification-idempotency-575.md`.
It uses only a fresh temporary root with a separate child directory per
scenario, sets `YUVA_DIR` to that child, and has no imports from `bin/yuva` or
`panel/`. It never reads
or writes `/home/yucel-pc/yuva` or a canonical task store.

Fixture task snapshots use the current `gorevler.json` v1 root shape:
`schema_version`, `siradaki`, and `gorevler[]` with integer task IDs and
`gecmis[]`. `operations` and `outbox` are optional additive top-level fields;
the prototype preserves unrelated fields. A missing `schema_version` is
treated as legacy v1 and gets stamped on the first successful snapshot write.
Unknown schema versions or malformed v1 task records fail closed before a
snapshot replacement. This is a fixture compatibility gate, not a migration or
an integration with the canonical writer.

The nested `operations` / `outbox` contract is enforced by
`outbox_schema.py` before reads are accepted and before any snapshot replace:

| Limit / field | Fixture contract |
|---|---|
| Receipt count | At most 256 operation keys |
| Outbox count | At most 256 events |
| Canonical entry size | Each receipt and event at most 4096 UTF-8 bytes |
| Identifiers | Non-empty printable strings, at most 128 UTF-8 bytes |
| Notification body | String, at most 2048 UTF-8 bytes |
| Receipt fields | Exact field set for digest, operation, task ID, committed status, result, event IDs, and notification state |
| Event fields | Exact field set for event/operation/task IDs, kind, message, and delivery state |
| Uniqueness | Duplicate JSON keys, duplicate event IDs, or multiple events for one operation are rejected; receipt/event links must match one-to-one |
| Unknown fields | Unknown root extensions are preserved; unknown nested receipt/event/result fields fail closed |

The prototype does not evict receipts or events. Reaching a count/byte limit
rejects the next snapshot mutation before replacement; retention and cleanup
policy remain unresolved design decisions. These limits are fixture choices,
not production sizing recommendations.

Run the fixture with:

```sh
python3 prototypes/task-outbox/run_fixture.py
```

The fixture exercises four restart boundaries:

1. Two concurrent duplicate operation IDs with the same request return one
   receipt, task history entry, and outbox event; reuse with different request
   data conflicts.
2. A schema-less legacy v1 ledger is preserved and stamped on successful
   additive write; a future schema version is rejected byte-for-byte unchanged.
3. Injected directory-fsync failure after `os.replace` returns
   `CommitUnknown`; reopening and looking up the same operation ID reconciles
   the visible receipt without emitting its notification.
4. An abrupt simulated process stop after message append+fsync but before the
   outbox `delivered` update is recovered by scanning the JSONL event ID; restart
   marks it delivered without appending a second line.
5. An append/fsync error becomes `delivery_unknown`; restart may resolve it by
   finding the exact event, but it never appends again based only on absence.
6. A malformed/incomplete JSONL tail, a conflicting event body, or a duplicate
   event ID changes the pending event to
   `delivery_unknown`, appends nothing, and remains unresolved on later passes.
7. An injected uncertain append with no visible event, or an event-ID readback
   error, remains `delivery_unknown` after restart/retry and never appends based
   on absence alone.

Focused nested-schema fixture checks are in
`tests/test_task_outbox_nested_schema_fixture.py` and can be run with:

```sh
python3 -m unittest tests.test_task_outbox_nested_schema_fixture -v
```

## Contract boundary

- Task snapshot, operation receipt, transition history, and pending outbox are
  replaced as one JSON snapshot while holding one `flock` on `.kilit`.
- Message append and full-file event-ID readback use that same lock. A bounded
  tail is never used as duplicate evidence.
- `CommitUnknown` and `delivery_unknown` require reconciliation; neither is
  converted to rejection or automatic retry. For `delivery_unknown`, a full
  valid readback can confirm an exact event ID; a missing event or malformed
  tail remains unknown. `operation_id`/`event_id` are dedupe keys, not identity
  or authorization.
- Faults are deterministic fixture injection points. They demonstrate the
  modeled recovery branches, not real power-loss durability or all filesystem
  behavior. The implementation is a prototype, not canonical CLI/panel code.
- The runner is intentionally separate from the project test suite and does
  not start a server, provider, worker, or external process.
