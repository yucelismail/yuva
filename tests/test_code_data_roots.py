import importlib.util
import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "bin" / "yuva"
PANEL_PATH = REPO_ROOT / "panel" / "server.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CodeDataRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_root = self.root / "shared-data"
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.data_root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_cli_uses_candidate_code_root_and_separate_shared_data_root(self):
        yuva = load_module("yuva_roots_cli", CLI_PATH)

        self.assertEqual(yuva.CODE_ROOT, REPO_ROOT)
        self.assertEqual(yuva.KOK, self.data_root)
        self.assertEqual(yuva.CALISAN, CLI_PATH)
        self.assertEqual(yuva.STATE, self.data_root / "durum.json")
        self.assertEqual(yuva.GOREV, self.data_root / "gorevler.json")
        self.assertEqual(yuva.BUS, self.data_root / "mesaj.jsonl")
        self.assertEqual(yuva.EKRAN, self.data_root / "ekran")

    def test_cli_panel_command_selects_candidate_panel_and_keeps_data_env(self):
        yuva = load_module("yuva_roots_cli_panel", CLI_PATH)
        args = SimpleNamespace(port=8765)

        with patch.object(yuva.os, "execv") as execv:
            yuva.cmd_panel(args)

        execv.assert_called_once_with(
            yuva.sys.executable,
            [yuva.sys.executable, str(REPO_ROOT / "panel" / "server.py"),
             "--port", "8765"])
        self.assertEqual(os.environ["YUVA_DIR"], str(self.data_root))

    def test_panel_local_mvp_task_write_records_unverified_actor_label(self):
        panel = load_module("yuva_roots_panel_cli", PANEL_PATH)

        with patch.dict(os.environ, {"YUVA_AUTH_ENABLED": "0"}):
            status, result = panel.gorev_calistir({
                "islem": "ekle", "baslik": "fixture local task",
                "kimden": "local-worker"})

        self.assertEqual(status, 200, result)
        task = json.loads((self.data_root / "gorevler.json").read_text())["gorevler"][0]
        self.assertEqual(task["kimden"], "local-worker")
        self.assertEqual(task["gecmis"][0]["actor_trust"], "local_unverified")

    def test_panel_reads_ui_from_code_root_not_shared_data_root(self):
        panel = load_module("yuva_roots_panel_ui", PANEL_PATH)
        data_ui = self.data_root / "panel" / "ui.html"
        data_ui.parent.mkdir(parents=True)
        data_ui.write_text("data-root UI decoy", encoding="utf-8")

        self.assertEqual(panel.KOK, self.data_root)
        self.assertEqual(panel.CODE_ROOT, REPO_ROOT)
        self.assertEqual(panel.sayfa(),
                         (REPO_ROOT / "panel" / "ui.html").read_text(encoding="utf-8"))
        self.assertNotEqual(panel.sayfa(), "data-root UI decoy")

    def test_missing_yuva_dir_keeps_home_yuva_as_default_data_root(self):
        self.env.stop()
        with patch.dict(os.environ, {"YUVA_DIR": ""}), \
                patch.object(Path, "home", return_value=self.root):
            yuva = load_module("yuva_roots_cli_default", CLI_PATH)
            panel = load_module("yuva_roots_panel_default", PANEL_PATH)

        self.assertEqual(yuva.CODE_ROOT, REPO_ROOT)
        self.assertEqual(yuva.KOK, self.root / "yuva")
        self.assertEqual(panel.CODE_ROOT, REPO_ROOT)
        self.assertEqual(panel.KOK, self.root / "yuva")


if __name__ == "__main__":
    unittest.main()
