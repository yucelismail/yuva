import contextlib
import http.client
import importlib.util
import io
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.http_fixture_lifecycle import start_server


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "panel" / "server.py"


def load_panel(name):
    spec = importlib.util.spec_from_file_location(
        name, SERVER_PATH, loader=SourceFileLoader(name, str(SERVER_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PanelErrorEphemeralHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-panel-error-http-")
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "YUVA_DIR": str(Path(self.temp.name) / "yuva-data"),
            "YUVA_AUTH_ENABLED": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.panel = load_panel(f"yuva_panel_error_http_{id(self)}")
        self.old_handler_state = (
            self.panel.H.AUTH_GATE, self.panel.H.BROWSER_SESSION_GATE,
            self.panel.H.SUNUCU_PORT,
            self.panel.H.IZINLI_HOSTLAR)
        self.panel.H.AUTH_GATE = None
        class FixtureBrowserSessionGate:
            def authorize_get(_self, route, scope, cookie):
                return cookie == "yuva_session=fixture-session"
        self.panel.H.BROWSER_SESSION_GATE = FixtureBrowserSessionGate()
        self.panel.H.IZINLI_HOSTLAR = {"localhost", "127.0.0.1"}
        self.server = self.panel.Sunucu(("127.0.0.1", 0), self.panel.H)
        self.panel.H.SUNUCU_PORT = self.server.server_port
        self.addCleanup(self._restore_handler_state)
        self.thread = start_server(self, self.server)

    def _restore_handler_state(self):
        (self.panel.H.AUTH_GATE, self.panel.H.BROWSER_SESSION_GATE,
         self.panel.H.SUNUCU_PORT,
         self.panel.H.IZINLI_HOSTLAR) = self.old_handler_state

    def request(self, method, path, *, body=None, headers=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        try:
            request_headers = dict(headers or {})
            if method == "GET" and path in ("/", "/index.html", "/api/veri", "/veri"):
                request_headers.setdefault("Cookie", "yuva_session=fixture-session")
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, response.getheaders(), raw
        finally:
            connection.close()

    def assert_common_error_contract(self, status, headers, body, *, secret=None):
        self.assertGreaterEqual(status, 400)
        lowered = {}
        for name, value in headers:
            lowered.setdefault(name.lower(), []).append(value)
        self.assertEqual(lowered.get("cache-control"), ["no-store"])
        self.assertEqual(lowered.get("x-content-type-options"), ["nosniff"])
        self.assertEqual(lowered.get("referrer-policy"), ["no-referrer"])
        self.assertEqual(lowered.get("x-frame-options"), ["DENY"])
        self.assertEqual(lowered.get("content-length"), [str(len(body))])
        self.assertNotIn(b"Traceback", body)
        self.assertNotIn(b"/home/", body)
        if secret is not None:
            self.assertNotIn(secret.encode("utf-8"), body)

    def test_real_http_protocol_and_request_rejections_have_common_headers(self):
        secret = "SYNTHETIC_HTTP_ERROR_SECRET_642"
        cases = [
            ("unknown route", "GET", f"/{secret}", None, None, 404),
            ("invalid origin", "GET", "/", None,
             {"Origin": "http://untrusted.example"}, 403),
            ("options", "OPTIONS", "/", None, None, 405),
            ("unsupported method", "TRACE", f"/{secret}", None, None, 501),
            ("bad json", "POST", "/api/yaz", b"{",
             {"Content-Type": "application/json"}, 400),
            ("bad content type", "POST", "/api/yaz", b"{}",
             {"Content-Type": "text/plain"}, 415),
        ]
        for label, method, path, body, headers, expected_status in cases:
            with self.subTest(case=label):
                status, response_headers, response_body = self.request(
                    method, path, body=body, headers=headers)
                self.assertEqual(status, expected_status)
                self.assert_common_error_contract(
                    status, response_headers, response_body, secret=secret)
                self.assertNotIn(secret.encode("utf-8"), response_body)

    def test_persistent_state_and_route_exceptions_are_redacted_over_http(self):
        secret = "SYNTHETIC_INTERNAL_EXCEPTION_642"
        stderr = io.StringIO()
        with patch.object(self.panel, "veri",
                          side_effect=self.panel.DurumHatasi(secret)), \
                contextlib.redirect_stderr(stderr):
            status, headers, body = self.request("GET", "/api/veri")
        self.assertEqual(status, 500)
        self.assert_common_error_contract(status, headers, body, secret=secret)
        self.assertNotIn(secret, stderr.getvalue())
        decoded = json.loads(body)
        self.assertRegex(decoded["olay_id"], r"^[0-9a-f]{8}$")

    def test_screen_write_exception_does_not_echo_command_or_credentials(self):
        secret = "SYNTHETIC_SCREEN_HANDLER_CANARY_642"
        command = ("env API_KEY=" + secret
                   + " PASSWORD=SYNTHETIC_SCREEN_PASSWORD_642")
        stderr = io.StringIO()
        with patch.object(self.panel, "ekran_yaz",
                          side_effect=RuntimeError(command)), \
                contextlib.redirect_stderr(stderr):
            status, headers, body = self.request(
                "POST", "/api/ekran",
                body=json.dumps({"kimlik": "fixture", "satir": command,
                                 "tur": "komut"}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
        self.assertEqual(status, 500)
        self.assert_common_error_contract(status, headers, body, secret=secret)
        self.assertNotIn(b"SYNTHETIC_SCREEN_PASSWORD_642", body)
        self.assertNotIn(command, stderr.getvalue())
        self.assertNotIn("SYNTHETIC_SCREEN_PASSWORD_642", stderr.getvalue())
        decoded = json.loads(body)
        self.assertRegex(decoded["olay_id"], r"^[0-9a-f]{8}$")

        def fail_route(_payload):
            raise RuntimeError(secret)

        stderr = io.StringIO()
        with patch.dict(self.panel.UCLAR, {"/api/yaz": fail_route}), \
                contextlib.redirect_stderr(stderr):
            status, headers, body = self.request(
                "POST", "/api/yaz", body=b"{}",
                headers={"Content-Type": "application/json"})
        self.assertEqual(status, 500)
        self.assert_common_error_contract(status, headers, body, secret=secret)
        self.assertNotIn(secret, stderr.getvalue())
        decoded = json.loads(body)
        self.assertRegex(decoded["olay_id"], r"^[0-9a-f]{8}$")


if __name__ == "__main__":
    unittest.main()
