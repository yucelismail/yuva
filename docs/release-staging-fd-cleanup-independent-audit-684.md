# Release staging FD cleanup: independent audit (#684)

## Scope and status

This is a source and disposable-fixture audit of the #683 descriptor-cleanup change in `release_staging_inventory.py` and `tests/test_release_staging_inventory.py`. It does not inspect or alter a host `INSTALL_ROOT`, service, or installation. The initial pre-acceptance probe found two close-error leaks and was delivered as preliminary evidence. After #683 was revised and marked `verified`, this audit was repeated against that accepted revision. Both reported paths are now covered by regression fixtures and pass with stable descriptor counts.

## Results matrix

| Path | Evidence | Result |
|---|---|---|
| Normal repeated inventory | Existing `test_repeated_inventory_keeps_process_descriptor_count_stable` runs 40 temporary-root calls and compares `/proc/self/fd` before/after. | PASS; no descriptor growth. |
| Child `fstat` error after open | Existing `test_child_directory_fstat_error_closes_opened_descriptor` injects `fstat` failure and checks descriptor count. | PASS; opened child FD is closed. |
| Second child acquisition error | Existing `test_second_child_open_error_closes_first_child_descriptor` injects failure opening `manifests` after `releases` was acquired. | PASS; first child FD is closed. |
| Explicit-root traversal: prior-component `close` error (before #683 revision) | Initial disposable root probe injected an error from closing the old traversal FD after the next component was opened. | FAIL before revision; descriptor count increased by 1. |
| Child cleanup: first `close` error (before #683 revision) | Initial disposable root probe acquired both child FDs, then injected an error while closing `releases` in `_inventory_open_root` cleanup. | FAIL before revision; descriptor count increased by 1. |

## Re-audit after #683 acceptance

#683 was marked `verified` before this repeat audit. The revised source now transfers `next_fd` into the owned `fd` slot before closing the previous traversal descriptor and attempts cleanup of the new descriptor if the close raises. `_inventory_open_root` now attempts both child descriptor closes, retains the first close exception, and raises it only after both attempts.

| Path on accepted #683 revision | Fixture evidence | Result |
|---|---|---|
| Normal repeated inventory | `test_repeated_inventory_keeps_process_descriptor_count_stable`: 40 calls against a temporary root. | PASS; descriptor count unchanged. |
| Child `fstat` error after open | `test_child_directory_fstat_error_closes_opened_descriptor`. | PASS; descriptor count unchanged. |
| Second child acquisition error | `test_second_child_open_error_closes_first_child_descriptor`. | PASS; descriptor count unchanged. |
| Root traversal previous-FD close error | `test_explicit_root_traversal_close_error_closes_next_descriptor`. | PASS; injected close error propagates and descriptor count is unchanged. |
| First child cleanup close error | `test_child_cleanup_close_error_still_closes_other_child`. | PASS; injected close error propagates after attempting the other close; descriptor count is unchanged. |

Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_staging_inventory -v`

Result: 11 tests passed. The two new close-error regressions reproduce the previously failing conditions. No production `INSTALL_ROOT`, service, or host path was used.

The two injected failures were exercised in an inline Python fixture using `TemporaryDirectory`, patched `os.close`, and `/proc/self/fd` counts. Observed results were `root_traversal_close ... fd_delta=1` and `root_child_cleanup ... fd_delta=1`; the fixture closed the leaked descriptors after measuring them. No production path was used.

## Findings

1. **FD leak if closing a traversed parent raises.** In `_open_explicit_root`, `next_fd` is opened before `os.close(fd)`, but ownership is transferred with `fd = next_fd` only after the close returns. If close raises, the outer exception handler retries closing the old descriptor and never closes `next_fd`. Preserve both descriptors in cleanup until transfer succeeds, and make cleanup attempt each owned descriptor even when one close raises.

2. **Second child FD can be skipped during cleanup.** `_inventory_open_root` closes `releases_fd` and then `manifests_fd` sequentially in one `finally`. If the first close raises, the second close is skipped. Cleanup should attempt both closes and then propagate/report a deterministic error after all owned descriptors have been handled.

The injected `close` errors model a syscall that reports failure after the descriptor was closed. Since a close error can leave descriptor state ambiguous, cleanup must avoid assuming either that the FD remains open or that later cleanup statements will run.

## Initial fixture run before #683 revision

Command: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_staging_inventory -v`

Result: 9 tests passed, including the normal repeated-call, injected child `fstat`, and second child-open cases. This suite does not cover either injected close-failure path above, so the pass does not clear those findings.

## Disposition

The two previously observed leaks are corrected in the accepted #683 revision and the new temporary-root regressions pass. No remaining descriptor leak was found in the requested open/dup/scandir/fstat/close and early-return paths. This review changes no implementation or test code; only this audit note was updated.
