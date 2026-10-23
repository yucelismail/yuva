# Panel admin state + audit outbox fixture

An isolated prototype for the #674 ADR. It uses only a disposable directory
created by `run_fixture.py`; it never imports `panel.server`, reads the real
`durum.json`, or writes the real `mesaj.jsonl`.

The synthetic `durum.json` snapshot stores a state change, a stable operation
receipt, and the exact audit event body/event ID in one atomically replaced
snapshot under a fixture `.kilit`. Audit JSONL delivery follows that snapshot
commit. Repeating the same operation ID and request returns the stored receipt;
reusing it with changed data conflicts. Event IDs are deterministic from the
operation ID.

The fixture covers:

1. Two concurrent identical requests yield one state revision, receipt,
   outbox event, and later one audit line; a changed request conflicts.
2. State replace followed by directory-fsync uncertainty leaves a visible
   receipt; same-ID readback does not apply the mutation a second time.
3. Process crash after audit append but before the delivered marker, and
   append-fsync uncertainty after bytes are visible, are reconciled by exact
   event ID + exact body without a duplicate line.
4. Uncertain append with no visible line remains `delivery_unknown`; a later
   empty read is not permission to append again.
5. A same-ID/different-body line, duplicate event ID, or malformed tail stays
   `delivery_unknown` and is not modified by another append.
6. Post-replace directory descriptor close failure is `CommitUnknown`; a lock
   descriptor close error after commit releases the lock and same-ID replay
   does not create a second revision or event.
7. Partial append and readback I/O failure stay `delivery_unknown`; retries
   neither append over a malformed tail nor treat a failed read as delivery.

Run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 prototypes/panel-admin-outbox/run_fixture.py
```

This prototype illustrates modeled control flow only. Its file layout, lock,
fsync handling, JSONL reader and audit schema are not canonical Yuva behavior;
the fixture is not a power-loss guarantee, production integration, or approval
to modify live panel routes or data.
