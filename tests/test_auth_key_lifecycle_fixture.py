import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "prototypes" / "auth-key-lifecycle" / "fixture.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_auth_key_lifecycle_fixture_test", FIXTURE_PATH,
    loader=SourceFileLoader("yuva_auth_key_lifecycle_fixture_test", str(FIXTURE_PATH)))
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class AuthKeyLifecycleFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-auth-lifecycle-")
        self.root = Path(self.temp.name) / "auth-fixture"
        self.store = fixture.initialize_fixture_store(self.root)

    def tearDown(self):
        root = Path(self.temp.name)
        self.temp.cleanup()
        self.assertFalse(root.exists(), "auth lifecycle fixture was not removed")

    @staticmethod
    def digest(label):
        return hashlib.sha256(label.encode("ascii")).hexdigest()

    def enrollment(self, label="token-a", *, principal="fixture-agent",
                   scopes=None, expires=900, issuer="fixture-issuer", now=100):
        return fixture.create_enrollment(
            self.store, token_digest=self.digest(label), principal_id=principal,
            issuer_key_id=issuer,
            scopes=scopes or ["POST /api/yaz"], expires_at=expires, now=now,
            admin_principals=["fixture-admin"],
            allowed_principals=["fixture-agent", "fixture-operator"])

    def redeem(self, label="token-a", *, key_id="client-key-a",
               key=bytes([0x42]) * 32, operation="redeem-op-a", now=101):
        return fixture.redeem_enrollment(
            self.store, token_digest=self.digest(label), key_id=key_id,
            synthetic_client_key=key, operation_id=operation, now=now)

    def test_allowlist_scope_and_expiry_rejections_do_not_commit(self):
        generation = self.store.read()["generation"]
        with self.assertRaises(fixture.LifecycleError) as denied:
            self.enrollment(principal="not-allowlisted")
        self.assertEqual(denied.exception.code, "principal_not_allowed")
        with self.assertRaises(fixture.LifecycleError) as broad_scope:
            self.enrollment(label="scope", scopes=["GET /api/veri"])
        self.assertEqual(broad_scope.exception.code, "scope_exceeds_issuer")
        with self.assertRaises(fixture.LifecycleError) as expired:
            self.enrollment(label="expired", expires=100)
        self.assertEqual(expired.exception.code, "enrollment_expired_or_invalid")
        state = self.store.read()
        self.assertEqual(state["generation"], generation)
        self.assertEqual(state["enrollments"], {})

    def test_enroll_redeem_dedupes_operation_and_rotation_revokes_old_key(self):
        self.assertEqual(self.enrollment(), "enrollment_created")
        self.assertEqual(self.redeem(), "enrollment_redeemed")
        generation = self.store.read()["generation"]
        self.assertEqual(self.redeem(), "already_redeemed")
        self.assertEqual(self.store.read()["generation"], generation)
        with self.assertRaises(fixture.LifecycleError) as conflict:
            self.redeem(key=bytes([0x43]) * 32, operation="different-op")
        self.assertEqual(conflict.exception.code, "enrollment_already_consumed")

        self.enrollment(label="token-b", expires=1000, now=102)
        self.redeem(label="token-b", key_id="client-key-b",
                    key=bytes([0x44]) * 32, operation="redeem-op-b", now=103)
        # A caller would verify the new client through a non-destructive path
        # before revoking the previous credential; no HMAC request is sent here.
        self.assertEqual(fixture.revoke_key(self.store, key_id="client-key-a", now=110),
                         "key_revoked")
        state = self.store.read()
        self.assertTrue(state["keys"]["client-key-a"]["revoked"])
        self.assertFalse(state["keys"]["client-key-b"]["revoked"])
        self.assertEqual(state["enrollments"][self.digest("token-a")]["status"], "revoked")

    def test_issuer_revoke_closes_pending_enrollment_atomically(self):
        self.enrollment(label="pending-token")
        self.assertEqual(fixture.revoke_key(
            self.store, key_id="fixture-issuer", now=110), "key_revoked")
        state = self.store.read()
        self.assertTrue(state["keys"]["fixture-issuer"]["revoked"])
        self.assertEqual(state["enrollments"][self.digest("pending-token")]["status"],
                         "revoked")
        self.assertEqual(fixture.revoke_key(
            self.store, key_id="fixture-issuer", now=111), "already_revoked")

    def test_commit_unknown_redeem_uses_exact_readback_without_retry(self):
        self.enrollment(label="token-commit-unknown")
        key = bytes([0x45]) * 32
        original_fsync = os.fsync

        def fail_directory_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory fsync failure")
            return original_fsync(fd)

        with patch.object(fixture.auth_store.os, "fsync", side_effect=fail_directory_fsync):
            with self.assertRaises(fixture.auth_store.CommitUnknown):
                self.redeem(label="token-commit-unknown", key_id="uncertain-key",
                            key=key, operation="operation-unknown")

        self.assertEqual(fixture.reconcile_redeem(
            self.store, token_digest=self.digest("token-commit-unknown"),
            key_id="uncertain-key", operation_id="operation-unknown",
            synthetic_client_key=key), "committed")
        self.assertEqual(fixture.reconcile_redeem(
            self.store, token_digest=self.digest("token-commit-unknown"),
            key_id="other-key", operation_id="operation-unknown",
            synthetic_client_key=key), "unresolved")
        state = self.store.read()
        self.assertEqual(state["generation"], 3)
        self.assertEqual(state["enrollments"][self.digest("token-commit-unknown")]["status"],
                         "consumed")

    def test_pre_replace_failure_stays_pending_and_malformed_store_is_rejected(self):
        self.enrollment(label="token-pre-replace")
        before = self.store.read()
        with patch.object(fixture.auth_store.os, "replace",
                          side_effect=OSError("synthetic replace failure")):
            with self.assertRaises(fixture.auth_store.AuthStateError) as failed:
                self.redeem(label="token-pre-replace", key_id="no-commit-key",
                            operation="pre-replace-op")
        self.assertEqual(failed.exception.code, "commit_not_started")
        after = self.store.read()
        self.assertEqual(after["generation"], before["generation"])
        self.assertEqual(after["enrollments"][self.digest("token-pre-replace")]["status"],
                         "pending")
        self.assertNotIn("no-commit-key", after["keys"])

        state_path = self.root / fixture.auth_store.STORE_NAME
        state_path.write_bytes(b'{"broken":')
        state_path.chmod(0o600)
        with self.assertRaises(fixture.auth_store.AuthStateError) as corrupt:
            self.store.read()
        self.assertEqual(corrupt.exception.code, "store_invalid")


if __name__ == "__main__":
    unittest.main()
