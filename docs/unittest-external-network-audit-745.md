# Unittest external network audit (#745)

## Findings

Static search covered test modules, Python fixtures, and the test runner for
HTTP clients, URL openers, common API SDKs, socket connections, and command
based download/network tools. No `requests`, `httpx`, `aiohttp`, `urllib.request`,
`urlopen`, or external API client is used by the unittest suite. The only
`urllib` import in a fixture is `urllib.parse.urlsplit`, which parses a URL and
does not perform I/O.

Real HTTP traffic is confined to local test servers. Every server constructor
started by an active unittest fixture binds `127.0.0.1` with port `0`; clients
use that server's assigned `server_port`. A copied legacy panel source fixture
contains its historical production default but is not launched by tests.
Covered modules include task assignment, snapshot
budget, GET acceptance, panel error handling, browser session handling, CSP,
browser CSRF routing, and HTTP fixture lifecycle. The CSP and browser-session
fixture servers follow the same loopback/ephemeral pattern. AF_UNIX sockets in
presence and operator-broker tests are local IPC, not external network access.

Other URL-shaped values are test data: invalid-origin cases, redaction canaries,
`http://127.0.0.1:1` passed to the heartbeat child test, and `curl` text inside
a synthetic command string. They are not HTTP client calls. Remaining `8686`
strings are production defaults or synthetic headers; they do not open a test
listener. CLI tests create disposable local Git repositories; their Git
subprocesses use local paths and `file://` protocol only where explicitly
enabled. No clone/fetch/pull, package install, or HTTP download was found.

## Closed-network coverage proposal

Keep the current deterministic unit suite as the baseline and add an opt-in
offline job that runs `PYTHONDONTWRITEBYTECODE=1 python scripts/run_tests.py`
with outbound networking denied at the runner/container level. Preserve
loopback so ephemeral HTTP fixtures continue to work; preserve AF_UNIX for
local IPC tests. A small guard smoke test should demonstrate that an attempted
non-loopback TCP connection is denied while a loopback fixture request and
Unix-socket exchange still succeed. Run the full discovered suite under that
same restriction and require a nonzero result if any test tries external
network access. The current CI workflow does not itself impose an egress deny,
so this audit does not claim an OS-enforced closed-network full-suite run.

## Scope and evidence

This was a read-only source audit plus the targeted #742 ephemeral loopback
collision/cleanup regression test (1/1 passed). No production endpoint, live
panel, network service, or external API was contacted.
