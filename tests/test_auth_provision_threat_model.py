import json
import fcntl
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
sys.path.insert(0, str(ROOT / "panel"))
import auth_provision_draft as provisioner
import auth_store_v2


class AuthProvisionThreatModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-auth-threat-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "store-root"
        self.root.mkdir(mode=0o700)
        # Deliberately omit inherited operator and CI variables from the CLI.
        self.env = {
            "HOME": str(self.base),
            "TMPDIR": str(self.base),
            "YUVA_AUTH_ENABLED": "0",
        }
        self.operation = "threat-fixture-op"
        self.instance = "threat-fixture-instance"
        self.audience = "threat-fixture-api"

    def tearDown(self):
        root = Path(self.temp.name)
        self.temp.cleanup()
        self.assertFalse(root.exists(), "auth threat fixture was not removed")

    def run_cli(self, root=None, *, env=None):
        return subprocess.run(
            [sys.executable, str(CLI), "auth", "provision",
             "--store-root", str(root or self.root),
             "--instance-id", self.instance,
             "--audience", self.audience,
             "--operation-id", self.operation],
            env=env or self.env, capture_output=True, text=True, timeout=10)

    def test_cli_does_not_echo_environment_secret_sentinel(self):
        env = dict(self.env)
        sentinel = "SYNTHETIC_SECRET_ENV_SENTINEL_8f12"
        env["YUVA_TEST_SECRET_SENTINEL"] = sentinel

        result = self.run_cli(env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt_line = next(line for line in result.stdout.splitlines()
                            if line.startswith("{"))
        receipt = json.loads(receipt_line)
        self.assertEqual(receipt["operation_id"], self.operation)
        self.assertEqual(receipt["instance_id"], self.instance)
        self.assertEqual(receipt["audience"], self.audience)
        self.assertEqual(env["YUVA_AUTH_ENABLED"], "0")
        persisted = ((self.root / auth_store_v2.STORE_NAME).read_bytes()
                     + (self.root / provisioner.PROVISION_RECEIPT_NAME).read_bytes())
        observed = result.stdout.encode() + result.stderr.encode() + persisted
        if sentinel.encode() in observed:
            self.fail("synthetic environment sentinel escaped provisioning outputs")

    def test_symlink_root_is_rejected_without_mutating_target(self):
        alias = self.base / "root-alias"
        alias.symlink_to(self.root, target_is_directory=True)

        result = self.run_cli(root=alias)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("yalnız geçici dizin", result.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_wrong_root_mode_is_rejected_without_creating_store(self):
        self.root.chmod(0o755)
        try:
            result = self.run_cli()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe_root", result.stderr)
            self.assertEqual(list(self.root.iterdir()), [])
        finally:
            self.root.chmod(0o700)

    def test_wrong_effective_owner_is_rejected_before_filesystem_mutation(self):
        real_euid = os.geteuid()
        with patch.object(provisioner.os, "geteuid", return_value=real_euid + 1):
            with self.assertRaises(provisioner.ProvisionError) as failure:
                provisioner.provision_empty_store_with_receipt(
                    self.root, operation_id=self.operation,
                    instance_id=self.instance, audience=self.audience, now=100)
        self.assertEqual(failure.exception.code, "unsafe_root")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_partial_snapshot_write_records_not_committed_and_cleans_temp(self):
        real_write_all = provisioner._write_all
        calls = 0

        def fail_after_partial_store_write(fd, payload):
            nonlocal calls
            calls += 1
            if calls == 2:  # prepared receipt succeeds; snapshot stage is partial
                real_write_all(fd, payload[:32])
                raise OSError("synthetic partial snapshot write")
            return real_write_all(fd, payload)

        with patch.object(provisioner, "_write_all",
                          side_effect=fail_after_partial_store_write):
            with self.assertRaises(provisioner.ProvisionError) as failure:
                provisioner.provision_empty_store_with_receipt(
                    self.root, operation_id=self.operation,
                    instance_id=self.instance, audience=self.audience, now=100)

        self.assertEqual(failure.exception.code, "snapshot_write_failed")
        self.assertFalse((self.root / auth_store_v2.STORE_NAME).exists())
        receipt = json.loads((self.root / provisioner.PROVISION_RECEIPT_NAME)
                             .read_text(encoding="ascii"))
        self.assertEqual(receipt["status"], "not_committed")
        self.assertEqual(receipt["result_code"], "snapshot_write_failed")
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.assertFalse(list(self.root.glob(".*.tmp")))

    def test_provision_unlock_error_closes_both_fds_and_replay_is_unchanged(self):
        lock_path = self.root / provisioner.PROVISION_LOCK_NAME
        lock_path.touch(mode=0o600)
        lock_path.chmod(0o600)
        lock_stat = lock_path.stat()
        before_fds = len(os.listdir("/proc/self/fd"))
        real_flock = provisioner.fcntl.flock

        def fail_provision_unlock(fd, operation):
            info = os.fstat(fd)
            if (operation == fcntl.LOCK_UN
                    and (info.st_dev, info.st_ino)
                    == (lock_stat.st_dev, lock_stat.st_ino)):
                raise OSError("synthetic provision unlock failure")
            return real_flock(fd, operation)

        with patch.object(provisioner.fcntl, "flock",
                          side_effect=fail_provision_unlock):
            with self.assertRaises(OSError):
                provisioner.provision_empty_store_with_receipt(
                    self.root, operation_id=self.operation,
                    instance_id=self.instance, audience=self.audience, now=100)

        after_fds = len(os.listdir("/proc/self/fd"))
        self.assertEqual(after_fds - before_fds, 0)
        store_path = self.root / auth_store_v2.STORE_NAME
        receipt_path = self.root / provisioner.PROVISION_RECEIPT_NAME
        store_before = store_path.read_bytes()
        receipt_before = receipt_path.read_bytes()
        self.assertEqual(json.loads(receipt_before)["status"], "committed")

        status, receipt = provisioner.provision_empty_store_with_receipt(
            self.root, operation_id=self.operation,
            instance_id=self.instance, audience=self.audience, now=100)

        self.assertEqual(status, "replayed")
        self.assertEqual(receipt["status"], "committed")
        self.assertEqual(store_path.read_bytes(), store_before)
        self.assertEqual(receipt_path.read_bytes(), receipt_before)

    def test_unlock_error_does_not_mask_commit_unknown_or_retry(self):
        lock_path = self.root / provisioner.PROVISION_LOCK_NAME
        lock_path.touch(mode=0o600)
        lock_path.chmod(0o600)
        lock_stat = lock_path.stat()
        real_flock = provisioner.fcntl.flock
        real_fsync = os.fsync
        directory_fsync_count = 0
        before_fds = len(os.listdir("/proc/self/fd"))

        def fail_provision_unlock(fd, operation):
            info = os.fstat(fd)
            if (operation == fcntl.LOCK_UN
                    and (info.st_dev, info.st_ino)
                    == (lock_stat.st_dev, lock_stat.st_ino)):
                raise OSError("synthetic provision unlock failure")
            return real_flock(fd, operation)

        def fail_store_directory_fsync(fd):
            nonlocal directory_fsync_count
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                directory_fsync_count += 1
                if directory_fsync_count == 3:
                    raise OSError("synthetic store directory fsync failure")
            return real_fsync(fd)

        with patch.object(provisioner.fcntl, "flock",
                          side_effect=fail_provision_unlock), \
                patch.object(provisioner.os, "fsync",
                             side_effect=fail_store_directory_fsync):
            with self.assertRaises(provisioner.ProvisionError) as failure:
                provisioner.provision_empty_store_with_receipt(
                    self.root, operation_id=self.operation,
                    instance_id=self.instance, audience=self.audience, now=100)

        self.assertEqual(failure.exception.code, "commit_unknown")
        after_fds = len(os.listdir("/proc/self/fd"))
        self.assertEqual(after_fds - before_fds, 0)
        receipt_path = self.root / provisioner.PROVISION_RECEIPT_NAME
        store_path = self.root / auth_store_v2.STORE_NAME
        store_before = store_path.read_bytes()
        receipt_before = receipt_path.read_bytes()
        self.assertEqual(json.loads(receipt_before)["status"], "commit_unknown")

        with self.assertRaises(provisioner.ProvisionError) as replay:
            provisioner.provision_empty_store_with_receipt(
                self.root, operation_id=self.operation,
                instance_id=self.instance, audience=self.audience, now=100)

        self.assertEqual(replay.exception.code, "commit_unknown")
        self.assertEqual(store_path.read_bytes(), store_before)
        self.assertEqual(receipt_path.read_bytes(), receipt_before)


if __name__ == "__main__":
    unittest.main()
