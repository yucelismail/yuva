# Task history trust regressions (#718)

Task history is display/audit data. A recorded actor, role, event name, or
`actor_trust` value does not authorize a task transition. The CLI authorizes
review from the current `durum.json` role and checks the task's current status.

The CLI and panel now reject task rows with an unknown or non-string status and
history arrays containing non-object events. The synthetic ledger regression
also supplies duplicate forged `onaylandı` events claiming `operator`,
`denetci`, and `verified_hmac`; the task remains `pending_verification`, and a
CLI review attempt by the unregistered `operator` fails without changing the
ledger bytes.

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_task_ledger_integrity tests.test_task_principal_gate \
  tests.test_panel_ui_workflow -v
Ran 24 tests ... OK
```
