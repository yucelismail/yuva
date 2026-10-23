from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class CiCheckoutCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            r"(?ms)^      - name: Check out repository\n"
            r"(?P<step>.*?)(?=^      - name:|\Z)",
            cls.workflow,
        )
        if match is None:
            raise AssertionError("checkout step was not found")
        cls.checkout_step = match.group("step")
        cls.after_checkout = cls.workflow[match.end():]

    def test_checkout_does_not_persist_credentials(self):
        self.assertRegex(self.checkout_step, r"(?m)^        with:\s*$")
        self.assertRegex(
            self.checkout_step,
            r"(?m)^          persist-credentials:\s*false\s*$",
        )

    def test_later_ci_steps_do_not_need_authenticated_git(self):
        self.assertNotRegex(
            self.after_checkout,
            r"(?i)\bgit\s+(?:clone|fetch|pull|push|ls-remote)\b",
        )

    def test_full_unittest_suite_runs_on_minimum_and_current_stable_python(self):
        expected_steps = (
            ("3.8", "Set up Python 3.8 for minimum-version unittest",
             "Run unittest suite on Python 3.8"),
            ("3.15", "Set up Python 3.15 for current-stable unittest",
             "Run unittest suite on Python 3.15"),
        )
        for version, setup_name, test_name in expected_steps:
            with self.subTest(python=version):
                pattern = (
                    r"(?ms)^      - name: " + re.escape(setup_name) + r"\n"
                    r".*?^          python-version: \"" + re.escape(version) + r"\"\n\n"
                    r"      - name: " + re.escape(test_name) + r"\n"
                    r"        run: PYTHONDONTWRITEBYTECODE=1 python scripts/run_tests.py$"
                )
                self.assertRegex(self.workflow, pattern)


if __name__ == "__main__":
    unittest.main()
