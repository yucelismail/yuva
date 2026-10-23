import importlib.util
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from panel.auth import VerifiedPrincipal
from panel.auth_integration_draft import (
    AuthError, AuthGate, AuthenticatedRequest, message_source_class,
)


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OperatorCustodySourceClassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-operator-custody-")
        self.addCleanup(self.temp.cleanup)
        self.data_root = Path(self.temp.name) / "yuva-data"
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.data_root),
                                          "YUVA_AUTH_ENABLED": "0"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.panel = load_module(
            "yuva_operator_custody_panel", ROOT / "panel" / "server.py")

    def test_auth_off_identity_and_signature_shaped_claims_never_promote_operator(self):
        self.assertEqual(message_source_class(
            principal=None, admin_principals=frozenset({"operator"}),
            operator_custody_verified=True), ("unknown", "unverified"))
        status, result = self.panel.api_yaz({
            "kimden": "operatörüm", "ad": "Yuva sahibi", "metin": "claim",
            "kime": "@hepsi", "signature": "A" * 43,
            "key_id": "operator-key", "audience": "yuva-local",
            "timestamp": "1790000000", "nonce": "A" * 32,
        })
        self.assertEqual(status, 403, result)
        self.assertFalse((self.data_root / "mesaj.jsonl").exists())

    def test_auth_gate_without_custody_keeps_allowlisted_principal_unknown(self):
        principal = VerifiedPrincipal("operator", "key-1", "local",
                                      "POST /api/yaz", 10)
        gate = AuthGate(object(), admin_principals=frozenset({"operator"}))

        self.assertFalse(gate._operator_custody_verified)
        self.assertEqual(
            message_source_class(principal=principal,
                                 admin_principals=frozenset({"operator"})),
            ("unknown", "unverified"))
        authorization = gate.authorize_payload(
            AuthenticatedRequest("/api/yaz", principal), {"metin": "hello"})
        self.assertEqual(authorization, "unknown")
        status, result = self.panel.api_yaz(
            {"kimden": "operatör", "metin": "unverified admin claim"},
            principal=principal, authorization=authorization)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["mesaj"]["source_class"], "unknown")
        self.assertEqual(result["mesaj"]["source_class_trust"], "unverified")

    def test_operator_requires_verified_principal_allowlist_and_explicit_custody(self):
        principal = VerifiedPrincipal("operator", "key-1", "local",
                                      "POST /api/yaz", 10)
        admin_ids = frozenset({"operator"})

        self.assertEqual(message_source_class(
            principal=principal, admin_principals=admin_ids,
            operator_custody_verified=True), ("operator", "verified"))
        self.assertEqual(message_source_class(
            principal=principal, admin_principals=frozenset(),
            operator_custody_verified=True), ("agent", "verified"))
        self.assertEqual(message_source_class(
            principal=SimpleNamespace(principal_id="operator",
                                      scope="POST /api/yaz"),
            admin_principals=admin_ids, operator_custody_verified=True),
            ("unknown", "unverified"))
        self.assertEqual(message_source_class(
            principal=VerifiedPrincipal("operator", "key-1", "local",
                                        "POST /api/gorev", 10),
            admin_principals=admin_ids, operator_custody_verified=True),
            ("unknown", "unverified"))

        with self.assertRaises(ValueError):
            AuthGate(object(), admin_principals=admin_ids,
                     operator_custody_verified="true")

    def test_authenticated_route_without_principal_cannot_classify(self):
        gate = AuthGate(object(), admin_principals=frozenset({"operator"}),
                        operator_custody_verified=True)
        with self.assertRaises(AuthError) as raised:
            gate.authorize_payload(None, {"kimden": "operatör", "metin": "x"})
        self.assertEqual(raised.exception.code, "authentication_required")


if __name__ == "__main__":
    unittest.main()
