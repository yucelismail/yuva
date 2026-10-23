import email.message
import importlib.util
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import io
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "panel" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_panel_security_response_headers", SERVER_PATH,
    loader=SourceFileLoader("yuva_panel_security_response_headers", str(SERVER_PATH)))
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


class PanelSecurityResponseHeaderTests(unittest.TestCase):
    def make_handler(self):
        handler = object.__new__(panel.H)
        handler.client_address = ("127.0.0.1", 45000)
        handler.request_version = "HTTP/1.1"
        handler.requestline = "GET /fixture HTTP/1.1"
        handler.command = "GET"
        handler.path = "/fixture"
        handler.close_connection = False
        handler.wfile = io.BytesIO()
        handler.rfile = io.BytesIO()
        handler._headers_buffer = []
        handler.headers = email.message.Message()
        handler.log_request = lambda *args, **kwargs: None
        handler.log_error = lambda *args, **kwargs: None
        return handler

    def response_parts(self, handler):
        response = handler.wfile.getvalue().split(b"\r\n\r\n", 1)
        self.assertEqual(len(response), 2)
        header_bytes, body = response
        headers = {}
        for line in header_bytes.split(b"\r\n")[1:]:
            name, value = line.decode("iso-8859-1").split(":", 1)
            headers.setdefault(name.lower(), []).append(value.strip())
        return headers, body

    def assert_security_headers(self, handler):
        headers, _ = self.response_parts(handler)
        self.assertEqual(headers.get("cache-control"), ["no-store"])
        self.assertEqual(headers.get("x-content-type-options"), ["nosniff"])
        self.assertEqual(headers.get("referrer-policy"), ["no-referrer"])
        self.assertEqual(headers.get("x-frame-options"), ["DENY"])

    def assert_safe_error(self, handler, secret):
        self.assert_security_headers(handler)
        _, body = self.response_parts(handler)
        self.assertNotIn(secret.encode(), body)
        self.assertNotIn(b"Traceback", body)
        self.assertNotIn(b"/home/", body)

    def test_json_success_response_has_security_headers(self):
        handler = self.make_handler()
        panel.H._gonder(handler, 200, {"ok": True})
        self.assert_security_headers(handler)

    def test_options_error_response_has_security_headers(self):
        handler = self.make_handler()
        panel.H.do_OPTIONS(handler)
        self.assert_safe_error(handler, "fixture-secret")

    def test_standard_http_error_response_has_security_headers(self):
        handler = self.make_handler()
        secret = "fixture-secret /home/private/traceback"
        panel.H.send_error(handler, 501, secret, secret)
        self.assert_safe_error(handler, secret)

    def test_get_and_post_early_source_rejections_have_common_headers(self):
        for dispatch in (panel.H.do_GET, panel.H.do_POST):
            with self.subTest(dispatch=dispatch.__name__):
                handler = self.make_handler()
                handler.path = "/fixture-secret"
                dispatch(handler)
                self.assert_safe_error(handler, "fixture-secret")

    def test_get_not_found_has_headers_and_does_not_reflect_path(self):
        handler = self.make_handler()
        secret = "fixture-secret"
        handler.path = f"/{secret}"
        handler.headers["Host"] = "localhost:8686"

        panel.H.do_GET(handler)

        self.assert_safe_error(handler, secret)

    def test_post_parse_size_source_and_auth_errors_are_bounded(self):
        secret = "fixture-secret /home/private/token"
        cases = []

        source = self.make_handler()
        source.path = "/api/yaz"
        source.headers["Host"] = "evil.example"
        source.headers["Content-Type"] = f"application/json; {secret}"
        cases.append(("source", source))

        parse = self.make_handler()
        parse.path = "/api/yaz"
        parse.headers["Host"] = "localhost:8686"
        parse.headers["Content-Type"] = "application/json"
        parse.headers["Content-Length"] = "1"
        parse.rfile = io.BytesIO(b"{")
        cases.append(("parse", parse))

        size = self.make_handler()
        size.path = "/api/yaz"
        size.headers["Host"] = "localhost:8686"
        size.headers["Content-Type"] = "application/json"
        size.headers["Content-Length"] = str(panel.GOVDE_SINIR + 1)
        cases.append(("size", size))

        auth = self.make_handler()
        auth.path = "/api/yaz"
        auth.headers["Host"] = "localhost:8686"
        auth.headers["Content-Type"] = "application/json"
        auth.headers["Content-Length"] = "2"
        auth.rfile = io.BytesIO(b"{}")

        class RejectingAuthGate:
            @staticmethod
            def authenticate_post(*args):
                error = RuntimeError(secret)
                error.status = 401
                error.code = "invalid_signature"
                raise error

        auth.AUTH_GATE = RejectingAuthGate()
        cases.append(("auth", auth))

        for label, handler in cases:
            with self.subTest(error=label):
                panel.H.do_POST(handler)
                self.assert_safe_error(handler, secret)

    def test_handler_exception_body_and_stderr_do_not_leak_secret(self):
        secret = "fixture-secret /home/private/path"
        handler = self.make_handler()
        handler.path = "/api/yaz"
        handler.headers["Host"] = "localhost:8686"
        handler.headers["Content-Type"] = "application/json"
        handler.headers["Content-Length"] = "2"
        handler.rfile = io.BytesIO(b"{}")

        with patch.dict(panel.UCLAR, {
                "/api/yaz": lambda payload: (_ for _ in ()).throw(
                    RuntimeError(secret))}), patch("sys.stderr", new_callable=io.StringIO) as stderr:
            panel.H.do_POST(handler)

        self.assert_safe_error(handler, secret)
        self.assertNotIn(secret, stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertNotIn("/home/", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
