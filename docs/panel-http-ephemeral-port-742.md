# Panel HTTP fixture port audit (#742)

Panel/API HTTP fixtures bind only to loopback with port `0`, letting the OS
select an available ephemeral port. Added
`tests/test_panel_ephemeral_port_collision.py` to reserve a loopback port,
start the fixture listener on an ephemeral port, exercise a real Handler
request, and verify the listener releases its port during cleanup.

The audit found no fixed-port listener in the Handler/API fixtures. Remaining
`8686` references are production defaults/service documentation, copied legacy
fixtures, or synthetic `Host`/`Origin` values in direct handler unit tests;
none starts a listener or sends traffic to the live panel.

Verification: `tests.test_panel_ephemeral_port_collision` passed (1/1), and
`git diff --check` was clean. The fixture used only a temporary directory,
loopback sockets, and synthetic request data.
