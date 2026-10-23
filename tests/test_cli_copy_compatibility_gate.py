import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "prototypes" / "cli-copy-compatibility" / "gate.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_cli_copy_compatibility_gate_fixture", PATH,
    loader=SourceFileLoader("yuva_cli_copy_compatibility_gate_fixture", str(PATH)))
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


class CliCopyCompatibilityGateTests(unittest.TestCase):
    def profile(self, **overrides):
        profile = {
            "sha256": "a" * 64,
            "source_role": "canonical",
            "recovery_only": False,
            "uses_shared_lock": True,
            "locks_full_read_modify_write": True,
            "validates_schema_version": True,
            "preserves_schema_version": True,
            "schema_version": 1,
            "supported_schema_versions": [1],
        }
        profile.update(overrides)
        return profile

    def test_only_pinned_canonical_complete_contract_is_allowed(self):
        decision = gate.task_writer_decision(self.profile(), approved_sha256="a" * 64)
        self.assertEqual(decision, gate.GateDecision(True, "canonical_writer_compatible"))

    def test_noncanonical_recovery_unlocked_unknown_schema_and_missing_proof_deny(self):
        cases = (
            (self.profile(source_role="development"), "writer_not_canonical"),
            (self.profile(recovery_only=True), "recovery_copy_read_only"),
            (self.profile(uses_shared_lock=False), "lock_contract_unproven"),
            (self.profile(locks_full_read_modify_write=False), "lock_contract_unproven"),
            (self.profile(validates_schema_version=False), "schema_contract_unproven"),
            (self.profile(preserves_schema_version=False), "schema_contract_unproven"),
            (self.profile(schema_version=99), "schema_version_unsupported"),
            (self.profile(schema_version=True), "schema_version_unsupported"),
            ({"sha256": "a" * 64}, "writer_profile_incomplete"),
        )
        for profile, reason in cases:
            with self.subTest(reason=reason, profile=profile):
                decision = gate.task_writer_decision(profile, approved_sha256="a" * 64)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, reason)

    def test_hash_mismatch_and_malformed_approval_fail_closed(self):
        mismatch = gate.task_writer_decision(self.profile(), approved_sha256="b" * 64)
        self.assertEqual(mismatch.reason, "writer_hash_unapproved")
        malformed = gate.task_writer_decision(self.profile(), approved_sha256="not-a-hash")
        self.assertEqual(malformed.reason, "approved_writer_hash_invalid")


if __name__ == "__main__":
    unittest.main()
