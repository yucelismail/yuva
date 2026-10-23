# Synthetic auth key lifecycle fixture (#591)

This fixture exercises the existing v2 `AuthStateStore` transaction API with
fixed synthetic bytes in a marked `TemporaryDirectory`. It does not create
real keys/tokens, expose secrets, alter `YUVA_DIR`, enable auth, or implement
an enrollment/revoke endpoint or CLI.

Run the focused fixture:

```bash
python3 -m unittest tests.test_auth_key_lifecycle_fixture -v
```

The lifecycle design, transaction error matrix, same-UID NO-GO boundary, and
known operation-receipt gap are in
[`docs/auth-key-enrollment-lifecycle-fixture-591.md`](../../docs/auth-key-enrollment-lifecycle-fixture-591.md).
