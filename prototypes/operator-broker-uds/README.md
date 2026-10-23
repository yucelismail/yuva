# Operator signer → broker UDS contract fixture

Run from the repository root:

```sh
python3 prototypes/operator-broker-uds/fixture.py
```

This in-memory fixture models a single exact request frame and policy sequence.
Synthetic peer labels are ordinary strings; they do not name or create OS
accounts. `signature_verdict="valid_fixture"` is an injected test result, not
an HMAC computation. There is no socket, `SO_PEERCRED` syscall, key, verifier
store, service, HTTP route, or Yuva mutation.

The request frame is a 4-byte big-endian length followed by strict UTF-8 JSON
with an exact field allowlist. Its body is canonical unpadded base64url so the
signer and broker recover the same raw bytes that HMAC v1 signs. The frame has
no caller-supplied UID or scope: peer UID comes from the kernel in deployment,
and scope is derived as `METHOD path`. The only fixture route is
`POST /api/yaz`.

Cases cover the accepted signer peer, agent peer spoof attempt, principal/key/
audience mismatch, out-of-scope task and query routes, bad signature, nonce
replay, unknown nonce commit, unverified operator custody, duplicate frame
keys, and injected identity/secret fields. Logs/reports contain only decisions
and constant reason codes. The fixture does not test Linux peer-credential
semantics or cryptographic HMAC correctness.

Linux `SO_PEERCRED` kernel behavior is covered separately by
`python3 -m unittest tests.test_operator_broker_peercred_fixture -v`. That
fixture opens only a temporary filesystem UDS and tests the current process
UID against a synthetic allowlist; it does not create a second UID or run a
broker service. See `docs/operator-broker-peercred-fixture-615.md`.

The separate two-UID runner is an explicit root-only staging-host operation;
it requires two existing non-root local accounts and uses `setpriv` plus a
temporary socket tree only:

```sh
sudo python3 prototypes/operator-broker-uds/two_uid_acceptance.py \
  --broker-uid 2101 --signer-uid 2102
```

It does not create accounts, keys, services, or Yuva state. Its PASS is only
for the disposable kernel peer-UID fixture; see
`docs/operator-broker-two-uid-fixture-649.md` and the separate host runbook
`docs/operator-broker-separate-uid-host-acceptance-637.md`.
