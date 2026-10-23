import hashlib
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


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = (REPO_ROOT / "tests" / "fixtures" / "cli-copies"
               / "legacy" / "yuva")
LEGACY_CLI = LEGACY_ROOT / "bin" / "yuva"
LEGACY_PANEL = LEGACY_ROOT / "panel" / "server.py"


def load_legacy_panel(path, data_root):
    with patch.dict(os.environ, {"YUVA_DIR": str(data_root),
                                 "HOME": str(data_root.parent / "home")}):
        spec = importlib.util.spec_from_file_location("yuva_legacy_panel_fixture", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class LegacyTaskWriteGuardTests(unittest.TestCase):
    def test_legacy_cli_and_panel_reject_task_mutations_with_temp_data(self):
        with tempfile.TemporaryDirectory(prefix="yuva-legacy-task-guard-") as td:
            root = Path(td) / "data"
            root.mkdir(mode=0o700)
            ledger = root / "gorevler.json"
            payload = {
                "siradaki": 2,
                "gorevler": [{
                    "id": 1, "baslik": "synthetic fixture", "detay": "",
                    "kimden": "fixture", "assignee": "codex-kole3",
                    "durum": "assigned", "gecmis": [],
                }],
            }
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            before = ledger.read_bytes()
            before_digest = hashlib.sha256(before).hexdigest()

            # The direct legacy CLI entry point must fail before loading or
            # writing the fixture ledger.
            bin_dir = root / "bin"
            bin_dir.mkdir(mode=0o700)
            cli_copy = bin_dir / "yuva"
            shutil.copy2(LEGACY_CLI, cli_copy)
            result = subprocess.run(
                [sys.executable, str(cli_copy), "gorev", "iptal", "1",
                 "--from", "codex-kole3"],
                env={**os.environ, "YUVA_DIR": str(root),
                     "HOME": str(root.parent / "home")},
                capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("görev yazımı reddedildi", result.stderr)
            self.assertEqual(hashlib.sha256(ledger.read_bytes()).hexdigest(),
                             before_digest)

            # The old HTTP route returns before reading the request body or
            # dispatching gorev_calistir; the direct bridge is disabled too.
            panel_dir = root / "panel"
            panel_dir.mkdir(mode=0o700)
            panel_copy = panel_dir / "server.py"
            shutil.copy2(LEGACY_PANEL, panel_copy)
            panel = load_legacy_panel(panel_copy, root)
            body_read = []

            class FakeHandler:
                path = "/api/gorev?ignored=1"

                def _gonder(self, status, body):
                    return status, body

                @property
                def rfile(self):
                    body_read.append(True)
                    raise AssertionError("request body must not be read")

            route_result = panel.H.do_POST(FakeHandler())
            bridge_result = panel.gorev_calistir({
                "islem": "iptal", "id": 1, "kimden": "codex-kole3"})
            self.assertEqual(route_result[0], 410)
            self.assertEqual(route_result[1]["hata"], "legacy_task_writes_disabled")
            self.assertEqual(bridge_result, (410, {
                "ok": False, "hata": "legacy_task_writes_disabled"}))
            self.assertEqual(body_read, [])
            self.assertEqual(hashlib.sha256(ledger.read_bytes()).hexdigest(),
                             before_digest)


if __name__ == "__main__":
    unittest.main()
