"""Run the repository unittest suite and reject empty discovery."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from typing import Optional
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPOSITORY_ROOT / "tests"
TEST_PATTERN = "test_*.py"


@contextmanager
def isolated_test_environment():
    """Give tests disposable HOME and YUVA_DIR roots, including child processes."""
    with tempfile.TemporaryDirectory(prefix="yuva-test-isolation-") as temp:
        fixture_root = Path(temp)
        home = fixture_root / "home"
        data_root = home / "yuva"
        home.mkdir(mode=0o700)
        data_root.mkdir(mode=0o700)
        with patch.dict(os.environ, {
            "HOME": str(home),
            "YUVA_DIR": str(data_root),
            "YUVA_TEST_ROOT": str(fixture_root),
        }):
            yield


def _failed_test_placeholder_count(suite) -> int:
    failed_test_type = getattr(unittest.loader, "_FailedTest", None)
    count = 0
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            count += _failed_test_placeholder_count(test)
        elif failed_test_type is not None and isinstance(test, failed_test_type):
            count += 1
    return count


def main(*, start_dir: Path = TESTS_ROOT,
         top_level_dir: Optional[Path] = None, stream=None) -> int:
    """Discover and run tests; return non-zero for errors or zero tests."""
    loader = unittest.TestLoader()
    with isolated_test_environment():
        try:
            discovery_root = top_level_dir
            if (discovery_root is None
                    and Path(start_dir).resolve() == TESTS_ROOT):
                discovery_root = REPOSITORY_ROOT
            suite = loader.discover(
                start_dir=str(start_dir), pattern=TEST_PATTERN,
                top_level_dir=(str(discovery_root)
                               if discovery_root is not None else None))
        except Exception as error:
            print(f"test discovery failed: {type(error).__name__}", file=sys.stderr)
            return 2

        failed_placeholders = _failed_test_placeholder_count(suite)
        if loader.errors or failed_placeholders:
            print(
                "test discovery failed: "
                f"{len(loader.errors)} import error(s), "
                f"{failed_placeholders} failed-test placeholder(s)",
                file=sys.stderr,
            )
            return 2

        count = suite.countTestCases()
        if count == 0:
            print(
                f"test discovery found zero tests (pattern {TEST_PATTERN})",
                file=sys.stderr,
            )
            return 2

        result = unittest.TextTestRunner(verbosity=2, stream=stream).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
