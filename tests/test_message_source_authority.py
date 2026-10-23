import contextlib
import importlib.util
import io
import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from panel.auth import VerifiedPrincipal
from panel.auth_integration_draft import AuthGate, AuthenticatedRequest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MessageSourceAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp.name) / "yuva-data"
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.data_root),
                                          "YUVA_AUTH_ENABLED": "0"})
        self.env.start()
        self.panel = load_module(
            "yuva_message_authority_panel", ROOT / "panel" / "server.py")
        self.cli = load_module("yuva_message_authority_cli", ROOT / "bin" / "yuva")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_cli_operator_from_claim_is_rejected_without_writing(self):
        args = SimpleNamespace(from_="operatör", metin="fake", to="@hepsi",
                               tur="not", panel=None)
        with self.assertRaises(self.cli.VeriHatasi):
            self.cli.cmd_yaz(args)
        self.assertFalse((self.data_root / "mesaj.jsonl").exists())

    def test_cli_offline_fallback_records_unknown_unverified_source(self):
        args = SimpleNamespace(from_="worker-1", metin="operator class please",
                               to="@hepsi", tur="not", panel=None)
        with patch.object(self.cli, "http_iste", return_value=(
                False, {"transport_state": self.cli.POST_NOT_SENT})):
            self.cli.cmd_yaz(args)

        rows = [json.loads(line) for line in
                (self.data_root / "mesaj.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_class"], "unknown")
        self.assertEqual(rows[0]["source_class_trust"], "unverified")
        self.assertEqual(rows[0]["provenance"]["trust"], "unverified")
        self.assertIsNone(rows[0]["provenance"]["actor_id"])

    def test_cli_has_no_source_class_override_flag(self):
        with patch.object(sys, "argv", ["yuva", "yaz", "claim class",
                                         "--from", "worker-1",
                                         "--source-class", "operator"]), \
                contextlib.redirect_stderr(io.StringIO()):
            # argparse rejects unsupported identity controls before cmd_yaz
            # can contact the panel or append a local message.
            with self.assertRaises(SystemExit) as raised:
                self.cli.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse((self.data_root / "mesaj.jsonl").exists())

    def test_api_rejects_source_class_and_operator_identity_claims(self):
        status, _ = self.panel.api_yaz({
            "kimden": "worker", "metin": "fake class", "source_class": "operator"})
        self.assertEqual(status, 400)

        status, _ = self.panel.api_yaz({
            "kimden": "operatörüm", "metin": "trust me"})
        self.assertEqual(status, 403)
        self.assertFalse((self.data_root / "mesaj.jsonl").exists())

    def test_exact_panel_ui_payload_writes_unknown_when_auth_is_off(self):
        ui = (ROOT / "panel" / "ui.html").read_text(encoding="utf-8")
        sender = re.search(r'async function gonder\(\)\s*\{(.*?)\n\}', ui, re.S)
        self.assertIsNotNone(sender)
        match = re.search(r'var ok=await yaz\(\{([^}]+)\}\);', sender.group(1))
        self.assertIsNotNone(match)
        self.assertNotIn("source_class", match.group(1))
        self.assertIn('kimden:"kullanici",ad:"Kullanıcı",kime:kime,metin:metin,tur:tur',
                      match.group(1))

        # Values instantiate the exact object shape produced by gonder().
        panel_payload = {"kimden": "kullanici", "ad": "Kullanıcı",
                         "kime": "@hepsi", "metin": "fixture panel message",
                         "tur": "not"}
        status, result = self.panel.api_yaz(panel_payload)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["mesaj"]["source_class"], "unknown")
        self.assertEqual(result["mesaj"]["source_class_trust"], "unverified")

    def test_only_verified_principal_and_operator_allowlist_choose_class(self):
        gate = AuthGate(object(), admin_principals=frozenset({"panel-admin"}),
                        operator_custody_verified=True)
        admin = VerifiedPrincipal("panel-admin", "k1", "test",
                                  "POST /api/yaz", 10)
        agent = VerifiedPrincipal("registered-agent", "k2", "test",
                                  "POST /api/yaz", 10)
        body = {"kimden": "kullanici", "ad": "Kullanıcı", "kime": "@hepsi",
                "metin": "verified source", "tur": "not"}

        for principal, expected in ((admin, "operator"), (agent, "agent")):
            authorization = gate.authorize_payload(
                AuthenticatedRequest("/api/yaz", principal), body)
            status, result = self.panel.api_yaz(
                {**body, "source_class": "unknown"},
                principal=principal, authorization=authorization)
            self.assertEqual(status, 400, result)
            status, result = self.panel.api_yaz(
                body, principal=principal, authorization=authorization)
            self.assertEqual(status, 200, result)
            self.assertEqual(result["mesaj"]["source_class"], expected)
            self.assertEqual(result["mesaj"]["source_class_trust"], "verified")

        rows = self.panel.mesajlar()
        self.assertEqual([row["source_class"] for row in rows], ["operator", "agent"])
        self.assertTrue(all(row["source_class_trust"] == "unverified" for row in rows))


if __name__ == "__main__":
    unittest.main()
