# Task CLI stale snapshot and lock failure fixture (#704)

## Source review

The canonical CLI routes `gorev ekle`, `ata`, `al`, `teslim`, and `denetle`
through their `cmd_gorev_*` handlers in `bin/yuva`. Each handler performs its
lookup and state transition in a callback passed to `gorev_guncelle`. That
function takes `kilit_tut()` before loading the ledger, invokes the callback
against that locked snapshot, then persists it. The `al` transition therefore
rechecks pending state and assignee under the same lock used for the write;
the multi-process claim fixture also checks this behavior under contention.

## Disposable negative coverage

`tests/test_task_ledger_integrity.py` now exercises all five mutation handlers
with an injected lock timeout and asserts the ledger bytes remain unchanged.
It also invokes the real CLI commands against a malformed ledger and asserts
each exits unsuccessfully without replacing or truncating those bytes. Both
fixtures use the test's `TemporaryDirectory` root; no live board is involved.

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_task_ledger_integrity.TaskLedgerIntegrityTests.test_canonical_task_mutations_do_not_write_when_lock_times_out \
  tests.test_task_ledger_integrity.TaskLedgerIntegrityTests.test_canonical_task_cli_mutations_preserve_malformed_ledger_bytes -v
Ran 2 tests ... OK
```
