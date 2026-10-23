# Task outbox canonical schema fixture (#702)

Prerequisites #678 and #687 are verified. The new disposable fixture creates a
task with the canonical `bin/yuva gorev ekle` writer, copies that v1 ledger into
a separate temporary prototype root, then applies one outbox operation there.
It checks preservation of canonical task fields, `siradaki`, schema version,
history, and an opaque additive root extension. The generated receipt and event
pass the prototype validator and remain inside its entry, message, and count
bounds.

A second fixture probes `.kilit` from independent file descriptors during the
prototype's ledger read and snapshot replacement, confirming both operations
remain inside the lock scope. All reads and writes use the test's
`TemporaryDirectory`; this adds no canonical CLI/panel adapter or live ledger
behavior.

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_task_outbox_canonical_schema_fixture \
  tests.test_task_outbox_nested_schema_fixture \
  tests.test_task_outbox_canonical_writer_compat_fixture -v
Ran 12 tests ... OK
```
