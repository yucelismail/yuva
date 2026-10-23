import unittest

import release_acceptance


class ReleaseAcceptanceTests(unittest.TestCase):
    def test_missing_unknown_and_false_gates_are_no_go(self):
        passed = {name: True for name in release_acceptance.REQUIRED_GATES}
        self.assertEqual(release_acceptance.evaluate_gates(passed)["decision"], "GO")
        for value in (None, "unknown", False):
            with self.subTest(value=value):
                evidence = dict(passed)
                evidence["fixture_writer_sequential"] = value
                result = release_acceptance.evaluate_gates(evidence)
                self.assertEqual(result["decision"], "NO-GO")
                self.assertIn("fixture_writer_sequential", result["failed_gates"])
        self.assertEqual(release_acceptance.evaluate_gates({})["decision"], "NO-GO")

    def test_schema_rollback_requires_known_equal_contract(self):
        known = {"data_contract": {"schema_compatibility":
                                   release_acceptance.KNOWN_DATA_CONTRACT}}
        unknown = {"data_contract": {"schema_compatibility": "unspecified"}}
        self.assertTrue(release_acceptance.schema_rollback_compatible(known, known))
        self.assertFalse(release_acceptance.schema_rollback_compatible(known, unknown))
        self.assertFalse(release_acceptance.schema_rollback_compatible(unknown, unknown))

    def test_full_acceptance_sequence_uses_only_temporary_fixtures(self):
        report = release_acceptance.run_fixture_harness()
        self.assertEqual(report["fixture_decision"], "GO", report)
        self.assertEqual(report["fixture_failed_gates"], [])
        self.assertTrue(report["fixture_target_checks"]["path_entry_is_symlink"])
        self.assertTrue(report["fixture_target_checks"]["path_entry_current_cli"])
        self.assertTrue(report["fixture_target_checks"]["unit_panel_current"])
        self.assertTrue(report["fixture_target_checks"]["unit_workdir_current"])
        self.assertTrue(report["fixture_target_checks"]["unit_data_fixture"])
        self.assertTrue(report["fixture_target_checks"]["unit_data_external"])
        self.assertTrue(all(report["rollback_target_checks"].values()))
        self.assertEqual(report["host_rollout_decision"], "NO-GO")
        self.assertIn("does not inspect or prove host writer/process identity",
                      report["fixture_writer_scope"])
        self.assertTrue(report["unknown_schema_is_no_go"])
        self.assertEqual(report["unknown_writer_decision"], "NO-GO")
        self.assertEqual(report["payload_path_checks"], {
            "malformed_path_rejected": True,
            "escaping_symlink_rejected": True,
            "dangling_symlink_rejected": True,
        })
        self.assertTrue(report["temporary_roots_removed_on_exit"])


if __name__ == "__main__":
    unittest.main()
