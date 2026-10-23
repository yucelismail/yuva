# Presence UI states fixture (#720)

The roster now distinguishes three evidence states. Unknown presence stays
neutral gray; a fresh `host_presence.state=online` observation appears blue as
“Host etkin · kullanıcı kimliği doğrulanmadı”; principal presence appears green
only when the existing `online`, `presence_state=online`,
`presence_verified=true`, and fresh-heartbeat checks all pass. Host liveness is
kept out of the principal-online count, target eligibility, and green styling.
Stale host observations remain unknown.

The synthetic UI contract fixture covers unknown, host-only, and
principal-verified states alongside the #650 projection fixture. It uses no
real broker, UID, socket, service, or panel endpoint.

Validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_panel_ui_workflow \
  tests.test_panel_presence_broker_principal_fixture -v
Ran 17 tests ... OK
```
