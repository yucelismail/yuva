# Panel HTTP fixture lifecycle (#743)

## Changes

- Added `tests/http_fixture_lifecycle.py` to start non-daemon fixture server
  threads and register shutdown, socket close, and bounded join cleanup.
- The cleanup still closes the socket and joins the thread when shutdown raises;
  a live thread after the timeout fails the test.
- Applied the helper to the task-assignment and panel-error loopback fixtures.
- Changed the other panel HTTP fixture server threads in the audited tests to
  non-daemon threads. Their existing teardown paths close the server and assert
  the thread has exited.
- Added successful-request and injected-shutdown-error tests. Both verify the
  socket is closed, the thread is stopped, and the temporary root is removed.

## Verification

The focused lifecycle and HTTP fixture modules passed: 38 tests total. The
local-socket test run required approval because the default sandbox blocks
loopback binds. No live panel or production endpoint was used.
