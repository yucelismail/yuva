# Release installer crash and cleanup: independent audit (#708)

## Scope

Compared `release_installer.py`, the temporary-root fault fixtures in `tests/test_release_installer.py`, and the verified evidence in #618, #630, and #631. All execution used temporary roots. No host `INSTALL_ROOT`, service, live pointer, backup, or user data was inspected or changed.

## Crash and failure matrix

| Failure point | Source/result invariant | Evidence and limit |
|---|---|---|
| Payload copy or staged verification before publish | On ordinary exceptions, `moved` is false and staging cleanup is attempted. `current`/`previous` are not switched; data root is outside install root and unchanged. | #618 fixture `test_copy_and_staged_manifest_faults_preserve_current_and_data_hash` checks both injected paths and verifies the staging directory is removed, pointer unchanged, data digest unchanged. Abrupt kill can bypass cleanup; #631 correctly classifies any residual staging as HOLD. |
| Final rename succeeds, then `releases/` directory fsync fails | `moved` is true, so final release is retained; manifest receipt and pointers have not yet been written/switched. Data root remains unchanged. | #618 `test_release_directory_fsync_fault_keeps_old_pointer_and_data` verifies final release remains, old `current` remains, and data digest is unchanged. Receipt absence is consistent with write order in `install_release`. |
| Manifest receipt write or `manifests/` fsync fails | Final release may remain with an absent/partial/full receipt; pointer updates have not started. Do not retry the same release ID or repair the receipt blindly. Data root remains outside this write path. | Source order at `release_installer.py:561-566` and #631 recovery classification establish the possible states. Existing #618 tests do not inject either receipt failure; they also do not prove power-loss persistence. |
| `previous` pointer pre-sync/replace/post-sync fails during install or rollback | `previous` is a separate atomic pointer operation before `current`. A failure can leave a temp symlink, unchanged `previous`, or a visibly switched `previous` with durability unknown; `current` may still be old. | Source order at `release_installer.py:567-569` and `616-617`; #630 documents the two-pointer intermediate state. These pointer-specific failure branches are not directly exercised by `tests/test_release_installer.py`. |
| `current` replace fails | API returns `CommitUnknown`; no compensating pointer switch occurs. Exact pointer readback is required. | #618 `test_current_pointer_replace_fault_is_commit_unknown_without_rollback` injects a pre-replace error and confirms old `current` and unchanged data digest. This fixture does not model an error reported after the syscall has actually replaced the link. |
| `current` directory fsync fails after replace | API returns `CommitUnknown`; the new target is visible in the current process, but crash durability remains unknown. No rollback is attempted. | #618 `test_post_replace_pointer_fsync_fault_is_commit_unknown_no_auto_rollback` confirms visible new target and unchanged data digest. |
| Normal install and rollback | Pointer target changes only after checks and publication; data root is read/validated but not written. | Existing `test_install_and_rollback_keep_data_root_outside_release_tree` checks pointer outcomes and exact data-tree digest. |
| Pointer directory FD close fails after successful replace and post-replace fsync | **Finding:** the new pointer is already visible and its directory fsync returned successfully, but the close exception is caught by the outer generic `OSError` handler and reported as “pointer setup failed before switch.” | Reproduced with `_atomic_pointer` on a temporary root by injecting `os.close` failure after performing the real close. It raised `InstallError: current pointer setup failed before switch (OSError)` while `current` already pointed to the new release. No temp pointer or data-root change occurred. This can mislead a caller about commit state. |

## Verification

Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_installer -v`

Result: 14 tests passed. This confirms the existing synthetic cases only; it does not cover abrupt process death, receipt write/fsync failures, `previous` pointer failures, or a close failure after pointer commit.

The close-error reproduction used only a `TemporaryDirectory`, synthetic canonical release IDs and patched `os.close`; the patch performed the real close before raising. The new symlink target was read back from that temporary directory.

## Finding and follow-up

`_atomic_pointer()` closes `root_fd` in a `finally` inside the outer `try`. If that close raises after both `os.replace` and the post-replace `fsync` succeeded, the generic handler at `release_installer.py:220-226` incorrectly describes a committed pointer as a pre-switch setup failure. A caller may treat the operation as failed even though the new pointer is visible and synced. The pointer ID collision prevents a blind repeat install from silently overwriting the release, but the returned classification is still false and obscures the required reconciliation state.

A separate follow-up task #729 was opened to correct this status path and cover it with a temporary-root regression. It also asks for `_install_lock()` close errors after a successful transaction to be inspected, since a lock-close exception can mask a committed install/rollback result. No installer implementation or test file was changed in this audit.

## Disposition

The verified #618/#630/#631 invariants hold for the exercised paths: no automatic pointer rollback, data-root bytes remain unchanged in fault fixtures, and incomplete published artifacts remain for HOLD/reconciliation. The post-commit close-error classification is a real residual issue and is tracked separately. No live installation or cleanup action is authorized by this review.
