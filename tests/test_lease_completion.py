import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from importlib.machinery import SourceFileLoader


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "prototypes" / "lease-presence" / "writer.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_isolated_lease_completion", MODULE_PATH,
    loader=SourceFileLoader("yuva_isolated_lease_completion", str(MODULE_PATH)))
writer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(writer)


class LeaseCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-lease-complete-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / writer.FIXTURE_MARKER).write_text(
            writer.FIXTURE_MARKER_VALUE, encoding="utf-8")
        self.ledger = self.root / "gorevler.json"
        self.ledger.write_text(json.dumps({
            "schema_version": 1, "siradaki": 2,
            "gorevler": [{"id": 1, "durum": "pending", "assignee": None,
                          "gecmis": []}],
        }), encoding="utf-8")
        self.ledger.chmod(0o600)

    def read_task(self):
        return json.loads(self.ledger.read_text(encoding="utf-8"))["gorevler"][0]

    def test_stale_epoch_is_audited_without_task_snapshot_change_then_current_completes(self):
        epoch_n = writer.claim_task(
            self.root, 1, "old-owner", operation_id="claim-n", claimed_at="t1")

        # Fixture setup models an expiry that has been explicitly reconciled:
        # the prior epoch is closed and the task is available for a new claim.
        expired = self.read_task()
        expired["execution"]["lease_state"] = "closed"
        expired["execution"]["closed_reason"] = "expired_reconciled_in_fixture"
        expired["durum"] = "pending"
        expired["assignee"] = None
        self.ledger.write_text(json.dumps({
            "schema_version": 1, "siradaki": 2, "gorevler": [expired],
        }), encoding="utf-8")
        epoch_n_plus_1 = writer.claim_task(
            self.root, 1, "new-owner", operation_id="claim-n-plus-1", claimed_at="t2")
        self.assertEqual(epoch_n["lease_epoch"] + 1, epoch_n_plus_1["lease_epoch"])

        before = self.ledger.read_bytes()
        stale = writer.complete_task(
            self.root, 1, "old-owner", epoch_n["lease_epoch"],
            operation_id="late-complete", completed_at="t3", note="stale")

        self.assertEqual(stale["result"], "lease_epoch_mismatch")
        self.assertEqual(stale["current_epoch"], epoch_n_plus_1["lease_epoch"])
        self.assertEqual(self.ledger.read_bytes(), before)
        attempts = [json.loads(line) for line in
                    (self.root / writer.ATTEMPT_LOG).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["operation_id"], "late-complete")
        self.assertEqual(attempts[0]["result"], "lease_epoch_mismatch")

        accepted = writer.complete_task(
            self.root, 1, "new-owner", epoch_n_plus_1["lease_epoch"],
            operation_id="current-complete", completed_at="t4", note="delivered")
        self.assertEqual(accepted["result"], "completed")
        task = self.read_task()
        self.assertEqual(task["durum"], "pending_verification")
        self.assertEqual(task["execution"]["lease_state"], "closed")
        self.assertEqual(task["execution"]["completion_operation_id"], "current-complete")
        self.assertEqual([event["olay"] for event in task["gecmis"]], ["teslim"])
        self.assertEqual(task["gecmis"][0]["kimden"], "new-owner")


if __name__ == "__main__":
    unittest.main()
