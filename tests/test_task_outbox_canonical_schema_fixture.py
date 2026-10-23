"""Compare the disposable outbox prototype with a canonical CLI v1 task."""

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "bin" / "yuva"
OUTBOX_DIR = ROOT / "prototypes" / "task-outbox"
sys.path.insert(0, str(OUTBOX_DIR))
from task_outbox import TaskOutbox  # noqa: E402
import outbox_schema  # noqa: E402


def load_cli(path):
    spec = importlib.util.spec_from_file_location("yuva_outbox_canonical_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskOutboxCanonicalSchemaFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-outbox-canonical-schema-")
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.canonical_root = self.parent / "canonical"
        self.prototype_root = self.parent / "prototype"
        self.canonical_root.mkdir(mode=0o700)
        self.prototype_root.mkdir(mode=0o700)
        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(self.canonical_root),
            "YUVA_AUTH_ENABLED": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_canonical_cli_task_round_trips_additively_through_prototype(self):
        created = subprocess.run(
            [sys.executable, str(CLI_PATH), "gorev", "ekle", "synthetic task",
             "--from", "synthetic-owner"], env=os.environ.copy(),
            capture_output=True, text=True, timeout=10)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("#1 eklendi", created.stdout)

        canonical_path = self.canonical_root / "gorevler.json"
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        task_before = canonical["gorevler"][0]
        for field in ("id", "baslik", "kimden", "durum", "gecmis",
                      "assignee", "gorevli_kimlik", "ust_gorev_id",
                      "olusturma", "guncelleme"):
            self.assertIn(field, task_before)
        self.assertEqual(canonical["schema_version"], 1)
        self.assertEqual(canonical["siradaki"], 2)

        canonical["canonical_extension"] = {"preserve": ["synthetic", 7]}
        prototype_path = self.prototype_root / "gorevler.json"
        prototype_path.write_text(json.dumps(canonical, ensure_ascii=False),
                                  encoding="utf-8")
        prototype_path.chmod(0o600)
        shutil.copyfile(self.canonical_root / ".kilit",
                        self.prototype_root / ".kilit")
        (self.prototype_root / "mesaj.jsonl").touch(mode=0o600)

        store = TaskOutbox(self.prototype_root)
        self.assertEqual(store.apply_operation(
            "synthetic-op", 1, "assigned", "synthetic-event",
            "synthetic notification" )["status"], "committed")
        state = store.snapshot()
        outbox_schema.validate_extensions(state)

        task_after = state["gorevler"][0]
        for field in ("id", "baslik", "kimden", "assignee", "gorevli_kimlik",
                      "ust_gorev_id", "olusturma", "guncelleme"):
            self.assertEqual(task_after[field], task_before[field], field)
        self.assertEqual(task_after["durum"], "assigned")
        self.assertEqual(len(task_after["gecmis"]), len(task_before["gecmis"]) + 1)
        self.assertEqual(state["schema_version"], 1)
        self.assertEqual(state["siradaki"], 2)
        self.assertEqual(state["canonical_extension"], {"preserve": ["synthetic", 7]})
        self.assertEqual(len(state["operations"]), 1)
        self.assertEqual(len(state["outbox"]), 1)
        receipt = state["operations"]["synthetic-op"]
        event = state["outbox"][0]
        for entry in (receipt, event):
            encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.assertLessEqual(len(encoded), outbox_schema.MAX_ENTRY_BYTES)
        self.assertLessEqual(len(event["message"].encode("utf-8")),
                             outbox_schema.MAX_MESSAGE_BYTES)
        self.assertLessEqual(len(state["operations"]), outbox_schema.MAX_OPERATIONS)
        self.assertLessEqual(len(state["outbox"]), outbox_schema.MAX_OUTBOX_EVENTS)

    def test_read_mutate_and_replace_stay_inside_one_prototype_lock(self):
        ledger = {
            "schema_version": 1, "siradaki": 2,
            "gorevler": [{"id": 1, "baslik": "synthetic", "kimden": "owner",
                           "assignee": None, "durum": "pending", "gecmis": []}],
        }
        path = self.prototype_root / "gorevler.json"
        path.write_text(json.dumps(ledger), encoding="utf-8")
        store = TaskOutbox(self.prototype_root)

        def assert_lock_held():
            fd = os.open(store.lock_path, os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)

        original_read = store._read_state
        original_replace = store._replace
        with patch.object(store, "_read_state", side_effect=lambda: (
                assert_lock_held(), original_read())[1]) as read_spy, \
             patch.object(store, "_replace", side_effect=lambda state: (
                assert_lock_held(), original_replace(state))[1]) as replace_spy:
            store.apply_operation("lock-op", 1, "assigned", "lock-event", "notice")
            store.lookup("lock-op")

        self.assertGreaterEqual(read_spy.call_count, 2)
        self.assertEqual(replace_spy.call_count, 1)


if __name__ == "__main__":
    unittest.main()
