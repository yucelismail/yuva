import importlib.util
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_from_path(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScreenRedactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "yuva-data"
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.root)})
        self.env.start()
        self.redactor = load_from_path(
            "yuva_screen_redaction_test", REPO_ROOT / "yuva_screen_redaction.py")
        self.panel = load_from_path("yuva_panel_redaction_test",
                                    REPO_ROOT / "panel" / "server.py")
        self.cli = load_from_path("yuva_cli_redaction_test", REPO_ROOT / "bin" / "yuva")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def record(self, line=None):
        return {
            "ts": "2026-10-23T12:00:00+03:00",
            "kimlik": "codex-kole3",
            "ad": "Kole 3",
            "tur": "ekran",
            "satir": line if line is not None else "normal fixture output",
        }

    def test_panel_and_cli_writers_share_redaction_and_preserve_benign_text(self):
        line = (
            "normal status; Authorization: Bearer SYNTHETIC_BEARER_123456789; "
            "api_key=SYNTHETIC_API_KEY_123456789; "
            "export API_KEY=SYNTHETIC_ENV_API_KEY_ABCDEFGHI; "
            "env PASSWORD=SYNTHETIC_ENV_PASSWORD_987654; "
            "Cookie: session=SYNTHETIC_COOKIE; refresh=SYNTHETIC_COOKIE_REFRESH; "
            "https://synthetic-user:synthetic-pass@example.test/path; "
            "sk-" + "S" * 24
        )
        source_record = self.record(line)
        panel_path = self.root / "ekran" / "panel.jsonl"
        cli_path = self.root / "ekran" / "codex-kole3.jsonl"
        self.panel.ekle(panel_path, source_record)
        args = SimpleNamespace(satir=[line], from_="codex-kole3", tur="ekran",
                               panel="http://fixture.invalid")
        with patch.object(self.cli, "http_iste", return_value=(
                False, {"transport_state": self.cli.POST_NOT_SENT})):
            self.cli.cmd_ekran(args)

        panel_record = json.loads(panel_path.read_text(encoding="utf-8"))
        cli_record = json.loads(cli_path.read_text(encoding="utf-8"))
        self.assertEqual(source_record["satir"], line)
        self.assertEqual(panel_record["satir"], cli_record["satir"])
        self.assertIn("normal status", panel_record["satir"])
        self.assertGreaterEqual(panel_record["satir"].count("[REDACTED:credential]"), 4)
        for raw in ("SYNTHETIC_BEARER_123456789", "SYNTHETIC_API_KEY_123456789",
                    "SYNTHETIC_ENV_API_KEY_ABCDEFGHI", "SYNTHETIC_ENV_PASSWORD_987654",
                    "SYNTHETIC_COOKIE", "SYNTHETIC_COOKIE_REFRESH",
                    "synthetic-user", "synthetic-pass",
                    "sk-" + "S" * 24):
            self.assertNotIn(raw, panel_path.read_text(encoding="utf-8"))
            self.assertNotIn(raw, cli_path.read_text(encoding="utf-8"))

    def test_malformed_and_oversized_records_are_rejected(self):
        invalid = [
            self.record(7),
            dict(self.record(), extra="unexpected field"),
            dict(self.record(), ts="not-a-timestamp"),
            dict(self.record(), kimlik="../outside"),
            self.record("invalid unicode: " + chr(0xD800)),
            self.record("x" * (16 * 1024)),
        ]
        for record in invalid:
            with self.subTest(record_type=type(record.get("satir"))):
                with self.assertRaises(self.redactor.ScreenRedactionError):
                    self.redactor.redact_screen_record(record)

    def test_panel_api_returns_redacted_display_name(self):
        with patch.object(self.panel, "durum_oku", return_value={
                "kullanicilar": {"codex-kole3": {}}}), \
                patch.object(self.panel, "coz", return_value="codex-kole3"), \
                patch.object(self.panel, "adi",
                             return_value="Kole3 api_key=SYNTHETIC_DISPLAY_SECRET"):
            status, response = self.panel.api_ekran({
                "kimlik": "codex-kole3", "satir": "benign fixture", "tur": "ekran"})
        self.assertEqual(status, 200)
        self.assertNotIn("SYNTHETIC_DISPLAY_SECRET", response["ad"])
        stored = (self.root / "ekran" / "codex-kole3.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("SYNTHETIC_DISPLAY_SECRET", stored)

    def test_panel_api_command_and_environment_canaries_are_redacted_before_write(self):
        line = ("$ env API_KEY=SYNTHETIC_API_ENV_CANARY_12345 "
                "PASSWORD=SYNTHETIC_PASSWORD_CANARY_67890; "
                "curl -H Authorization: Bearer SYNTHETIC_COMMAND_BEARER_123456")
        with patch.object(self.panel, "durum_oku", return_value={
                "kullanicilar": {"codex-kole3": {}}}), \
                patch.object(self.panel, "coz", return_value="codex-kole3"), \
                patch.object(self.panel, "adi", return_value="Kole 3"):
            status, response = self.panel.api_ekran({
                "kimlik": "codex-kole3", "satir": line, "tur": "komut"})
        self.assertEqual(status, 200)
        self.assertNotIn("SYNTHETIC_API_ENV_CANARY_12345",
                         json.dumps(response, ensure_ascii=False))
        self.assertNotIn("SYNTHETIC_PASSWORD_CANARY_67890",
                         json.dumps(response, ensure_ascii=False))
        self.assertNotIn("SYNTHETIC_COMMAND_BEARER_123456",
                         json.dumps(response, ensure_ascii=False))
        stored = (self.root / "ekran" / "codex-kole3.jsonl").read_text(encoding="utf-8")
        self.assertIn("[REDACTED:credential]", stored)
        for raw in ("SYNTHETIC_API_ENV_CANARY_12345",
                    "SYNTHETIC_PASSWORD_CANARY_67890",
                    "SYNTHETIC_COMMAND_BEARER_123456"):
            self.assertNotIn(raw, stored)
            self.assertNotIn(raw, json.dumps(response, ensure_ascii=False))

    def test_panel_api_redactor_exception_returns_content_free_rejection(self):
        secret = "SYNTHETIC_API_REDACTOR_EXCEPTION_123"
        with patch.object(self.panel, "durum_oku", return_value={
                "kullanicilar": {"codex-kole3": {}}}), \
                patch.object(self.panel, "coz", return_value="codex-kole3"), \
                patch.object(self.panel, "adi", return_value="Kole 3"), \
                patch.object(self.panel._EKRAN_REDAKSIYON, "redact_text",
                             side_effect=RuntimeError(secret)):
            status, response = self.panel.api_ekran({
                "kimlik": "codex-kole3", "satir": "env TOKEN=" + secret,
                "tur": "komut"})
        self.assertEqual(status, 400)
        self.assertNotIn(secret, json.dumps(response, ensure_ascii=False))
        self.assertFalse((self.root / "ekran" / "codex-kole3.jsonl").exists())

    def test_redactor_exception_fails_closed_for_both_writers(self):
        panel_path = self.root / "ekran" / "panel.jsonl"
        cli_path = self.root / "ekran" / "cli.jsonl"
        with patch.object(self.panel._EKRAN_REDAKSIYON, "redact_text",
                          side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(self.panel._EKRAN_REDAKSIYON.ScreenRedactionError) as raised:
                self.panel.ekle(panel_path, self.record("SYNTHETIC_SECRET_VALUE"))
        self.assertNotIn("SYNTHETIC_SECRET_VALUE", str(raised.exception))
        self.assertFalse(panel_path.exists())

        args = SimpleNamespace(satir=["SYNTHETIC_SECRET_VALUE"], from_="codex-kole3",
                               tur="ekran", panel="http://fixture.invalid")
        with patch.object(self.cli, "http_iste", return_value=(
                False, {"transport_state": self.cli.POST_NOT_SENT})):
            with patch.object(self.cli._EKRAN_REDAKSIYON, "redact_text",
                                  side_effect=RuntimeError("synthetic failure")):
                with self.assertRaises(self.cli.VeriHatasi) as raised:
                    self.cli.cmd_ekran(args)
        self.assertNotIn("SYNTHETIC_SECRET_VALUE", str(raised.exception))
        self.assertFalse(cli_path.exists())


if __name__ == "__main__":
    unittest.main()
