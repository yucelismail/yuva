# Yuva #700 — Temporary auth provision CLI

**Scope:** `yuva auth provision` creates an empty v2 auth store only in an existing private directory below the process temporary root. No credentials or enrollment records are created.

## Invocation contract

```text
yuva auth provision --store-root <existing-temp-directory> \
  --instance-id <stable-id> --audience <api-audience> --operation-id <stable-operation-id>
```

The CLI rejects relative paths, parent traversal, symlinked/non-canonical roots, the temp root itself, and paths outside `tempfile.gettempdir()`. The target must already be owned by the effective UID and have mode `0700`; the command never creates the root. Store schema validation and exact ID/audience constraints run before store creation.

The result contains an empty v2 state (`keys`, `enrollments`, `nonces`, and `rate_limits` are empty), a stable auth lock, a separate provision lock, and a secret-free `auth-provision-v1.receipt.json`. Receipt fields bind the operation ID, kind, instance, audience, initial wall time, state digest and status. No key, token, enrollment, provider setting, user account or auth environment setting is written.

## Replay and uncertain commit

- Same operation ID and request with a committed receipt plus exact store digest returns `replayed` without changing state or receipt bytes.
- Reusing an operation ID with different instance/audience is rejected without overwrite.
- A known pre-commit failure is recorded as `not_committed`; a retry can use the same operation ID and fixed initial timestamp.
- A prepared receipt after interruption, digest mismatch, or store/directory durability uncertainty returns `commit_unknown`. It is never retried automatically; operator readback/reconciliation is required.
- Receipt replacement uses a same-directory temporary file, file fsync, atomic replace and directory fsync. Failure after replace is `commit_unknown`.

This CLI is a temporary fixture workflow, not production key provisioning, custody, anti-rollback backup/restore, browser session setup, or permission to set `YUVA_AUTH_ENABLED=1`. Existing `auth init` remains a separate empty-store initializer.

## Verification

`tests/test_auth_provision_cli.py` uses only `TemporaryDirectory` roots. It covers initial provision, receipt replay, operation conflict, rejection outside a selected temp root, and injected store directory-fsync `commit_unknown`; no real key material is generated or copied.
