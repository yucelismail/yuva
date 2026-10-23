# Yuva #662 — Exact event-ID append reconciliation fixture

The existing task-outbox prototype already modeled full JSONL readback,
exact-record matching, post-append restart, conflicting bodies, duplicate IDs,
malformed tails, and append-fsync uncertainty. This change closes an uncovered
negative branch: when append outcome or event-ID readback is uncertain and the
event is not visible, the fixture must not treat absence as permission to
append again.

## Added fixture branches

- `append_before_write` injects an ambiguous append outcome before any fixture
  bytes are written. The outbox moves to `delivery_unknown`; after reopening,
  the missing event remains unknown and the JSONL remains empty.
- `readback_error` injects a failed exact-ID lookup. The event is not appended;
  a later successful but empty read still does not retry because the persisted
  delivery state is already unknown.
- Existing `append_then_crash_restart` confirms one exact ID + exact body is
  read back as delivered without a second append.
- Existing conflicting body, duplicate event ID, malformed-tail, and
  append-fsync cases continue to stop blind retries.

All inputs are synthetic and each case uses a disposable temporary YUVA_DIR.
No real `mesaj.jsonl`, live ledger, panel notification, canonical CLI, or
production worker is used. Fault seams demonstrate modeled control flow, not
real power-loss or filesystem guarantees.

## Verification

```sh
python3 prototypes/task-outbox/run_fixture.py
```

All 8 fixture scenarios passed, including `ambiguous_absence_never_retries`.
