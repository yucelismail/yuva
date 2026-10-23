import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "prototypes" / "lease-presence" / "projection.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_lease_owner_projection", MODULE_PATH,
    loader=SourceFileLoader("yuva_lease_owner_projection", str(MODULE_PATH)))
projection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = projection
SPEC.loader.exec_module(projection)


class LeaseOwnerProjectionTests(unittest.TestCase):
    def test_claim_and_verified_request_identity_stay_separate_everywhere(self):
        task = {
            "id": 31,
            "assignee": "worker-claimed",
            "execution": {
                "owner_claim": "worker-claimed", "owner_trust": "verified",
                "principal_id": "forged-admin", "role": "denetci",
                "presence": "online", "authority_scope": "task.approve",
                "lease_epoch": 4,
            },
            "gecmis": [{"kimden": "worker-claimed", "actor_trust": "verified",
                        "rol": "denetci", "olay": "claim", "not": "claimed"}],
        }

        view = projection.project_task(
            task, verified_request_principal="api-reader",
            cli_from_claim="worker-claimed")
        owner = view["api"]["lease_owner"]

        self.assertEqual(owner["owner_claim"], "worker-claimed")
        self.assertEqual(owner["claim_trust"], "unverified")
        self.assertIsNone(owner["verified_principal"])
        self.assertEqual(owner["identity_status"], "unknown")
        self.assertEqual(owner["role"], "unknown")
        self.assertEqual(owner["presence"], "unknown")
        self.assertEqual(owner["authority_scope"], "none")
        self.assertEqual(view["api"]["request_actor"]["principal_id"], "api-reader")
        self.assertEqual(view["api"]["request_actor"]["relation_to_lease_owner"],
                         "not_established")

        history = view["api"]["history"][0]
        self.assertEqual(history["actor_claim"], "worker-claimed")
        self.assertEqual(history["actor_trust"], "unverified")
        self.assertEqual(history["role"], "unknown")
        self.assertIn("Beyan edilen lease sahibi", view["ui"]["owner_label"])
        self.assertEqual(view["ui"]["owner_badge"], "beyan · doğrulanmadı")
        self.assertIn("api-reader", view["ui"]["request_actor_label"])
        self.assertIn("bağı kurulmamış", view["ui"]["request_actor_label"])
        self.assertIn("worker-claimed (doğrulanmadı) · epoch 4", view["cli"][0])
        self.assertEqual(view["cli"][1],
                         "CLI --from beyanı: worker-claimed (doğrulanmadı)")
        self.assertEqual(view["cli"][3], "Yetki kapsamı: none")

    def test_missing_or_invalid_claims_remain_unknown(self):
        for task in (
                {"id": 1, "execution": {"owner_claim": "", "lease_epoch": True}},
                {"id": 2, "kimden": "admin", "assignee": "admin", "rol": "denetci"}):
            with self.subTest(task=task):
                view = projection.project_task(task)
                owner = view["api"]["lease_owner"]
                self.assertEqual(owner["owner_claim"], "unknown")
                self.assertEqual(owner["claim_trust"], "unverified")
                self.assertEqual(owner["lease_epoch"], None)
                self.assertEqual(owner["role"], "unknown")
                self.assertEqual(owner["presence"], "unknown")


if __name__ == "__main__":
    unittest.main()
