"""Verify CI explicitly runs the repository's CLI/panel acceptance modules."""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ACCEPTANCE_MODULES = (
    "tests.test_task_assignment_ephemeral_http",
    "tests.test_task_ledger_integrity",
    "tests.test_task_board_live_update_consistency_fixture",
)


def _load_test_runner():
    path = ROOT / "scripts" / "run_tests.py"
    spec = importlib.util.spec_from_file_location("ci_contract_test_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


test_runner = _load_test_runner()


class CiTestDiscoveryContractTests(unittest.TestCase):
    def test_acceptance_modules_exist_and_collect_the_expected_cases(self):
        loader = unittest.TestLoader()
        counts = {}
        for name in ACCEPTANCE_MODULES:
            with self.subTest(module=name):
                self.assertTrue((ROOT / (name.replace(".", "/") + ".py")).is_file())
                counts[name] = loader.loadTestsFromName(name).countTestCases()

        self.assertEqual(loader.errors, [])
        self.assertEqual(counts, {
            "tests.test_task_assignment_ephemeral_http": 1,
            "tests.test_task_ledger_integrity": 12,
            "tests.test_task_board_live_update_consistency_fixture": 3,
        })
        self.assertEqual(sum(counts.values()), 16)

    def test_workflow_runs_all_acceptance_modules_before_full_discovery(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        marker = "- name: Run CLI/panel task acceptance discovery"
        self.assertIn(marker, workflow)
        start = workflow.index(marker)
        end = workflow.find("\n      - name:", start + len(marker))
        step = workflow[start:end]

        self.assertIn("python -m unittest -v", step)
        for module in ACCEPTANCE_MODULES:
            with self.subTest(module=module):
                self.assertIn(module, step)
        self.assertLess(start, workflow.index(
            "- name: Run unittest suite on Python 3.8"))
        self.assertIn(
            "run: PYTHONDONTWRITEBYTECODE=1 python scripts/run_tests.py",
            workflow)

    def test_discovery_contract_covers_every_test_module(self):
        expected = test_runner._expected_test_modules(test_runner.TESTS_ROOT, ROOT)
        suite = unittest.TestLoader().discover(
            start_dir=str(test_runner.TESTS_ROOT),
            pattern=test_runner.TEST_PATTERN, top_level_dir=str(ROOT))
        discovered = test_runner._discovered_test_modules(suite)

        self.assertGreater(len(expected), 0)
        self.assertEqual(discovered, expected)


if __name__ == "__main__":
    unittest.main()
