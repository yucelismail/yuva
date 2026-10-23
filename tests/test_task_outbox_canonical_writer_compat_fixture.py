"""Disposable-data fixture for canonical task writer/outbox-field compatibility."""

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "bin" / "yuva"


class CanonicalTaskOutboxCompatibilityFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-outbox-canonical-")
        self.addCleanup(self.temp.cleanup)
        self.data_root = Path(self.temp.name) / "data"
        self.data_root.mkdir(mode=0o700)
        self.data_root.chmod(0o700)
        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(self.data_root),
            "YUVA_AUTH_ENABLED": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

        name = f"yuva_task_outbox_canonical_{id(self)}"
        spec = importlib.util.spec_from_file_location(
            name, CLI_PATH, loader=SourceFileLoader(name, str(CLI_PATH)))
        self.cli = importlib.util.module_from_spec(spec)
        sys.modules[name] = self.cli
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(self.cli)
        self.cli.KOK = self.data_root
        self.cli.GOREV = self.data_root / "gorevler.json"
        self.cli.KILIT = self.data_root / ".kilit"

    def ledger(self, *, schema_version=1):
        value = {
            "siradaki": 2,
            "gorevler": [{
                "id": 1,
                "baslik": "synthetic task",
                "kimden": "synthetic owner",
                "durum": "pending",
                "gecmis": [],
            }],
            "operations": {
                "synthetic-op-001": {
                    "operation": "fixture-operation",
                    "digest": "SYNTHETIC_DIGEST",
                    "task_id": 1,
                    "result": "committed",
                },
            },
            "outbox": [{
                "event_id": "synthetic-event-001",
                "operation_id": "synthetic-op-001",
                "state": "pending",
                "message": {
                    "id": "synthetic-event-001",
                    "metin": "synthetic notification body",
                },
            }],
            "unknown_extension": {"nested": ["synthetic", 7, None]},
        }
        if schema_version is not None:
            value["schema_version"] = schema_version
        return value

    def write(self, value, *, raw=None):
        raw = raw if raw is not None else json.dumps(
            value, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        self.cli.GOREV.write_bytes(raw)
        self.cli.GOREV.chmod(0o600)
        return raw

    def assert_lock_held(self):
        fd = os.open(self.data_root / ".kilit", os.O_RDWR)
        try:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)

    def test_canonical_reader_and_writer_preserve_additive_v1_root_fields(self):
        for version in (None, 1):
            with self.subTest(schema_version=version):
                ledger = self.ledger(schema_version=version)
                self.write(ledger)
                loaded = self.cli.gorev_yukle()
                self.assertEqual(loaded["operations"], ledger["operations"])
                self.assertEqual(loaded["outbox"], ledger["outbox"])
                self.assertEqual(loaded["unknown_extension"],
                                 ledger["unknown_extension"])

                before_stat = self.cli.GOREV.stat()
                result = self.cli.gorev_guncelle(
                    lambda current: self._mutate_under_lock(current))
                self.assertEqual(result, "fixture-mutated")

                after = json.loads(self.cli.GOREV.read_text(encoding="utf-8"))
                after_stat = self.cli.GOREV.stat()
                self.assertEqual(after["schema_version"], 1)
                self.assertEqual(after["operations"], ledger["operations"])
                self.assertEqual(after["outbox"], ledger["outbox"])
                self.assertEqual(after["unknown_extension"],
                                 ledger["unknown_extension"])
                self.assertEqual(after["gorevler"][0]["durum"], "assigned")
                self.assertEqual(len(after["gorevler"][0]["gecmis"]), 1)
                self.assertNotEqual((before_stat.st_dev, before_stat.st_ino),
                                    (after_stat.st_dev, after_stat.st_ino))
                self.assertEqual(list(self.data_root.glob("gorevler.json.*.tmp")), [])

    def _mutate_under_lock(self, current):
        self.assert_lock_held()
        task = current["gorevler"][0]
        task["durum"] = "assigned"
        task["gecmis"].append({
            "ts": "synthetic-time",
            "kimden": "synthetic-actor",
            "olay": "fixture-transition",
            "actor_trust": "local_unverified",
            "not": "synthetic note",
        })
        return "fixture-mutated"

    def test_canonical_save_runs_under_lock_and_replaces_one_complete_snapshot(self):
        self.write(self.ledger())
        real_save = self.cli.kaydet
        saves = []

        def checked_save(path, value):
            self.assertEqual(Path(path), self.cli.GOREV)
            self.assert_lock_held()
            saves.append(value)
            return real_save(path, value)

        with patch.object(self.cli, "kaydet", side_effect=checked_save):
            self.cli.gorev_guncelle(
                lambda current: current["gorevler"][0].update({"durum": "assigned"}))

        self.assertEqual(len(saves), 1)
        stored = json.loads(self.cli.GOREV.read_text(encoding="utf-8"))
        self.assertEqual(stored["gorevler"][0]["durum"], "assigned")
        self.assertEqual(stored["operations"], self.ledger()["operations"])
        self.assertEqual(stored["outbox"], self.ledger()["outbox"])

    def test_unknown_schema_is_rejected_before_callback_with_byte_for_byte_no_write(self):
        raw = self.write(self.ledger(schema_version=99))
        called = []
        with self.assertRaises(self.cli.VeriHatasi):
            self.cli.gorev_guncelle(lambda current: called.append(True))
        self.assertEqual(called, [])
        self.assertEqual(self.cli.GOREV.read_bytes(), raw)
        self.assertEqual(list(self.data_root.glob("gorevler.json.*.tmp")), [])

    def test_replace_failure_keeps_original_outbox_snapshot_bytes(self):
        raw = self.write(self.ledger())
        with patch.object(self.cli.os, "replace",
                          side_effect=OSError("synthetic replace failure")):
            with self.assertRaises(OSError):
                self.cli.gorev_guncelle(
                    lambda current: current["gorevler"][0].update({
                        "durum": "assigned"}))
        self.assertEqual(self.cli.GOREV.read_bytes(), raw)
        self.assertEqual(list(self.data_root.glob("gorevler.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
