# CI runner import-placeholder guard (#769)

`scripts/run_tests.py` now uses a fresh `TestLoader`, rejects loader import
errors and recursively detects `unittest.loader._FailedTest` entries before
starting the suite. It returns a discovery error code and a count-only
diagnostic, so an import placeholder cannot appear in a green test report.
Discovery exceptions also return nonzero. Normal test failures keep their
existing nonzero result.

Runner regressions cover a real synthetic module `ImportError`, an injected
`_FailedTest` suite, empty discovery, and a passing suite. The targeted runner
module passed 5/5 tests. Full repository suite execution is a separate clean
checkout acceptance task (#770).
