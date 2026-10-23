# Release installer disposable-root audit (#752)

`tests/test_release_installer.py` builds a synthetic Git source repository,
release payloads, manifests, rollback worktrees, install root, `current` and
`previous` pointers, and Yuva-like data beneath one `TemporaryDirectory`.
The fixture records data bytes and hashes around failure/rollback paths; no
production `current` symlink, host install root, or real Yuva data path is
passed to the installer.

The test root now uses a temporary child of `Path.home()`. The installer checks
every ancestor of `INSTALL_ROOT` and correctly rejects shared writable
directories such as `/tmp`; a root under the private runner home allows the
tests to exercise installer behavior while keeping all writes disposable. The
fixture teardown asserts the temporary tree is removed.

Crash and rollback coverage includes staged copy/manifest faults, release
directory fsync failure, pointer replacement uncertainty, post-replace fsync
uncertainty, descriptor close errors after commit, data-contract rollback
rejection, and successful rollback with unchanged data root. These cases
assert pointer and data state remains consistent with each commit outcome.

Verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
tests.test_release_installer -v` passed (25/25). The initial run using the
platform default `/tmp` parent was rejected by the installer ancestor policy;
after moving the disposable parent under the runner home, all tests reached
their intended cases and passed. `git diff --check` was clean.
