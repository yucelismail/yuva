# Auth provisioning test isolation (#753)

Provisioning CLI fixtures now pass a small explicit environment to child
processes (`HOME`, `TMPDIR`, fixture `YUVA_DIR`, and
`YUVA_AUTH_ENABLED=0`) instead of copying the developer/CI environment. The
threat-model case adds only a synthetic secret sentinel and verifies it is
absent from CLI output, stderr, the temporary auth snapshot, and the temporary
receipt. Its check uses a fixed failure message to avoid echoing the sentinel
if the regression occurs.

Auth lifecycle keys use fixed synthetic bytes; enrollment inputs and operation
IDs are fixture labels. Provisioning and receipt tests use `TemporaryDirectory`
roots, and teardown now asserts those roots were removed, including receipts.
The fixtures call the auth v2 store only at explicit temporary roots. No
operator secret, real credential, key-generation service, external store, or
non-fixture `YUVA_DIR` is used.

Verification: four focused modules passed (25/25):
`test_auth_provision_cli`, `test_auth_provision_threat_model`,
`test_auth_key_lifecycle_fixture`, and `test_auth_key_operation_receipts`.
