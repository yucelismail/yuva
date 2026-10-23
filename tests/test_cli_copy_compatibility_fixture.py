import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI_COPY_FIXTURES = ROOT / "tests" / "fixtures" / "cli-copies"
COPY_SOURCES = {
    "yuva-dev": CLI_COPY_FIXTURES / "yuva-dev" / "bin" / "yuva",
    "yuva-ui-dev": CLI_COPY_FIXTURES / "yuva-ui-dev" / "bin" / "yuva",
    "restore-check-fixture-a": (
        CLI_COPY_FIXTURES / "restore-check.fixture-a" / "yuva" / "bin" / "yuva"),
    "restore-check-fixture-b": (
        CLI_COPY_FIXTURES / "restore-check.fixture-b" / "yuva" / "bin" / "yuva"),
}
LEGACY_CLI = CLI_COPY_FIXTURES / "legacy" / "yuva" / "bin" / "yuva"
CANONICAL_CLI = Path(__file__).resolve().parents[1] / "bin" / "yuva"


class CliCopyCompatibilityFixtureTests(unittest.TestCase):
    def test_historical_cli_copies_are_repository_local_fixtures(self):
        sources = (*COPY_SOURCES.values(), LEGACY_CLI)
        for source in sources:
            with self.subTest(fixture=source.name):
                self.assertIn(CLI_COPY_FIXTURES, source.parents)
                self.assertTrue(source.is_file(), source.name)

    def temp_copy(self, temp_root, label, source):
        target = temp_root / label / "bin" / "yuva"
        target.parent.mkdir(parents=True)
        shutil.copy2(source, target)
        return target

    def run_cli(self, cli, data_root, *args):
        home = data_root.parent / "home"
        home.mkdir(exist_ok=True)
        env = os.environ.copy()
        env.update({"YUVA_DIR": str(data_root), "HOME": str(home),
                    "YUVA_AUTH_ENABLED": "0"})
        return subprocess.run([sys.executable, str(cli), *args], env=env,
                              capture_output=True, text=True, timeout=10)

    def test_dev_copies_fail_closed_before_unknown_schema_ledger_changes(self):
        for label, source in ((name, path) for name, path in COPY_SOURCES.items()
                              if name in {"yuva-dev", "yuva-ui-dev"}):
            with self.subTest(cli=label), tempfile.TemporaryDirectory(
                    prefix="yuva-copy-schema-") as temp:
                root = Path(temp)
                data = root / "data"
                data.mkdir(mode=0o700)
                ledger = data / "gorevler.json"
                initial = {
                    "schema_version": 99, "siradaki": 2,
                    "gorevler": [{"id": 1, "baslik": "fixture task",
                                  "kimden": "fixture-owner", "assignee": None,
                                  "durum": "pending", "gecmis": []}],
                }
                ledger.write_text(json.dumps(initial), encoding="utf-8")
                initial_bytes = ledger.read_bytes()
                copied = self.temp_copy(root, label, source)

                result = self.run_cli(copied, data, "gorev", "al", "1",
                                      "--from", "fixture-agent")

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("görev yazımı reddedildi: kanonik writer kullanın",
                              result.stderr)
                self.assertEqual(ledger.read_bytes(), initial_bytes)

    def test_canonical_cli_accepts_supported_schema_v1_writer_path(self):
        with tempfile.TemporaryDirectory(prefix="yuva-canonical-schema-v1-") as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir(mode=0o700)
            ledger = data / "gorevler.json"
            initial = {
                "schema_version": 1, "siradaki": 2,
                "gorevler": [{"id": 1, "baslik": "fixture task",
                              "kimden": "fixture-owner", "assignee": None,
                              "durum": "pending", "gecmis": []}],
            }
            ledger.write_text(json.dumps(initial), encoding="utf-8")
            (data / "durum.json").write_text(json.dumps({
                "schema_version": 1, "rev": 0,
                "kullanicilar": {"fixture-agent": {"rol": "isci"}},
            }), encoding="utf-8")

            result = self.run_cli(CANONICAL_CLI, data, "gorev", "al", "1",
                                  "--from", "fixture-agent")

            self.assertEqual(result.returncode, 0, result.stderr)
            after = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(after["schema_version"], 1)
            self.assertEqual(after["gorevler"][0]["durum"], "assigned")
            self.assertEqual(after["gorevler"][0]["assignee"], "fixture-agent")

    def test_canonical_cli_rejects_unsupported_schema_without_byte_changes(self):

        with tempfile.TemporaryDirectory(prefix="yuva-canonical-schema-") as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir(mode=0o700)
            ledger = data / "gorevler.json"
            initial = {"schema_version": 99, "siradaki": 2,
                       "gorevler": [{"id": 1, "baslik": "fixture task",
                                     "kimden": "fixture-owner", "assignee": None,
                                     "durum": "pending", "gecmis": []}]}
            ledger.write_text(json.dumps(initial), encoding="utf-8")
            (data / "durum.json").write_text(json.dumps({
                "schema_version": 1, "rev": 0,
                "kullanicilar": {"fixture-agent": {"rol": "isci"}},
            }), encoding="utf-8")
            initial_bytes = ledger.read_bytes()

            result = self.run_cli(CANONICAL_CLI, data, "gorev", "al", "1",
                                  "--from", "fixture-agent")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("desteklenmeyen schema_version", result.stderr)
            self.assertEqual(ledger.read_bytes(), initial_bytes)

    def test_restore_copies_fail_open_on_corrupt_ledger_in_temp_only(self):
        for label, source in ((name, path) for name, path in COPY_SOURCES.items()
                              if name.startswith("restore-check-")):
            with self.subTest(cli=label), tempfile.TemporaryDirectory(
                    prefix="yuva-copy-corrupt-") as temp:
                root = Path(temp)
                data = root / "data"
                data.mkdir(mode=0o700)
                ledger = data / "gorevler.json"
                ledger.write_bytes(b'{"corrupt":')
                copied = self.temp_copy(root, label, source)

                result = self.run_cli(copied, data, "gorev", "ekle", "synthetic",
                                      "--from", "fixture-agent")

                self.assertEqual(result.returncode, 0, result.stderr)
                after = json.loads(ledger.read_text(encoding="utf-8"))
                self.assertEqual(len(after["gorevler"]), 1)
                self.assertNotIn("corrupt", after)

    def test_legacy_mutation_guard_rejects_before_fixture_ledger_changes(self):
        with tempfile.TemporaryDirectory(prefix="yuva-legacy-guard-") as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir(mode=0o700)
            ledger = data / "gorevler.json"
            initial = {"siradaki": 1, "gorevler": []}
            ledger.write_text(json.dumps(initial), encoding="utf-8")
            copied = self.temp_copy(root, "legacy", LEGACY_CLI)

            result = self.run_cli(copied, data, "gorev", "ekle", "synthetic",
                                  "--from", "fixture-agent")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("görev yazımı reddedildi", result.stderr)
            self.assertEqual(json.loads(ledger.read_text(encoding="utf-8")), initial)


if __name__ == "__main__":
    unittest.main()
