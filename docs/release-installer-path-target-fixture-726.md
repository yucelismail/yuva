# Release installer path and collision fixture (#726)

## Scope

Expanded the `tests.test_release_installer` temporary-root fixture to check that installer writes stay within the manifest-allowed release tree and that unsafe or pre-existing path conflicts are preserved. No real install root, service, pointer, or user data was used.

## Results

| Adversarial case | Expected result | Fixture evidence |
|---|---|---|
| Relative `INSTALL_ROOT` | Reject before target writes. | `test_relative_install_root_is_rejected_without_writes` confirms no relative target is created and data digest is unchanged. |
| Symlink component in `INSTALL_ROOT` | Reject without following or writing through the link. | `test_symlink_component_in_install_root_is_rejected_without_writes` compares target and data digests. |
| `..` path in a manifest record | Reject manifest before creating the install root. | `test_manifest_path_traversal_is_rejected_before_root_writes` keeps an external canary and data digest unchanged. |
| Escaping symlink in payload | Reject before creating the install root. | `test_escaping_payload_symlink_is_rejected_without_writes` preserves external canary and data digest. |
| Payload regular file hard-linked to an external fixture file | Install only a copied file under the verified release tree; do not modify or retain an inode link to the external target. | `test_external_hardlinked_payload_is_copied_without_writing_target` compares external bytes, inode identity, and installed paths against manifest file records. |
| Existing non-symlink or unsafe `current` path | Reject before creating `releases`, `manifests`, or lock artifacts. | The two `test_preexisting_*current*` cases compare the entire temporary install-root and data digests. |
| Existing staging directory or symlink at the generated staging name | Reject while preserving the pre-existing entry and symlink target. | The two `test_preexisting_staging*collision*` cases force a UUID collision and compare root, outside target, and data digests. |

## Implementation change

Installer pointer names are now checked for malformed existing paths before creating child directories or the lock. Staging is created exclusively before copying; a collision returns `InstallError` and is never cleaned up as though it belonged to the current invocation. Partial copy failures still clean the staging directory after this invocation has created it.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_installer tests.test_release_manifest -v
```

Result: 34 tests passed. All adverse cases use disposable temporary roots; no release operation was run against an installed system.
