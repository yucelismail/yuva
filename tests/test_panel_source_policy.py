import email.message
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest
from unittest.mock import Mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "panel" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_panel_source_policy", SERVER_PATH,
    loader=SourceFileLoader("yuva_panel_source_policy", str(SERVER_PATH)))
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


class PanelSourcePolicyTests(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(panel.H)
        self.handler.client_address = ("127.0.0.1", 45000)
        self.handler.headers = email.message.Message()
        self.handler.headers["Host"] = "localhost:8686"
        self.handler.headers["Origin"] = "http://localhost:8686"
        self.handler.headers["Content-Type"] = "application/json; charset=utf-8"
        self.handler.SUNUCU_PORT = 8686
        self.handler.IZINLI_HOSTLAR = {"localhost", "127.0.0.1", "::1"}

    def source_check(self, post=False):
        return panel.H._kaynak_denetimi(self.handler, post=post)

    def test_same_origin_json_post_passes_source_preflight(self):
        self.assertIsNone(self.source_check(post=True))

    def test_cross_origin_fetch_and_dns_rebinding_host_are_rejected(self):
        self.handler.headers.replace_header("Origin", "http://attacker.example:8686")
        self.assertEqual(self.source_check(post=True)[0], 403)

        self.handler.headers.replace_header("Host", "attacker.example:8686")
        self.handler.headers.replace_header("Origin", "http://attacker.example:8686")
        self.assertEqual(self.source_check()[0], 403)

    def test_simple_form_content_types_are_rejected(self):
        for content_type in ("application/x-www-form-urlencoded", "multipart/form-data",
                             "text/plain"):
            with self.subTest(content_type=content_type):
                self.handler.headers.replace_header("Content-Type", content_type)
                self.assertEqual(self.source_check(post=True)[0], 415)

    def test_malformed_or_non_origin_origin_values_fail_closed(self):
        for origin in (
                "null", "http://localhost:bad", "http://localhost:8686/",
                "http://localhost:8686/path", "http://user@localhost:8686",
                "http://localhost:8686?x=1", "https://localhost:8686"):
            with self.subTest(origin=origin):
                self.handler.headers.replace_header("Origin", origin)
                self.assertEqual(self.source_check()[0], 403)

    def test_duplicate_security_headers_are_rejected(self):
        self.handler.headers["Origin"] = "http://localhost:8686"
        self.assertEqual(self.source_check()[0], 403)

        self.handler.headers = email.message.Message()
        self.handler.headers["Host"] = "localhost:8686"
        self.handler.headers["Host"] = "127.0.0.1:8686"
        self.assertEqual(self.source_check()[0], 403)

        self.handler.headers = email.message.Message()
        self.handler.headers["Host"] = "localhost:8686"
        self.handler.headers["Content-Type"] = "application/json"
        self.handler.headers["Content-Type"] = "text/plain"
        self.assertEqual(self.source_check(post=True)[0], 415)

    def test_options_preflight_is_denied_without_cors_allow_headers(self):
        fixture = type("OptionsFixture", (), {
            "close_connection": False,
            "send_response": Mock(),
            "send_header": Mock(),
            "end_headers": Mock(),
        })()

        panel.H.do_OPTIONS(fixture)

        fixture.send_response.assert_called_once_with(405)
        names = [call.args[0].lower() for call in fixture.send_header.call_args_list]
        self.assertFalse(any(name.startswith("access-control-allow-") for name in names))
        self.assertTrue(fixture.close_connection)


if __name__ == "__main__":
    unittest.main()
