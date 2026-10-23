import sys
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "prototypes" / "rollback-data-decision"))
import decision


class RollbackDataDecisionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.actual_records = {
            "durum": {"schema_version": 1, "rev": 4, "kullanicilar": {}},
            "gorevler": {
                "schema_version": 1,
                "siradaki": 2,
                "gorevler": [{
                    "id": 1, "baslik": "synthetic task", "kimden": "fixture",
                    "durum": "pending", "gecmis": [],
                    "ledger": {"writer_epoch": 8, "future": {"tag": "keep-me"}},
                }],
            },
            "mesajlar": [
                {"mesaj": "legacy"},
                {"schema_version": 1, "mesaj": "v1"},
                {"schema_version": 2, "mesaj": "v2"},
            ],
            "ekran": [{"tur": "ekran", "satir": "synthetic"}],
            "ekran_auxiliary": {"cursor": {"generation": 3, "offset": 12}},
        }
        self.actual = {
            "durum": "v1",
            "gorevler": "v1-ledger-with-nested-extension",
            "mesajlar": "legacy/v1/v2",
            "ekranlar": "unversioned-json-object",
        }
        self.reader = {
            "durum": {"v1"},
            "gorevler": {"v1-ledger-with-nested-extension"},
            "mesajlar": {"legacy/v1/v2"},
            "ekranlar": {"unversioned-json-object"},
        }

    def decide(self, **overrides):
        args = {
            "current_contract": decision.KNOWN_CONTRACT,
            "target_contract": decision.KNOWN_CONTRACT,
            "actual_schema": self.actual,
            "target_reader": self.reader,
            "nested_extra_preservation": True,
            "screen_auxiliary_support": True,
            "writers_frozen": True,
        }
        args.update(overrides)
        return decision.decide_rollback(**args)

    def test_explicit_old_reader_support_is_only_a_candidate(self):
        result = self.decide()
        self.assertEqual(result["decision"], "candidate")
        self.assertIn("actual-schema-supported", result["reasons"])
        self.assertNotEqual(result["decision"], "GO")

    def test_new_nested_ledger_extension_without_preservation_proof_is_hold(self):
        self.assertEqual(
            self.actual_records["gorevler"]["gorevler"][0]["ledger"]["future"]["tag"],
            "keep-me")
        result = self.decide(nested_extra_preservation=None)
        self.assertEqual(result, {
            "decision": "HOLD",
            "reasons": ["nested-extra-preservation-unknown"],
        })

    def test_reader_that_drops_nested_extra_is_no_go(self):
        result = self.decide(nested_extra_preservation=False)
        self.assertEqual(result["decision"], "NO-GO")
        self.assertIn("nested-extra-loss", result["reasons"])

    def test_unversioned_screen_auxiliary_state_without_reader_contract_is_hold(self):
        self.assertEqual(self.actual_records["ekran_auxiliary"]["cursor"]["offset"], 12)
        result = self.decide(screen_auxiliary_support=None)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("screen-auxiliary-unknown", result["reasons"])

    def test_unknown_target_reader_is_hold(self):
        reader = dict(self.reader)
        reader["gorevler"] = "unknown"
        result = self.decide(target_reader=reader)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("target-reader-unknown", result["reasons"])

    def test_new_actual_schema_rejected_by_old_reader_is_no_go(self):
        actual = dict(self.actual)
        actual["gorevler"] = "v2"
        result = self.decide(actual_schema=actual)
        self.assertEqual(result["decision"], "NO-GO")
        self.assertIn("target-reader-incompatible", result["reasons"])

    def test_equal_manifest_id_does_not_hide_unknown_auxiliary_store(self):
        result = self.decide(screen_auxiliary_support=None)
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["reasons"], ["screen-auxiliary-unknown"])

    def test_unknown_contract_or_unfrozen_writer_stays_hold(self):
        self.assertEqual(self.decide(target_contract="unknown")["decision"], "HOLD")
        self.assertEqual(self.decide(writers_frozen=None)["decision"], "HOLD")

    def test_recognized_but_unequal_contracts_are_no_go(self):
        result = self.decide(target_contract="yuva-data-contract/v2")
        self.assertEqual(result["decision"], "NO-GO")
        self.assertIn("contract-mismatch", result["reasons"])


if __name__ == "__main__":
    unittest.main()
