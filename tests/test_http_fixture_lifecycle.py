import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.http_fixture_lifecycle import start_server, stop_server


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"fixture-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        pass


class HttpFixtureLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-http-lifecycle-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.marker = self.root / "fixture.marker"
        self.marker.write_text("temporary", encoding="utf-8")
        self.server = HTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.thread = start_server(self, self.server)

    def _request(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_successful_request_closes_socket_joins_thread_and_cleans_temp_root(self):
        self.assertFalse(self.thread.daemon)
        self.assertEqual(self._request(), (200, b"fixture-ok"))

        self.doCleanups()

        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.server.socket.fileno(), -1)
        self.assertFalse(self.root.exists())

    def test_shutdown_error_still_closes_socket_joins_and_cleans_temp_root(self):
        original_shutdown = self.server.shutdown

        def shutdown_then_fail():
            original_shutdown()
            raise RuntimeError("synthetic shutdown failure")

        with patch.object(self.server, "shutdown", side_effect=shutdown_then_fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic shutdown failure"):
                stop_server(self.server, self.thread)

        self.doCleanups()

        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.server.socket.fileno(), -1)
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
