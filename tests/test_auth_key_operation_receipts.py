import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "prototypes" / "auth-key-lifecycle" / "fixture.py"
SPEC = importlib.util.spec_from_file_location("yuva_auth_lifecycle_seed", FIXTURE_PATH)
seed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed)

RECEIPT_PATH = ROOT / "prototypes" / "auth-key-lifecycle" / "operation_receipts.py"
RECEIPT_SPEC = importlib.util.spec_from_file_location(
    "yuva_auth_operation_receipt_fixture", RECEIPT_PATH)
operations = importlib.util.module_from_spec(RECEIPT_SPEC)
RECEIPT_SPEC.loader.exec_module(operations)


class AuthKeyOperationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-auth-op-receipts-")
        self.root = Path(self.temp.name) / "fixture"
        self.store = operations.ReceiptFixtureStore.initialize(
            self.root, seed.initial_state(), clock=lambda: 100)

    def tearDown(self):
        root = Path(self.temp.name)
        self.temp.cleanup()
        self.assertFalse(root.exists(), "auth receipt fixture was not removed")

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    def create(self, operation_id="create-a", token="token-a", *, expires=900,
               scopes=None, now=100):
        return operations.create_enrollment(
            self.store, operation_id=operation_id, principal_id="fixture-agent",
            token_digest=self.digest(token), issuer_key_id="fixture-issuer",
            scopes=scopes or ["POST /api/yaz"], expires_at=expires, now=now,
            admin_principals=["fixture-admin"],
            allowed_principals=["fixture-agent", "fixture-operator"])

    def test_create_receipt_replay_and_exact_readback(self):
        status, receipt = self.create()
        self.assertEqual(status, "committed")
        self.assertEqual(receipt["kind"], "enrollment.create")
        self.assertEqual(set(receipt["result"]), {"enrollment_digest"})
        self.assertNotIn("secret_b64", receipt)
        self.assertNotIn("private_key", receipt)
        generation = self.store.read()["auth_state"]["generation"]

        replay_status, replay = self.create()
        self.assertEqual(replay_status, "replayed")
        self.assertEqual(replay, receipt)
        self.assertEqual(self.store.read()["auth_state"]["generation"], generation)
        self.assertEqual(operations.reconcile_create(
            self.store, operation_id="create-a", principal_id="fixture-agent",
            token_digest=self.digest("token-a"), issuer_key_id="fixture-issuer",
            scopes=["POST /api/yaz"], expires_at=900, issued_at=100), "committed")
        self.assertEqual(operations.reconcile_create(
            self.store, operation_id="create-a", principal_id="fixture-agent",
            token_digest=self.digest("different-token"), issuer_key_id="fixture-issuer",
            scopes=["POST /api/yaz"], expires_at=900, issued_at=100), "unresolved")

    def test_same_operation_id_with_different_request_conflicts_without_commit(self):
        self.create()
        before = self.store.read()
        with self.assertRaises(operations.FixtureError) as conflict:
            self.create(token="token-b")
        self.assertEqual(conflict.exception.code, "operation_id_conflict")
        after = self.store.read()
        self.assertEqual(after["auth_state"]["generation"],
                         before["auth_state"]["generation"])
        self.assertEqual(after["operations"], before["operations"])

    def test_revoke_receipt_replay_and_enrollment_update_are_atomic(self):
        self.create()
        args = {"operation_id": "revoke-issuer", "principal_id": "fixture-admin",
                "key_id": "fixture-issuer", "now": 110}
        status, receipt = operations.revoke_key(self.store, **args)
        self.assertEqual(status, "committed")
        self.assertEqual(receipt["result_code"], "key_revoked")
        state = self.store.read()
        self.assertTrue(state["auth_state"]["keys"]["fixture-issuer"]["revoked"])
        self.assertEqual(state["auth_state"]["enrollments"][self.digest("token-a")]["status"],
                         "revoked")
        self.assertEqual(operations.reconcile_revoke(
            self.store, operation_id="revoke-issuer", principal_id="fixture-admin",
            key_id="fixture-issuer"), "committed")
        generation = state["auth_state"]["generation"]

        replay_status, replay = operations.revoke_key(self.store, **args)
        self.assertEqual(replay_status, "replayed")
        self.assertEqual(replay, receipt)
        self.assertEqual(self.store.read()["auth_state"]["generation"], generation)
        with self.assertRaises(operations.FixtureError) as conflict:
            operations.revoke_key(self.store, operation_id="revoke-issuer",
                                  principal_id="fixture-admin", key_id="missing-key",
                                  now=111)
        self.assertEqual(conflict.exception.code, "operation_id_conflict")

    def test_create_commit_unknown_is_resolved_by_exact_receipt_and_state_readback(self):
        original_fsync = os.fsync

        def fail_directory_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory fsync failure")
            return original_fsync(fd)

        with patch.object(operations.os, "fsync", side_effect=fail_directory_fsync):
            with self.assertRaises(operations.auth_store.CommitUnknown):
                self.create(operation_id="create-unknown", token="token-unknown")

        state = self.store.read()
        self.assertEqual(state["auth_state"]["generation"], 2)
        self.assertEqual(operations.reconcile_create(
            self.store, operation_id="create-unknown", principal_id="fixture-agent",
            token_digest=self.digest("token-unknown"), issuer_key_id="fixture-issuer",
            scopes=["POST /api/yaz"], expires_at=900, issued_at=100), "committed")
        self.assertEqual(operations.reconcile_create(
            self.store, operation_id="create-unknown", principal_id="fixture-agent",
            token_digest=self.digest("other-token"), issuer_key_id="fixture-issuer",
            scopes=["POST /api/yaz"], expires_at=900, issued_at=100), "unresolved")
        self.assertEqual(state["operations"]["create-unknown"]["committed_generation"], 2)

    def test_revoke_commit_unknown_is_resolved_without_retry(self):
        self.create()
        original_fsync = os.fsync

        def fail_directory_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("synthetic directory fsync failure")
            return original_fsync(fd)

        with patch.object(operations.os, "fsync", side_effect=fail_directory_fsync):
            with self.assertRaises(operations.auth_store.CommitUnknown):
                operations.revoke_key(self.store, operation_id="revoke-unknown",
                                      principal_id="fixture-admin",
                                      key_id="fixture-issuer", now=110)

        state = self.store.read()
        self.assertEqual(state["auth_state"]["generation"], 3)
        self.assertEqual(operations.reconcile_revoke(
            self.store, operation_id="revoke-unknown", principal_id="fixture-admin",
            key_id="fixture-issuer"), "committed")
        self.assertEqual(operations.reconcile_revoke(
            self.store, operation_id="revoke-unknown", principal_id="fixture-admin",
            key_id="missing-key"), "unresolved")

    def test_malformed_or_unsupported_v2_snapshot_fails_closed(self):
        snapshot = self.root / operations.SNAPSHOT_NAME
        for mutate in (
            lambda doc: doc.update(auth_state={**doc["auth_state"], "version": 99}),
            lambda doc: doc.update(operations={"op-bad": {"kind": "key.revoke"}}),
        ):
            with self.subTest(mutate=mutate):
                doc = self.store.read()
                mutate(doc)
                snapshot.write_text(json.dumps(doc), encoding="ascii")
                snapshot.chmod(0o600)
                with self.assertRaises(operations.auth_store.AuthStateError) as invalid:
                    self.store.read()
                self.assertEqual(invalid.exception.code, "store_invalid")
                # Restore a fresh valid fixture for the next malformed variant.
                self.temp.cleanup()
                self.temp = tempfile.TemporaryDirectory(prefix="yuva-auth-op-receipts-")
                self.root = Path(self.temp.name) / "fixture"
                self.store = operations.ReceiptFixtureStore.initialize(
                    self.root, seed.initial_state(), clock=lambda: 100)
                snapshot = self.root / operations.SNAPSHOT_NAME

    def test_receipt_count_limit_rejects_without_domain_mutation(self):
        with patch.object(operations, "MAX_OPERATIONS", 1):
            self.create(operation_id="create-one", token="token-one")
            before = self.store.read()
            with self.assertRaises(operations.FixtureError) as limited:
                self.create(operation_id="create-two", token="token-two")
            self.assertEqual(limited.exception.code, "operation_receipt_limit")
            after = self.store.read()
        self.assertEqual(after["auth_state"]["generation"],
                         before["auth_state"]["generation"])
        self.assertEqual(after["auth_state"]["enrollments"],
                         before["auth_state"]["enrollments"])
        self.assertEqual(len(after["operations"]), 1)

    def test_receipt_byte_limit_rejects_without_domain_mutation(self):
        before = self.store.read()
        with patch.object(operations, "MAX_OPERATION_BYTES", 100):
            with self.assertRaises(operations.FixtureError) as limited:
                self.create(operation_id="large-receipt", token="token-large")
        self.assertEqual(limited.exception.code, "operation_receipt_limit")
        after = self.store.read()
        self.assertEqual(after["auth_state"]["generation"],
                         before["auth_state"]["generation"])
        self.assertEqual(after["auth_state"]["enrollments"], {})
        self.assertEqual(after["operations"], {})


if __name__ == "__main__":
    unittest.main()
