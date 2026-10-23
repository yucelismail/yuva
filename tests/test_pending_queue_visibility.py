import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "bin" / "yuva"


def load_cli(path):
    spec = importlib.util.spec_from_file_location(
        "yuva_pending_queue_cli", path,
        loader=SourceFileLoader("yuva_pending_queue_cli", str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PendingQueueVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-pending-queue-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.root),
                                           "YUVA_AUTH_ENABLED": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cli = load_cli(CLI_PATH)
        self.cli.KOK = self.root
        self.cli.GOREV = self.root / "gorevler.json"

    def write_ledger(self, tasks):
        self.cli.GOREV.write_text(json.dumps({
            "schema_version": 1,
            "siradaki": len(tasks) + 1,
            "gorevler": tasks,
        }), encoding="utf-8")
        self.cli.GOREV.chmod(0o600)

    @staticmethod
    def task(task_id, status="pending"):
        return {"id": task_id, "baslik": f"fixture-{task_id}",
                "kimden": "owner", "assignee": None,
                "durum": status, "gecmis": []}

    def board_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.cli.cmd_tahta(None)
        return output.getvalue()

    def test_warning_boundary_is_below_twelve_only_and_does_not_mutate(self):
        for count, should_warn in ((11, True), (12, False), (13, False)):
            with self.subTest(pending=count):
                self.write_ledger([self.task(i + 1) for i in range(count)])
                before = self.cli.GOREV.read_bytes()
                output = self.board_output()
                self.assertEqual("Atama bekleyen görev sayısı düşük" in output,
                                 should_warn)
                if should_warn:
                    self.assertIn("11 (alt sınır 12)", output)
                self.assertEqual(self.cli.GOREV.read_bytes(), before)

    def test_assigned_tasks_do_not_count_as_pending_queue(self):
        tasks = [self.task(i + 1, "assigned") for i in range(12)]
        for task in tasks:
            task["assignee"] = "worker"
        self.write_ledger(tasks)

        output = self.board_output()

        self.assertIn("Atama bekleyen görev sayısı düşük: 0", output)
        self.assertNotIn("Atama bekleyen görev sayısı düşük: 12", output)

    def test_claim_moves_one_task_from_pending_count_to_assigned(self):
        self.write_ledger([self.task(i + 1) for i in range(12)])
        (self.root / "durum.json").write_text(json.dumps({
            "schema_version": 1,
            "kullanicilar": {"worker": {"rol": "isci"}},
            "rev": 0,
        }), encoding="utf-8")
        (self.root / "durum.json").chmod(0o600)

        before = self.board_output()
        self.assertNotIn("Atama bekleyen görev sayısı düşük", before)
        claimed = subprocess.run(
            [sys.executable, str(CLI_PATH), "gorev", "al", "1",
             "--from", "worker"], env=os.environ.copy(), capture_output=True,
            text=True, timeout=10)
        self.assertEqual(claimed.returncode, 0, claimed.stderr)

        output = self.board_output()
        self.assertIn("Atama bekleyen görev sayısı düşük: 11", output)
        ledger = json.loads(self.cli.GOREV.read_text(encoding="utf-8"))
        self.assertEqual(sum(g["durum"] == "pending"
                             for g in ledger["gorevler"]), 11)
        self.assertEqual(ledger["gorevler"][0]["durum"], "assigned")


if __name__ == "__main__":
    unittest.main()
