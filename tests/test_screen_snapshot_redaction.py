import importlib.util
import json
import logging
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE_PATH = (REPO_ROOT / "prototypes" / "screen-snapshot-redaction"
                  / "project_fixture.py")


def load_prototype():
    spec = importlib.util.spec_from_file_location(
        "yuva_screen_snapshot_redaction_test",
        PROTOTYPE_PATH,
        loader=SourceFileLoader("yuva_screen_snapshot_redaction_test",
                                str(PROTOTYPE_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScreenSnapshotRedactionTests(unittest.TestCase):
    def setUp(self):
        self.prototype = load_prototype()
        self.temp = tempfile.TemporaryDirectory(prefix="screen-snapshot-redaction-")
        self.root = Path(self.temp.name) / "fixture"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        marker = self.root / self.prototype.MARKER_NAME
        marker.write_bytes(self.prototype.MARKER_CONTENT)
        marker.chmod(0o600)
        self.screen_dir = self.root / "ekran"
        self.screen_dir.mkdir(mode=0o700)
        self.screen_dir.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def write_records(self, name, records):
        path = self.screen_dir / (name + ".jsonl")
        path.write_bytes(b"".join(
            (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
            for record in records))
        path.chmod(0o600)
        return path

    def record(self, line):
        return {
            "ts": "2026-10-23T12:00:00+03:00",
            "kimlik": "fixture-agent",
            "ad": "Fixture Agent",
            "tur": "sonuc",
            "satir": line,
        }

    def test_redact_policy_scrubs_snapshot_ui_projection_and_log_without_writing(self):
        secret = "SYNTHETIC_SNAPSHOT_BEARER_123456789"
        path = self.write_records("fixture-agent", [self.record(
            "healthy output; Authorization: Bearer " + secret)])
        before = path.read_bytes()

        with self.assertLogs(self.prototype._logger, level=logging.INFO) as captured:
            snapshot = self.prototype.project_fixture_snapshot(self.root, "redact")

        api_body = json.dumps(snapshot, ensure_ascii=False)
        ui_rows = json.dumps(snapshot["ekranlar"], ensure_ascii=False)
        log_text = "\n".join(captured.output)
        self.assertIn("healthy output", api_body)
        self.assertIn("[REDACTED:credential]", ui_rows)
        self.assertEqual(snapshot["ekranlar_meta"]["redacted_records"], 1)
        self.assertNotIn(secret, api_body)
        self.assertNotIn(secret, ui_rows)
        self.assertNotIn(secret, log_text)
        self.assertEqual(path.read_bytes(), before)

    def test_reject_policy_omits_sensitive_file_and_keeps_source_unchanged(self):
        secret = "SYNTHETIC_REJECTED_VALUE_ABCDEFGHI"
        path = self.write_records("fixture-agent", [self.record(
            "token=" + secret), self.record("benign second row")])
        before = path.read_bytes()

        with self.assertLogs(self.prototype._logger, level=logging.INFO) as captured:
            snapshot = self.prototype.project_fixture_snapshot(self.root, "reject")

        self.assertEqual(snapshot["ekranlar"], {})
        self.assertEqual(snapshot["ekranlar_meta"]["rejected_files"], 1)
        self.assertIn("sensitive_file_rejected",
                      snapshot["ekranlar_meta"]["partial_reasons"])
        self.assertNotIn(secret, json.dumps(snapshot, ensure_ascii=False))
        self.assertNotIn(secret, "\n".join(captured.output))
        self.assertEqual(path.read_bytes(), before)

    def test_malformed_record_rejects_whole_file_without_raw_error_or_mutation(self):
        secret = "SYNTHETIC_MALFORMED_VALUE_ZYXWVUT"
        path = self.screen_dir / "fixture-agent.jsonl"
        raw = (b'{"ts":"broken","satir":"Authorization: Bearer '
               + secret.encode("ascii") + b'"\n')
        path.write_bytes(raw)
        path.chmod(0o600)

        with self.assertLogs(self.prototype._logger, level=logging.INFO) as captured:
            snapshot = self.prototype.project_fixture_snapshot(self.root, "redact")

        self.assertEqual(snapshot["ekranlar"], {})
        self.assertEqual(snapshot["ekranlar_meta"]["rejected_files"], 1)
        self.assertIn("invalid_or_unredactable_record",
                      snapshot["ekranlar_meta"]["partial_reasons"])
        self.assertNotIn(secret, json.dumps(snapshot, ensure_ascii=False))
        self.assertNotIn(secret, "\n".join(captured.output))
        self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
