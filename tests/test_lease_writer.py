import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from importlib.machinery import SourceFileLoader
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "prototypes" / "lease-presence" / "writer.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_isolated_lease_writer", MODULE_PATH,
    loader=SourceFileLoader("yuva_isolated_lease_writer", str(MODULE_PATH)))
writer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(writer)


class LeaseWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-lease-writer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / writer.FIXTURE_MARKER).write_text(
            writer.FIXTURE_MARKER_VALUE, encoding="utf-8")
        self.ledger_path = self.root / "gorevler.json"

    def write_task(self, task):
        self.ledger_path.write_text(json.dumps({
            "schema_version": 1, "siradaki": 2, "gorevler": [task],
        }), encoding="utf-8")
        self.ledger_path.chmod(0o600)

    def read_task(self):
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))["gorevler"][0]

    def test_claim_commits_owner_claim_and_epoch_in_same_task_snapshot(self):
        self.write_task({"id": 1, "durum": "pending", "assignee": None})

        claim = writer.claim_task(
            self.root, 1, "agent-label", operation_id="op-1", claimed_at="t1")

        task = self.read_task()
        self.assertEqual(task["durum"], "assigned")
        self.assertEqual(task["assignee"], "agent-label")
        self.assertEqual(task["execution"]["owner_claim"], "agent-label")
        self.assertEqual(task["execution"]["owner_trust"], "unverified")
        self.assertEqual(task["execution"]["lease_epoch"], 1)
        self.assertEqual(claim, task["execution"])
        self.assertEqual(writer.claim_task(
            self.root, 1, "agent-label", operation_id="op-1", claimed_at="t2"), claim)
        self.assertEqual(self.read_task()["execution"]["lease_epoch"], 1)

    def test_unmarked_store_is_rejected_before_lock_or_data_creation(self):
        (self.root / writer.FIXTURE_MARKER).unlink()
        with self.assertRaisesRegex(writer.LeaseWriterError, "fixture marker"):
            writer.claim_task(
                self.root, 1, "worker", operation_id="op-1", claimed_at="t")
        self.assertFalse((self.root / ".kilit").exists())
        self.assertFalse(self.ledger_path.exists())

    def test_new_claim_increments_closed_epoch_and_refuses_unproven_reclaim(self):
        self.write_task({
            "id": 1, "durum": "pending", "assignee": None,
            "execution": {"lease_state": "closed", "lease_epoch": 8},
        })
        claim = writer.claim_task(
            self.root, 1, "new-label", operation_id="op-new", claimed_at="t2")
        self.assertEqual(claim["lease_epoch"], 9)

        task = self.read_task()
        task["durum"] = "pending"
        task["execution"]["lease_state"] = "expired_suspect"
        self.write_task(task)
        with self.assertRaisesRegex(writer.LeaseWriterError, "reconciliation"):
            writer.claim_task(
                self.root, 1, "another-label", operation_id="op-3", claimed_at="t3")

    def test_parallel_claims_have_one_winner_under_shared_lock(self):
        self.write_task({"id": 1, "durum": "pending", "assignee": None})
        barrier = threading.Barrier(2)

        def claim(owner):
            barrier.wait(timeout=2)
            try:
                return writer.claim_task(
                    self.root, 1, owner, operation_id=f"op-{owner}", claimed_at="t")
            except writer.LeaseWriterError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("worker-a", "worker-b")))
        self.assertEqual(sum(result is not None for result in results), 1)
        task = self.read_task()
        self.assertEqual(task["assignee"], task["execution"]["owner_claim"])
        self.assertEqual(task["execution"]["owner_trust"], "unverified")

    def test_replace_failure_preserves_original_ledger(self):
        self.write_task({"id": 1, "durum": "pending", "assignee": None})
        before = self.ledger_path.read_bytes()
        with patch.object(writer.os, "replace", side_effect=OSError("fixture failure")):
            with self.assertRaises(OSError):
                writer.claim_task(
                    self.root, 1, "worker", operation_id="op-1", claimed_at="t")
        self.assertEqual(self.ledger_path.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".gorevler.lease-*")), [])


if __name__ == "__main__":
    unittest.main()
