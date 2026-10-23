"""Disposable handler/ledger fixture for task board live-update consistency."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from importlib.machinery import SourceFileLoader
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "bin" / "yuva"
PANEL_PATH = ROOT / "panel" / "server.py"
UI_PATH = ROOT / "panel" / "ui.html"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TaskBoardLiveUpdateConsistencyFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-board-live-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        (self.root / "ekran").mkdir(mode=0o700)
        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(self.root),
            "YUVA_AUTH_ENABLED": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

        self.panel_name = f"yuva_board_live_panel_{id(self)}"
        self.panel = load_module(self.panel_name, PANEL_PATH)
        self.addCleanup(sys.modules.pop, self.panel_name, None)
        self.panel.KOK = self.root
        self.panel.DURUM = self.root / "durum.json"
        self.panel.GOREV = self.root / "gorevler.json"
        self.panel.BUS = self.root / "mesaj.jsonl"
        self.panel.EKRAN = self.root / "ekran"
        self.panel.KILIT_DOSYA = self.root / ".kilit"
        self.panel._TASK_CORE = None

    def write_state(self, users):
        state = {
            "schema_version": 1,
            "rev": 0,
            "kullanicilar": {
                user: {"ad": user, "rol": role}
                for user, role in users.items()
            },
        }
        path = self.root / "durum.json"
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)

    def write_ledger(self, tasks):
        ledger = {"schema_version": 1, "siradaki": max(
            (task["id"] for task in tasks), default=0) + 1,
            "gorevler": tasks}
        path = self.root / "gorevler.json"
        path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)
        return path.read_bytes()

    def task(self, task_id, status="pending", assignee=None):
        return {
            "id": task_id,
            "baslik": f"synthetic task {task_id}",
            "kimden": "synthetic-owner",
            "assignee": assignee,
            "durum": status,
            "gecmis": [],
        }

    def snapshot(self):
        result = self.panel.veri()
        self.assertTrue(result["ok"])
        return result

    def cli_claim(self, task_id, worker):
        return subprocess.run(
            [sys.executable, str(CLI_PATH), "gorev", "al", str(task_id),
             "--from", worker], env=os.environ.copy(), capture_output=True,
            text=True, timeout=10)

    def test_assignment_delivery_and_snapshot_status_assignee_views_stay_consistent(self):
        self.write_state({"reviewer": "denetci", "worker-a": "isci",
                          "worker-b": "isci"})
        self.write_ledger([
            self.task(10, "pending"),
            self.task(11, "assigned", "worker-a"),
            self.task(12, "pending_revision", "worker-b"),
        ])

        status, response = self.panel.gorev_calistir({
            "islem": "ata", "id": 10, "kimden": "reviewer",
            "kime": "worker-b",
        })
        self.assertEqual(status, 200, response)
        board = self.snapshot()
        tasks = board["gorevler"]
        by_status = {
            state: {task["id"] for task in tasks if task["durum"] == state}
            for state in ("pending", "assigned", "pending_revision",
                          "pending_verification")
        }
        self.assertEqual(by_status["pending"], set())
        self.assertEqual(by_status["assigned"], {10, 11})
        self.assertEqual(by_status["pending_revision"], {12})
        self.assertEqual(by_status["pending_verification"], set())
        worker_b_tasks = [task for task in tasks if task.get("assignee") == "worker-b"]
        self.assertEqual({task["id"] for task in worker_b_tasks}, {10, 12})
        self.assertEqual(next(task for task in tasks if task["id"] == 10)["assignee"],
                         "worker-b")

        delivered = self.cli_claim(10, "worker-b")
        self.assertEqual(delivered.returncode, 1, delivered.stderr)
        # A pre-assigned task cannot be claimed again; assignment view remains stable.
        snapshot_after_rejected_claim = self.snapshot()
        task_10 = next(task for task in snapshot_after_rejected_claim["gorevler"]
                       if task["id"] == 10)
        self.assertEqual((task_10["durum"], task_10["assignee"]),
                         ("assigned", "worker-b"))

        delivered_status, delivered_response = self.panel.gorev_calistir({
            "islem": "teslim", "id": 10, "kimden": "worker-b",
            "not_": "synthetic delivery",
        })
        self.assertEqual(delivered_status, 200, delivered_response)
        after_delivery = self.snapshot()
        task_10 = next(task for task in after_delivery["gorevler"]
                       if task["id"] == 10)
        self.assertEqual((task_10["durum"], task_10["assignee"]),
                         ("pending_verification", "worker-b"))
        self.assertEqual(len(task_10["gecmis"]), 2)

        ui = UI_PATH.read_text(encoding="utf-8")
        self.assertIn('var TAHTA_AKTIF=["pending","assigned","pending_gorevli_review","pending_verification","pending_revision"]', ui)
        self.assertIn('var kol=gs.filter(function(g){return g.durum===st;})', ui)
        self.assertIn('gs.filter(function(g){return g.assignee===k;})', ui)
        self.assertIn('g.durum==="pending_revision"', ui)
        self.assertIn('g.durum==="pending_verification"', ui)

    def test_concurrent_panel_and_cli_claims_have_one_winner_and_one_snapshot_owner(self):
        self.write_state({"worker-a": "isci", "worker-b": "isci"})
        ledger_path = self.root / "gorevler.json"
        initial = self.write_ledger([self.task(20)])
        barrier = threading.Barrier(2)

        def panel_claim():
            barrier.wait(timeout=5)
            return self.panel.gorev_calistir({
                "islem": "al", "id": 20, "kimden": "worker-a"})

        def cli_claim():
            barrier.wait(timeout=5)
            return self.cli_claim(20, "worker-b")

        with ThreadPoolExecutor(max_workers=2) as pool:
            panel_future = pool.submit(panel_claim)
            cli_future = pool.submit(cli_claim)
            panel_result = panel_future.result(timeout=15)
            cli_result = cli_future.result(timeout=15)

        panel_won = panel_result[0] == 200
        cli_won = cli_result.returncode == 0
        self.assertEqual(int(panel_won) + int(cli_won), 1,
                         (panel_result, cli_result.stderr))
        current = json.loads(ledger_path.read_text(encoding="utf-8"))
        task = current["gorevler"][0]
        self.assertEqual(task["durum"], "assigned")
        self.assertIn(task["assignee"], {"worker-a", "worker-b"})
        self.assertEqual(len(task["gecmis"]), 1)
        board = self.snapshot()
        board_task = board["gorevler"][0]
        self.assertEqual((board_task["durum"], board_task["assignee"]),
                         ("assigned", task["assignee"]))
        if panel_won:
            self.assertEqual(board_task["assignee"], "worker-a")
        else:
            self.assertEqual(board_task["assignee"], "worker-b")
        self.assertNotEqual(ledger_path.read_bytes(), initial)

    def test_rejected_wrong_assignee_mutation_leaves_ledger_bytes_unchanged(self):
        self.write_state({"worker-a": "isci", "worker-b": "isci"})
        self.write_ledger([self.task(30, "assigned", "worker-a")])
        path = self.root / "gorevler.json"
        before = path.read_bytes()

        status, response = self.panel.gorev_calistir({
            "islem": "al", "id": 30, "kimden": "worker-b"})

        self.assertEqual(status, 400, response)
        self.assertFalse(response["ok"])
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / "mesaj.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
