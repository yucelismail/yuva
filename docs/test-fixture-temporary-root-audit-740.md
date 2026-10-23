# Test fixture temporary root audit (#740)

## Scope and change

The audit found two tests that pinned disposable fixture roots to `Path.home()`:

- `tests/test_panel_lifecycle.py`
- `tests/test_release_installer.py`

Both now use uniquely named `TemporaryDirectory` roots from the platform temp
directory. Each `tearDown` removes its root and asserts that the root no longer
exists. Fixture data remains under that root; neither test targets the Yuva
data directory.

## Verification

- `tests.test_panel_lifecycle`: 10 tests passed.
- `tests.test_release_installer`: 25 tests passed.

The local run supplied a private `TMPDIR` because this host's `/tmp` ownership
does not satisfy the product path-safety checks exercised by these tests. The
tests themselves still use the platform `TemporaryDirectory` default and do not
encode that local path.
