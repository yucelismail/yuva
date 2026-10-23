"""Prove panel HTTP fixtures avoid occupied ports and release their sockets."""

import http.client
import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "panel" / "server.py"


def load_panel(name):
    spec = importlib.util.spec_from_file_location(
        name, SERVER_PATH, loader=SourceFileLoader(name, str(SERVER_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PanelEphemeralPortCollisionTests(unittest.TestCase):
    def test_ephemeral_loopback_server_avoids_collision_and_releases_port(self):
        with tempfile.TemporaryDirectory(prefix="yuva-panel-port-collision-") as temp:
            env = patch.dict(os.environ, {
                "YUVA_DIR": str(Path(temp) / "synthetic-yuva"),
                "YUVA_AUTH_ENABLED": "0",
            })
            env.start()
            panel = load_panel(f"yuva_panel_port_collision_{id(self)}")
            occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server = None
            thread = None
            try:
                occupied.bind(("127.0.0.1", 0))
                occupied.listen(1)
                occupied_port = occupied.getsockname()[1]

                panel.H.AUTH_GATE = None
                panel.H.BROWSER_SESSION_GATE = None
                panel.H.IZINLI_HOSTLAR = {"localhost", "127.0.0.1"}
                server = panel.Sunucu(("127.0.0.1", 0), panel.H)
                server_port = server.server_port
                panel.H.SUNUCU_PORT = server_port
                self.assertNotEqual(server_port, occupied_port)
                self.assertEqual(server.server_address[0], "127.0.0.1")

                thread = threading.Thread(target=server.serve_forever, daemon=False)
                thread.start()
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server_port, timeout=3)
                try:
                    connection.request("GET", "/__ephemeral_fixture_missing__", headers={
                        "Host": f"127.0.0.1:{server_port}",
                    })
                    response = connection.getresponse()
                    body = response.read()
                finally:
                    connection.close()
                self.assertEqual(response.status, 404)
                self.assertNotIn(b"Traceback", body)
            finally:
                if server is not None:
                    if thread is not None and thread.is_alive():
                        server.shutdown()
                    server.server_close()
                    if thread is not None:
                        thread.join(timeout=2)
                        self.assertFalse(thread.is_alive())
                occupied.close()
                env.stop()

            # The fixture must leave no listener behind after server_close.
            released = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                released.bind(("127.0.0.1", server_port))
            finally:
                released.close()


if __name__ == "__main__":
    unittest.main()
