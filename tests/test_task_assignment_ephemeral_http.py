"""Canonical CLI claim -> real panel Handler -> UI task contract fixture."""

import http.client
import importlib.util
import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.http_fixture_lifecycle import start_server


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "yuva"
PANEL = ROOT / "panel" / "server.py"


def load_panel(name):
    spec = importlib.util.spec_from_file_location(
        name, PANEL, loader=SourceFileLoader(name, str(PANEL)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TaskAssignmentEphemeralHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-assignment-http-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        (self.root / "ekran").mkdir(mode=0o700)

        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(self.root),
            "YUVA_AUTH_ENABLED": "0",
            "YUVA_SNAPSHOT_BUDGET_ENABLED": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

        self.panel_name = f"yuva_assignment_http_panel_{id(self)}"
        self.panel = load_panel(self.panel_name)
        self.addCleanup(sys.modules.pop, self.panel_name, None)
        self.panel.KOK = self.root
        self.panel.DURUM = self.root / "durum.json"
        self.panel.GOREV = self.root / "gorevler.json"
        self.panel.BUS = self.root / "mesaj.jsonl"
        self.panel.EKRAN = self.root / "ekran"
        self.panel.KILIT_DOSYA = self.root / ".kilit"
        self.panel._TASK_CORE = None

        class FixtureBrowserSessionGate:
            def authorize_get(_self, route, scope, cookie):
                return cookie == "yuva_session=fixture-session"

        self.old_handler_values = (
            self.panel.H.AUTH_GATE,
            self.panel.H.BROWSER_SESSION_GATE,
            self.panel.H.SUNUCU_PORT,
            self.panel.H.IZINLI_HOSTLAR,
        )
        self.panel.H.AUTH_GATE = None
        self.panel.H.BROWSER_SESSION_GATE = FixtureBrowserSessionGate()
        self.panel.H.IZINLI_HOSTLAR = {"localhost", "127.0.0.1"}
        self.server = self.panel.Sunucu(("127.0.0.1", 0), self.panel.H)
        self.panel.H.SUNUCU_PORT = self.server.server_port
        self.addCleanup(self._restore_handler_values)
        self.thread = start_server(self, self.server)

    def _restore_handler_values(self):
        (self.panel.H.AUTH_GATE,
         self.panel.H.BROWSER_SESSION_GATE,
         self.panel.H.SUNUCU_PORT,
         self.panel.H.IZINLI_HOSTLAR) = self.old_handler_values

    @staticmethod
    def _write_private(path, content):
        path.write_bytes(content)
        path.chmod(0o600)

    def _write_board(self):
        state = {
            "schema_version": 1,
            "rev": 0,
            "kullanicilar": {
                "reviewer": {"ad": "Reviewer", "rol": "denetci"},
                "worker-b": {"ad": "Worker B", "rol": "isci"},
            },
        }
        ledger = {
            "schema_version": 1,
            "siradaki": 718,
            "gorevler": [{
                "id": 717,
                "baslik": "synthetic pending task",
                "detay": "fixture only",
                "kimden": "reviewer",
                "assignee": None,
                "durum": "pending",
                "gecmis": [],
            }],
        }
        self._write_private(self.root / "durum.json", json.dumps(state).encode())
        self._write_private(self.root / "gorevler.json", json.dumps(ledger).encode())

    def _get(self, path):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        connection.request("GET", path, headers={
            "Host": f"127.0.0.1:{self.server.server_port}",
            "Cookie": "yuva_session=fixture-session",
        })
        response = connection.getresponse()
        status = response.status
        headers = dict(response.getheaders())
        body = response.read()
        connection.close()
        return status, headers, body

    def test_cli_assignment_survives_real_handler_projection_and_ui_contract(self):
        self._write_board()
        ledger_path = self.root / "gorevler.json"
        before = ledger_path.read_bytes()

        claim = subprocess.run(
            [sys.executable, str(CLI), "gorev", "al", "717", "--from", "worker-b"],
            cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True,
            timeout=10, check=False)
        self.assertEqual(claim.returncode, 0, claim.stderr or claim.stdout)
        stored = json.loads(ledger_path.read_bytes())
        stored_task = next(task for task in stored["gorevler"] if task["id"] == 717)
        self.assertEqual((stored_task["durum"], stored_task["assignee"]),
                         ("assigned", "worker-b"))
        self.assertNotEqual(ledger_path.read_bytes(), before)
        ledger_after_claim = ledger_path.read_bytes()

        status, headers, body = self._get("/api/veri")
        self.assertEqual(status, 200, body)
        self.assertEqual(int(headers["Content-Length"]), len(body))
        snapshot = json.loads(body)
        projected_task = next(task for task in snapshot["gorevler"]
                              if task["id"] == 717)
        self.assertEqual((projected_task["durum"], projected_task["assignee"]),
                         ("assigned", "worker-b"))

        html_status, html_headers, html_body = self._get("/")
        self.assertEqual(html_status, 200)
        self.assertEqual(int(html_headers["Content-Length"]), len(html_body))
        ui = html_body.decode("utf-8")
        self.assertIn('"assigned"', ui)
        self.assertIn('gs.filter(function(g){return g.durum===st;})', ui)
        self.assertIn("g.assignee?kisiAd(veri,g.assignee)", ui)
        self.assertIn("esc(g.id)", ui)
        self.assertIn("esc(g.assignee||\"\")", ui)
        self.assertEqual(ledger_path.read_bytes(), ledger_after_claim)


if __name__ == "__main__":
    unittest.main()
