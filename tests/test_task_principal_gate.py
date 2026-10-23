import importlib.util
import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from panel.auth import AuthError, VerifiedPrincipal
from panel.auth_integration_draft import AuthGate, AuthenticatedRequest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskPrincipalGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp.name) / "yuva-data"
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.data_root)})
        self.env.start()
        self.panel = load_module(
            "yuva_task_gate_panel", REPO_ROOT / "panel" / "server.py")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_authenticated_api_uses_principal_not_body_actor_claim(self):
        principal = SimpleNamespace(
            principal_id="verified-worker", scope="POST /api/gorev")

        status, result = self.panel.gorev_calistir({
            "islem": "ekle", "baslik": "fixture task",
            "kimden": "forged-worker"}, principal=principal,
            authorization="task_admin")

        self.assertEqual(status, 200, result)
        task_data = json.loads((self.data_root / "gorevler.json").read_text())
        task = task_data["gorevler"][0]
        self.assertEqual(task["kimden"], "verified-worker")
        self.assertEqual(task["gecmis"][0]["kimden"], "verified-worker")
        self.assertEqual(task["gecmis"][0]["actor_trust"], "verified_hmac")

    def test_auth_off_direct_cli_mutation_is_recorded_as_unverified_label(self):
        cli = load_module("yuva_task_gate_cli", REPO_ROOT / "bin" / "yuva")
        args = SimpleNamespace(
            from_="local-worker", baslik="fixture local task", detay="",
            ata=None, gorevli=None, ust_gorev_id=None)

        with patch.dict(os.environ, {"YUVA_AUTH_ENABLED": "0"}):
            cli.cmd_gorev_ekle(args)

        task = json.loads((self.data_root / "gorevler.json").read_text())["gorevler"][0]
        self.assertEqual(task["kimden"], "local-worker")
        self.assertEqual(task["gecmis"][0]["actor_trust"], "local_unverified")

    def test_auth_on_direct_cli_mutation_without_principal_fails_closed(self):
        cli = load_module("yuva_task_gate_cli_auth_on", REPO_ROOT / "bin" / "yuva")
        args = SimpleNamespace(
            from_="claimed-worker", baslik="must not write", detay="",
            ata=None, gorevli=None, ust_gorev_id=None)

        with patch.dict(os.environ, {"YUVA_AUTH_ENABLED": "1"}):
            with self.assertRaises(SystemExit) as raised:
                cli.cmd_gorev_ekle(args)

        self.assertIn("doğrulanmış principal gerekli", str(raised.exception))
        self.assertFalse((self.data_root / "gorevler.json").exists())

    def test_auth_off_api_records_local_label_and_auth_on_requires_principal(self):
        with patch.dict(os.environ, {"YUVA_AUTH_ENABLED": "0"}):
            local_status, local_result = self.panel.gorev_calistir({
                "islem": "ekle", "baslik": "fixture local api task",
                "kimden": "local-api-worker"})
        local_task = json.loads(
            (self.data_root / "gorevler.json").read_text())["gorevler"][0]
        with patch.dict(os.environ, {"YUVA_AUTH_ENABLED": "1"}):
            auth_on = self.panel.gorev_calistir({
                "islem": "ekle", "baslik": "must not write",
                "kimden": "claimed-worker"})
        wrong_scope = self.panel.gorev_calistir(
            {"islem": "ekle", "baslik": "must not write"},
            principal=SimpleNamespace(
                principal_id="worker", scope="POST /api/yaz"),
            authorization="task_admin")
        missing_policy = self.panel.gorev_calistir(
            {"islem": "ekle", "baslik": "must not write"},
            principal=SimpleNamespace(
                principal_id="worker", scope="POST /api/gorev"))

        self.assertEqual(local_status, 200, local_result)
        self.assertEqual(local_task["kimden"], "local-api-worker")
        self.assertEqual(local_task["gecmis"][0]["actor_trust"], "local_unverified")
        self.assertEqual(auth_on[0], 401)
        self.assertEqual(wrong_scope[0], 403)
        self.assertEqual(missing_policy[0], 403)

    def test_auth_gate_applies_operation_policy_before_dispatch(self):
        gate = AuthGate(object(), admin_principals=frozenset({"admin"}))
        worker = VerifiedPrincipal(
            "worker", "k1", "test", "POST /api/gorev", 1)
        admin = VerifiedPrincipal(
            "admin", "k2", "test", "POST /api/gorev", 1)

        worker_al = gate.authorize_payload(
            AuthenticatedRequest("/api/gorev", worker), {"islem": "al"})
        with self.assertRaises(AuthError) as denied:
            gate.authorize_payload(
                AuthenticatedRequest("/api/gorev", worker), {"islem": "iptal"})
        admin_cancel = gate.authorize_payload(
            AuthenticatedRequest("/api/gorev", admin), {"islem": "iptal"})

        self.assertEqual(worker_al, "task_worker")
        self.assertEqual(denied.exception.code, "admin_required")
        self.assertEqual(admin_cancel, "task_admin")

    def test_worker_claim_binds_assignee_to_verified_principal(self):
        self.data_root.mkdir(parents=True)
        self.data_root.chmod(0o700)
        (self.data_root / "durum.json").write_text(json.dumps({
            "kullanicilar": {"worker": {"rol": "isci"}}, "rev": 0
        }))
        (self.data_root / "gorevler.json").write_text(json.dumps({
            "siradaki": 2,
            "gorevler": [{"id": 1, "baslik": "claim me", "kimden": "owner",
                          "assignee": None, "durum": "pending",
                          "gecmis": []}],
        }))

        status, result = self.panel.gorev_calistir(
            {"islem": "al", "id": 1, "kimden": "other-worker"},
            principal=SimpleNamespace(
                principal_id="worker", scope="POST /api/gorev"),
            authorization="task_worker")

        self.assertEqual(status, 200, result)
        task = json.loads((self.data_root / "gorevler.json").read_text())["gorevler"][0]
        self.assertEqual(task["assignee"], "worker")
        self.assertEqual(task["gecmis"][0]["kimden"], "worker")
        self.assertEqual(task["gecmis"][0]["actor_trust"], "verified_hmac")


if __name__ == "__main__":
    unittest.main()
