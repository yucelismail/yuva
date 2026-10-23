import importlib.util
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_tests.py"
SPEC = importlib.util.spec_from_file_location("yuva_test_runner", RUNNER_PATH)
test_runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(test_runner)


class TestRunnerTests(unittest.TestCase):
    def test_repository_discovery_uses_repository_root_for_imports(self):
        output = io.StringIO()
        with patch.object(test_runner.unittest.TestLoader, "discover",
                          return_value=unittest.TestSuite()) as discover:
            status = test_runner.main(stream=output)

        self.assertEqual(status, 2)
        self.assertEqual(discover.call_args.kwargs["top_level_dir"], str(ROOT))

    def test_import_error_placeholder_fails_before_suite_runner_can_report_success(self):
        with tempfile.TemporaryDirectory(prefix="yuva-import-error-tests-") as temp:
            tests = Path(temp) / "tests"
            tests.mkdir()
            (tests / "test_broken_fixture.py").write_text(
                "raise ImportError('synthetic test import failure')\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            error = io.StringIO()

            with redirect_stderr(error):
                status = test_runner.main(start_dir=tests, stream=output)

        combined = output.getvalue() + error.getvalue()
        self.assertEqual(status, 2)
        self.assertIn("1 import error(s)", error.getvalue())
        self.assertIn("failed-test placeholder(s)", error.getvalue())
        self.assertNotIn("_FailedTest", combined)
        self.assertNotIn("Ran ", output.getvalue())
        self.assertNotIn("OK", output.getvalue())

    def test_failed_test_placeholder_in_returned_suite_is_rejected(self):
        failed = test_runner.unittest.loader._FailedTest(
            "test_broken_fixture", ImportError("synthetic import error"))
        output = io.StringIO()
        error = io.StringIO()

        with patch.object(test_runner.unittest.TestLoader, "discover",
                          return_value=unittest.TestSuite([failed])), \
                redirect_stderr(error):
            status = test_runner.main(stream=output)

        self.assertEqual(status, 2)
        self.assertIn("0 import error(s), 1 failed-test placeholder(s)",
                      error.getvalue())
        self.assertNotIn("_FailedTest", output.getvalue() + error.getvalue())
        self.assertNotIn("OK", output.getvalue())

    def test_empty_discovery_returns_nonzero_without_reporting_success(self):
        with tempfile.TemporaryDirectory(prefix="yuva-empty-tests-") as temp:
            root = Path(temp)
            tests = root / "tests"
            tests.mkdir()
            output = io.StringIO()
            error = io.StringIO()

            with redirect_stderr(error):
                status = test_runner.main(
                    start_dir=tests, stream=output)

        self.assertEqual(status, 2)
        self.assertIn("zero tests", error.getvalue())
        self.assertNotIn("OK", output.getvalue())

    def test_nonempty_discovery_runs_suite_and_returns_success(self):
        with tempfile.TemporaryDirectory(prefix="yuva-positive-tests-") as temp:
            root = Path(temp)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_fixture_case.py").write_text(
                "import os, pathlib, subprocess, sys, unittest\n"
                "class FixtureCase(unittest.TestCase):\n"
                "    def test_fixture_roots_cover_test_and_child_process(self):\n"
                "        fixture = pathlib.Path(os.environ['YUVA_TEST_ROOT']).resolve()\n"
                "        home = pathlib.Path(os.environ['HOME']).resolve()\n"
                "        data = pathlib.Path(os.environ['YUVA_DIR']).resolve()\n"
                "        self.assertIn(fixture, home.parents)\n"
                "        self.assertEqual(data, home / 'yuva')\n"
                "        self.assertTrue(data.is_dir())\n"
                "        child_data = subprocess.check_output([sys.executable, '-c',\n"
                "            \"import os; print(os.environ['YUVA_DIR'])\"],\n"
                "            text=True, timeout=3).strip()\n"
                "        self.assertEqual(pathlib.Path(child_data).resolve(), data)\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            original = {name: os.environ.get(name) for name in (
                "HOME", "YUVA_DIR", "YUVA_TEST_ROOT")}

            status = test_runner.main(
                start_dir=tests, stream=output)

        self.assertEqual(status, 0)
        self.assertIn("Ran 1 test", output.getvalue())
        self.assertIn("OK", output.getvalue())
        self.assertEqual({name: os.environ.get(name) for name in original}, original)

if __name__ == "__main__":
    unittest.main()
