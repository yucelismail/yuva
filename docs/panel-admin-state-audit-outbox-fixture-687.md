# Yuva #687 — Panel admin state/audit idempotent outbox fixture

## Kapsam

`prototypes/panel-admin-outbox/` contains a separate synthetic prototype for
the future transaction shape described in [#674 ADR](panel-admin-state-audit-atomicity-adr-674.md).
It does not import `panel.server` and does not read or write the real
`durum.json` or `mesaj.jsonl`.

The fixture commits a synthetic state change, stable `operation_id` receipt,
and deterministic event ID/exact audit body into one temporary state snapshot
under a fixture lock. Audit JSONL append occurs after the state snapshot
commit. Same ID/same request is a replay; same ID/changed request conflicts.

## Scenarios

- Two concurrent identical calls produce one state revision, receipt and
  outbox event. Changed request with the same ID conflicts without changing
  state bytes.
- Post-replace state directory-fsync fault returns `CommitUnknown`; reopening
  and repeating the same request reads the stored receipt without a second
  mutation or audit append.
- Crash after audit append but before the delivered marker is reconciled by
  exact event ID/body readback with one audit line.
- Append-fsync uncertainty after the line is visible is reconciled the same
  way without a duplicate append.
- Uncertain append with no visible line, changed-body event ID, duplicate event
  ID, and malformed tail remain `delivery_unknown`; none authorizes blind
  append.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 prototypes/panel-admin-outbox/run_fixture.py
```

All 5 grouped fixture scenarios passed with bytecode generation disabled.
Output is aggregate-only; temporary paths and synthetic record bodies are not
printed. The fixture directory contains only `admin_outbox.py`,
`run_fixture.py`, and `README.md`.

## Boundary

This is control-flow evidence for the prototype only. The fixture's JSON
schema, lock acquisition, state writer and audit append are not canonical Yuva
implementations and do not prove filesystem power-loss durability. No panel
route, production CLI, live ledger, real audit/chat JSONL, service or provider
was changed or exercised. Integration still requires #674's data-schema,
writer compatibility, retention, authorization, durable append and restore
acceptance gates.
