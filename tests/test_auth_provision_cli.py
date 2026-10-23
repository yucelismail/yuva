import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "yuva"
PANEL_DIR = ROOT / "panel"
sys.path.insert(0, str(PANEL_DIR))
import auth_provision_draft as provisioner
import auth_store_v2


class AuthProvisionCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-auth-provision-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.data_root = self.base / "yuva-data"
        self.data_root.mkdir(mode=0o700)
        self.root = self.base / "auth-root"
        self.root.mkdir(mode=0o700)
        # Child CLI gets only fixture paths and the explicit disabled flag;
        # operator/CI credentials from the parent environment are not inherited.
        self.env = {
            "HOME": str(self.base),
            "TMPDIR": str(self.base),
            "YUVA_DIR": str(self.data_root),
            "YUVA_AUTH_ENABLED": "0",
        }

    def tearDown(self):
        root = Path(self.temp.name)
        self.temp.cleanup()
        self.assertFalse(root.exists(), "auth provisioning fixture was not removed")

    def run_provision(self, *, root=None, operation="fixture-op-1",
                      instance="fixture-instance", audience="fixture-api", env=None):
        return subprocess.run(
            [sys.executable, str(CLI), "auth", "provision",
             "--store-root", str(root or self.root),
             "--instance-id", instance, "--audience", audience,
             "--operation-id", operation],
            env=env or self.env, capture_output=True, text=True, timeout=10)

    def test_cli_provisions_empty_store_with_secret_free_idempotent_receipt(self):
        first = self.run_provision()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("auth empty-store provision created", first.stdout)
        receipt_line = next(line for line in first.stdout.splitlines()
                            if line.startswith("{"))
        receipt = json.loads(receipt_line)
        self.assertEqual(receipt["status"], "committed")
        self.assertEqual(receipt["operation_id"], "fixture-op-1")
        for secret_field in ("secret_b64", "private_key", "token", "credential"):
            self.assertNotIn(secret_field, receipt)

        state_path = self.root / auth_store_v2.STORE_NAME
        receipt_path = self.root / provisioner.PROVISION_RECEIPT_NAME
        state_before = state_path.read_bytes()
        receipt_before = receipt_path.read_bytes()
        state = auth_store_v2.AuthStateStore(self.root).read()
        self.assertEqual(state["generation"], 1)
        self.assertEqual(state["keys"], {})
        self.assertEqual(state["enrollments"], {})
        self.assertEqual(self.env["YUVA_AUTH_ENABLED"], "0")

        replay = self.run_provision()

        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertIn("auth empty-store provision replayed", replay.stdout)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(receipt_path.read_bytes(), receipt_before)
        self.assertEqual(os.stat(state_path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(receipt_path).st_mode & 0o777, 0o600)

    def test_operation_id_conflict_does_not_replace_store_or_receipt(self):
        first = self.run_provision()
        self.assertEqual(first.returncode, 0, first.stderr)
        state_path = self.root / auth_store_v2.STORE_NAME
        receipt_path = self.root / provisioner.PROVISION_RECEIPT_NAME
        state_before = state_path.read_bytes()
        receipt_before = receipt_path.read_bytes()

        conflict = self.run_provision(audience="other-api")

        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("operation_id_conflict", conflict.stderr)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(receipt_path.read_bytes(), receipt_before)

    def test_preexisting_store_without_matching_receipt_is_not_modified(self):
        state = provisioner.empty_initial_state(
            "fixture-instance", "fixture-api", now=100)
        state_path = provisioner.write_initial_state(self.root, state)
        state_before = state_path.read_bytes()

        result = self.run_provision()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("store_already_exists", result.stderr)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertFalse((self.root / provisioner.PROVISION_LOCK_NAME).exists())
        self.assertFalse((self.root / provisioner.PROVISION_RECEIPT_NAME).exists())

    def test_cli_rejects_store_root_outside_selected_temporary_directory(self):
        temp_root = self.base / "allowed-temp"
        temp_root.mkdir(mode=0o700)
        outside = self.base / "outside-temp-root"
        outside.mkdir(mode=0o700)
        env = dict(self.env)
        env["TMPDIR"] = str(temp_root)

        result = self.run_provision(root=outside, env=env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("yalnız geçici dizin", result.stderr)
        self.assertEqual(list(outside.iterdir()), [])

    def test_store_directory_fsync_commit_unknown_is_not_retried(self):
        real_fsync = os.fsync
        directory_fsync_count = 0

        def fail_store_directory_fsync(fd):
            nonlocal directory_fsync_count
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                directory_fsync_count += 1
                if directory_fsync_count == 3:
                    raise OSError("synthetic store directory fsync failure")
            return real_fsync(fd)

        with patch.object(provisioner.os, "fsync", side_effect=fail_store_directory_fsync):
            with self.assertRaises(provisioner.ProvisionError) as unknown:
                provisioner.provision_empty_store_with_receipt(
                    self.root, operation_id="fixture-unknown",
                    instance_id="fixture-instance", audience="fixture-api", now=100)
        self.assertEqual(unknown.exception.code, "commit_unknown")

        state_path = self.root / auth_store_v2.STORE_NAME
        receipt_path = self.root / provisioner.PROVISION_RECEIPT_NAME
        state_before = state_path.read_bytes()
        receipt = json.loads(receipt_path.read_text(encoding="ascii"))
        self.assertEqual(receipt["status"], "commit_unknown")
        self.assertEqual(auth_store_v2.AuthStateStore(self.root).read()["keys"], {})

        with self.assertRaises(provisioner.ProvisionError) as replay:
            provisioner.provision_empty_store_with_receipt(
                self.root, operation_id="fixture-unknown",
                instance_id="fixture-instance", audience="fixture-api")

        self.assertEqual(replay.exception.code, "commit_unknown")
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(json.loads(receipt_path.read_text(encoding="ascii")), receipt)


if __name__ == "__main__":
    unittest.main()
