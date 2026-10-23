import importlib.util
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "bin" / "yuva"


def load_cli(name):
    spec = importlib.util.spec_from_file_location(
        name, CLI_PATH, loader=SourceFileLoader(name, str(CLI_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PanelLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-panel-lifecycle-")
        self.root = Path(self.temp.name)
        self.data = self.root / "yuva-data"
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.data)})
        self.env.start()
        self.yuva = load_cli("yuva_panel_lifecycle_test")
        self.unit = self.root / "yuva-panel.service"
        self.unit.write_text(
            "[Service]\n"
            f"WorkingDirectory={REPO_ROOT}\n"
            f"Environment=YUVA_DIR={self.data}\n"
            f"ExecStart=/usr/bin/python3 -u {REPO_ROOT}/panel/server.py "
            "--host 127.0.0.1 --port 8765\n",
            encoding="utf-8")
        self.unit.chmod(0o644)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()
        self.assertFalse(self.root.exists(), "fixture temporary directory was not removed")

    def _result(self, stdout="", returncode=0):
        return self.yuva.subprocess.CompletedProcess([], returncode, stdout, "")

    def test_exact_unit_for_code_data_and_port_is_recognized(self):
        ok, reason = self.yuva._panel_unit_sahibi(self.unit, 8765)
        self.assertTrue(ok, reason)
        self.assertIn("eşleşiyor", reason)

    def test_unit_for_another_code_data_or_port_is_not_managed(self):
        original = self.unit.read_text(encoding="utf-8")
        self.unit.write_text(original.replace(str(REPO_ROOT), str(self.root / "other")),
                             encoding="utf-8")
        ok, _ = self.yuva._panel_unit_sahibi(self.unit, 8765)
        self.assertFalse(ok)
        self.unit.write_text(original.replace("8765", "8766"), encoding="utf-8")
        ok, _ = self.yuva._panel_unit_sahibi(self.unit, 8765)
        self.assertFalse(ok)

    def test_stop_refuses_a_unit_that_does_not_match_this_yuva(self):
        self.unit.write_text(self.unit.read_text(encoding="utf-8").replace(
            str(REPO_ROOT), str(self.root / "other")), encoding="utf-8")
        args = type("Args", (), {"action": "stop", "port": 8765})()
        with patch.object(self.yuva, "_panel_systemctl",
                          return_value=self._result(str(self.unit))), \
                patch.object(self.yuva, "_doctor_panel_port",
                             return_value=("occupied", "fixture listener")), \
                patch.object(self.yuva.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as raised:
                self.yuva.cmd_panel_service(args)
        self.assertIn("işlem yapılmadı", str(raised.exception))
        run.assert_not_called()

    def test_stop_refuses_unit_with_environment_file(self):
        self.unit.write_text(self.unit.read_text(encoding="utf-8").replace(
            "[Service]\n", "[Service]\nEnvironmentFile=/tmp/yuva.env\n"),
            encoding="utf-8")
        args = type("Args", (), {"action": "stop", "port": 8765})()
        with patch.object(self.yuva, "_panel_systemctl",
                          return_value=self._result(str(self.unit))), \
                patch.object(self.yuva, "_doctor_panel_port",
                             return_value=("occupied", "fixture listener")), \
                patch.object(self.yuva.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as raised:
                self.yuva.cmd_panel_service(args)
        self.assertIn("işlem yapılmadı", str(raised.exception))
        run.assert_not_called()

    def test_stop_targets_only_verified_yuva_systemd_unit(self):
        args = type("Args", (), {"action": "stop", "port": 8765})()
        with patch.object(self.yuva, "_panel_systemctl",
                          side_effect=[self._result(str(self.unit)),
                                       self._result("yuva-panel.service"),
                                       self._result(""),
                                       self._result("no"),
                                       self._result("active")]), \
                patch.object(self.yuva, "_doctor_panel_port",
                             return_value=("occupied", "fixture listener")), \
                patch.object(self.yuva.subprocess, "run",
                             return_value=self._result()) as run:
            self.yuva.cmd_panel_service(args)
        run.assert_called_once_with(
            ["systemctl", "--user", "stop", "yuva-panel.service"],
            capture_output=True, text=True, timeout=30, check=False)

    def test_stop_refuses_when_systemd_unit_needs_reload(self):
        args = type("Args", (), {"action": "stop", "port": 8765})()
        with patch.object(self.yuva, "_panel_systemctl",
                          side_effect=[self._result(str(self.unit)),
                                       self._result("yuva-panel.service"),
                                       self._result(""),
                                       self._result("yes")]), \
                patch.object(self.yuva, "_doctor_panel_port",
                             return_value=("occupied", "fixture listener")), \
                patch.object(self.yuva.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as raised:
                self.yuva.cmd_panel_service(args)
        self.assertIn("işlem yapılmadı", str(raised.exception))
        run.assert_not_called()

    def test_start_refuses_occupied_port_when_yuva_unit_is_inactive(self):
        args = type("Args", (), {"action": "start", "port": 8765})()
        with patch.object(self.yuva, "_panel_systemctl",
                          side_effect=[self._result(str(self.unit)),
                                       self._result("yuva-panel.service"),
                                       self._result(""),
                                       self._result("no"),
                                       self._result("inactive")]), \
                patch.object(self.yuva, "_doctor_panel_port",
                             return_value=("occupied", "fixture listener")), \
                patch.object(self.yuva.subprocess, "run") as run:
            with self.assertRaises(SystemExit) as raised:
                self.yuva.cmd_panel_service(args)
        self.assertIn("sahibi bilinmiyor", str(raised.exception))
        run.assert_not_called()

    def test_start_targets_verified_service_when_fixture_port_is_free(self):
        args = type("Args", (), {"action": "start", "port": 8765})()
        with patch.object(self.yuva, "_panel_systemctl",
                          side_effect=[self._result(str(self.unit)),
                                       self._result("yuva-panel.service"),
                                       self._result(""),
                                       self._result("no"),
                                       self._result("inactive")]), \
                patch.object(self.yuva, "_doctor_panel_port",
                             return_value=("no_listener_observed", "fixture port free")), \
                patch.object(self.yuva.subprocess, "run",
                             return_value=self._result()) as run:
            self.yuva.cmd_panel_service(args)
        run.assert_called_once_with(
            ["systemctl", "--user", "start", "yuva-panel.service"],
            capture_output=True, text=True, timeout=30, check=False)

    def test_status_reports_unknown_listener_without_stopping_processes(self):
        args = type("Args", (), {"action": "status", "port": 8765})()
        with patch.object(self.yuva, "_panel_systemctl",
                          side_effect=[self._result(str(self.unit)),
                                       self._result("yuva-panel.service"),
                                       self._result(""),
                                       self._result("no"),
                                       self._result("loaded"),
                                       self._result("active"),
                                       self._result("running")]), \
                patch.object(self.yuva, "_doctor_panel_port",
                             return_value=("occupied", "fixture listener")), \
                patch("builtins.print") as output, \
                patch.object(self.yuva.subprocess, "run") as run:
            self.yuva.cmd_panel_service(args)
        self.assertTrue(any("PID sahipliği doğrulanmadı" in str(c)
                            for c in output.call_args_list))
        run.assert_not_called()

    def test_procfs_port_fixture_is_read_only_and_detects_listener(self):
        table = self.root / "tcp"
        port_hex = format(8765, "04X")
        table.write_text(
            "sl local_address rem_address st\n"
            f"0: 0100007F:{port_hex} 00000000:0000 0A 0:0 00:00000000 00000000\n",
            encoding="ascii")
        self.assertEqual(self.yuva._doctor_panel_port(8765, [table])[0], "occupied")


if __name__ == "__main__":
    unittest.main()
