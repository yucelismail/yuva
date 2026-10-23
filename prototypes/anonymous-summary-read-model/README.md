# Anonymous summary read-model fixture

From the repository root, run:

```sh
python3 prototypes/anonymous-summary-read-model/fixture.py
```

This in-memory fixture projects a synthetic full snapshot through
`project_fixture.project_summary()`. Projection is default-off. When explicitly
enabled, it emits only validated roster IDs with `online`/`unknown` health and
aggregate task status counts. It omits names, roles, tools, profile notes,
relationships, heartbeat timestamps, task IDs/text/notes/history, chat text,
screen rows and other raw presence fields.

`ui_consumer.consume_summary()` is a separate view-model contract, not the
existing `panel/ui.html`. It labels the scope as summary-only. Partial input
shows visible entries as a lower bound, omits task counts, and never interprets
a missing roster as zero members. The fixture also covers disabled-by-default,
partial snapshot and missing roster cases, with private canary fields that
must not appear in any projection or view.

The fixture also checks each presence prerequisite independently (including
invalid TTLs and inclusive TTL boundaries), malformed or partially valid
rosters, missing/invalid task sources and statuses, incomplete source metadata,
unknown schema and transport failures, and the view-model's read-only field
allowlist. Every projection/view output is checked against private canary
values. `fixture.py` exits nonzero if any named check fails.

This prototype is not wired to `/api/veri` or `/veri`; it does not alter the
existing response/UI contract. Anonymous summary data minimization is not
authentication, authorization, or a same-UID process boundary. The real route
continues to expose its current contract until separately changed and
accepted. Source loading and live Yuva data are not used by this fixture.
