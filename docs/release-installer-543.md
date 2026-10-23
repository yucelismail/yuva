# #543 — explicit-root release install and rollback

`release_installer.py` installs only a release that passes the #542 verifier
against a clean source checkout and an externally supplied manifest SHA-256.
It requires explicit `INSTALL_ROOT`, `YUVA_DIR`, payload, manifest, and source
repository paths. It never copies, renames, or edits the data root.

## Prepare and install

1. Select the canonical repository and a full commit. Its worktree and
   submodules must be clean. Export that commit into a separate scratch payload
   and create its manifest with `release_manifest.py`.
2. Obtain the manifest SHA-256 through the trusted channel chosen by the release
   operator. The hash stored beside an installed manifest is only a receipt;
   the installer always requires the external pin as an argument.
3. Install with the same clean source checkout used for verification:

   ```sh
   python3 release_installer.py install \
     --install-root <absolute-owner-only-INSTALL_ROOT> \
     --data-root <existing-real-YUVA_DIR> \
     --payload <scratch-payload> \
     --manifest <external-manifest.json> \
     --source-repo <clean-canonical-Git-checkout> \
     --trusted-manifest-sha256 <externally-pinned-64-hex-digest>
   ```

The root and `releases/`/`manifests/` directories must be real owner-only
directories. `INSTALL_ROOT`, source, payload, and data root must be separate
and non-nested. An existing symlink in any root path is rejected. `current`
and `previous` are relative symlinks to
`releases/<full-commit>-<full-payload-sha256>`.

The installer verifies the source/payload/manifest/pin before creating the
install root, copies to a unique `.staging-*` directory on the release
filesystem, verifies the copied tree again, and freezes its directory tree
read-only. The final directory is published with an atomic no-replace rename;
existing release IDs are never overwritten. The manifest receipt is stored
outside the payload under `manifests/`. A new `current` pointer is installed
atomically; the former current ID becomes `previous`. A failed or ambiguous
pointer durability result is not automatically retried: inspect both exact
symlink targets first.

## Rollback

Rollback defaults to the `previous` pointer. Supply a clean source checkout at
that release's exact full commit and the manifest's externally trusted digest:

```sh
python3 release_installer.py rollback \
  --install-root <absolute-INSTALL_ROOT> \
  --data-root <same-existing-real-YUVA_DIR> \
  --source-repo <clean-checkout-at-target-release-commit> \
  --trusted-manifest-sha256 <externally-pinned-target-manifest-digest>
```

`--release-id <full-id>` may select a different verified release explicitly.
Rollback rechecks the target directory, stored manifest, clean source commit,
payload, and external pin before atomically switching the pointers. It does not
restore data, change the PATH entry, restart a panel, or claim that existing
processes changed code. Schema compatibility, backups, stopped writers, panel
runtime identity, and post-switch canary acceptance remain separate operator
gates from #486/#508; this tool does not establish them.

## Fixture coverage

`tests/test_release_installer.py` uses a temporary Git repository, payload,
install root, and data root. It covers verified installation, duplicate-ID
rejection, dirty source and wrong-pin failures, path overlap, unsafe pointer
rejection, and switching to/rolling back to a prior full release ID. It never
uses the host install root, live panel, systemd, or real Yuva data.
