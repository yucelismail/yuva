import contextlib
import importlib.util
import io
import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import sys
import traceback
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = REPO_ROOT / "panel" / "server.py"


def load_panel(path):
    spec = importlib.util.spec_from_file_location(
        "yuva_error_redaction_panel", path,
        loader=SourceFileLoader("yuva_error_redaction_panel", str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ErrorRedactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(Path(self.temp.name) / "yuva")})
        self.env.start()
        self.panel = load_panel(PANEL_PATH)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_persistent_state_response_and_stderr_do_not_echo_exception(self):
        secret = "fixture-prompt-token-should-not-escape"
        reply = {}

        class Handler:
            def _gonder(self, status, body):
                reply["status"] = status
                reply["body"] = body
                return status, body

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.panel.H._durum_hatasi(Handler(), self.panel.DurumHatasi(secret))

        combined = repr(reply) + stderr.getvalue()
        self.assertNotIn(secret, combined)
        self.assertEqual(reply["status"], 500)
        self.assertIn("elle onarım", reply["body"]["hata"])
        self.assertRegex(reply["body"]["olay_id"], r"^[0-9a-f]{8}$")
        self.assertIn("type=DurumHatasi", stderr.getvalue())

    def test_unexpected_task_failure_has_safe_user_error_and_bounded_log(self):
        secret = "fixture-screen-content-secret-token"

        class BrokenCore:
            @staticmethod
            def run_task_operation(*args):
                print(secret, file=sys.stderr)
                raise RuntimeError(secret)

        stderr = io.StringIO()
        with patch.object(self.panel, "_TASK_CORE", BrokenCore), \
                contextlib.redirect_stderr(stderr):
            status, result = self.panel.gorev_calistir(
                {"islem": "sonraki", "kimden": "fixture-worker"})

        self.assertEqual(status, 500)
        self.assertIn("tanı kaydını", result["hata"])
        self.assertNotIn(secret, json.dumps(result) + stderr.getvalue())
        self.assertIn("context=task_operation", stderr.getvalue())
        self.assertIn("type=RuntimeError", stderr.getvalue())

    def test_request_handler_error_does_not_echo_secret_in_body_or_log(self):
        secret = "auth-header-fixture-secret"

        class Handler:
            path = "/api/yaz"
            AUTH_GATE = None

            @staticmethod
            def _kaynak_denetimi(post=False):
                return None

            @staticmethod
            def _govde_oku():
                return b"{}", None

            @staticmethod
            def _gonder(status, body, **kwargs):
                return status, body

        stderr = io.StringIO()
        with patch.dict(self.panel.UCLAR, {
                "/api/yaz": lambda payload: (_ for _ in ()).throw(RuntimeError(secret))}), \
                contextlib.redirect_stderr(stderr):
            status, body = self.panel.H.do_POST(Handler())

        self.assertEqual(status, 500)
        self.assertNotIn(secret, json.dumps(body) + stderr.getvalue())
        self.assertIn("context=request_handler", stderr.getvalue())
        self.assertRegex(body["olay_id"], r"^[0-9a-f]{8}$")

    def test_error_report_drops_token_key_and_absolute_path_traceback_canaries(self):
        canaries = (
            "SYNTHETIC_BEARER_TOKEN_CANARY_749",
            "SYNTHETIC_PRIVATE_KEY_CANARY_749",
            "/home/fixture-agent/private/credential-canary-749",
        )
        diagnostic = "\n".join(canaries)
        try:
            raise RuntimeError(diagnostic)
        except RuntimeError as error:
            traceback_report = "".join(traceback.format_exception(
                type(error), error, error.__traceback__))

        class Handler:
            def _gonder(self, status, body):
                return status, body

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status, body = self.panel.H._durum_hatasi(
                Handler(), RuntimeError(traceback_report))

        report = json.dumps(body, ensure_ascii=False) + stderr.getvalue()
        if any(canary in report for canary in canaries):
            self.fail("sanitized error output leaked a synthetic redaction canary")
        if "Traceback" in report:
            self.fail("sanitized error output included traceback text")
        self.assertEqual(status, 500)
        self.assertRegex(body["olay_id"], r"^[0-9a-f]{8}$")
        self.assertIn("type=RuntimeError", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
