from __future__ import annotations

import hashlib
import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO


ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = ROOT / "prototypes" / "history-secret-scan" / "scanner.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_history_secret_scan_canary", SCANNER_PATH,
    loader=SourceFileLoader("yuva_history_secret_scan_canary", str(SCANNER_PATH)))
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


class HistoricalSecretScanCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-secret-canary-")
        self.parent = Path(self.temp.name)
        self.root = self.parent / "fixture"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        marker = self.root / scanner.MARKER
        marker.write_bytes(scanner.MARKER_VALUE)
        marker.chmod(0o600)
        self.screen = self.root / "ekran"
        self.screen.mkdir(mode=0o700)
        self.screen.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def write_chat(self, records):
        path = self.root / "mesaj.jsonl"
        raw = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
                       for row in records)
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    def write_screen(self, name, records):
        path = self.screen / (name + ".jsonl")
        raw = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
                       for row in records)
        path.write_bytes(raw)
        path.chmod(0o600)
        return path

    @staticmethod
    def screen_record(line, name="synthetic-agent"):
        return {"ts": "2026-10-23T12:00:00+03:00", "kimlik": "canary-agent",
                "ad": name, "tur": "sonuc", "satir": line}

    def capture_cli(self):
        output = StringIO()
        with redirect_stdout(output):
            status = scanner.main(["--fixture-root", str(self.root)])
        return status, output.getvalue()

    def test_known_synthetic_canaries_are_counted_without_echoing_sensitive_data(self):
        canaries = (
            "SYNTHETIC_BEARER_CANARY_123456789",
            "SYNTHETIC_API_KEY_CANARY_123456789",
        )
        screen_token = "ghp_" + "A" * 24
        chat = self.write_chat([{
            "schema_version": 1,
            "metin": "Authorization: Bearer " + canaries[0],
            "ad": "api_key=" + canaries[1],
        }])
        screen = self.write_screen("synthetic-agent", [self.screen_record(
            "output " + screen_token)])
        before = {path: (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
                  for path in (chat, screen)}
        raw_hashes = {hashlib.sha256(item[0]).hexdigest() for item in before.values()}

        status, output = self.capture_cli()
        report = json.loads(output)
        self.assertEqual(0, status)
        self.assertEqual("known_pattern_found", report["scan_state"])
        self.assertEqual("known_patterns_content_fields_only", report["policy"])
        self.assertEqual(2, report["files_scanned"])
        self.assertEqual(2, report["records_scanned"])
        self.assertEqual(3, report["fields_with_known_credential_pattern"])
        self.assertEqual(0, report["files_rejected"])
        self.assertEqual([], report["partial_reasons"])
        for secret in (*canaries, screen_token, str(self.root), str(chat),
                       str(screen), *raw_hashes, "Authorization: Bearer", "api_key="):
            self.assertNotIn(secret, output)
        for path, (raw, mode, mtime_ns) in before.items():
            self.assertEqual(raw, path.read_bytes())
            self.assertEqual(mode, path.stat().st_mode)
            self.assertEqual(mtime_ns, path.stat().st_mtime_ns)

    def test_unknown_pattern_result_does_not_claim_secret_free(self):
        unknown = "SYNTHETIC_UNRECOGNIZED_CANARY_XYZ_987654"
        path = self.write_chat([{"metin": unknown}])
        self.write_screen("synthetic-agent", [self.screen_record("benign fixture")])
        before = path.read_bytes()

        status, output = self.capture_cli()
        report = json.loads(output)
        self.assertEqual(0, status)
        self.assertEqual("no_known_pattern_detected", report["scan_state"])
        self.assertEqual(0, report["fields_with_known_credential_pattern"])
        self.assertEqual("known_patterns_content_fields_only", report["policy"])
        self.assertNotIn(unknown, output)
        self.assertEqual(before, path.read_bytes())

    def test_malformed_row_is_rejected_as_partial_and_report_stays_content_free(self):
        secret = "SYNTHETIC_MALFORMED_CANARY_123456"
        chat = self.write_chat([{"metin": "benign fixture"}])
        malformed = self.screen / "broken.jsonl"
        malformed.write_bytes(("{invalid Authorization: Bearer " + secret + "}\n")
                              .encode("utf-8"))
        malformed.chmod(0o600)
        self.write_screen("valid-agent", [self.screen_record("benign")])
        before = {path: path.read_bytes() for path in (chat, malformed)}
        hashes = {hashlib.sha256(raw).hexdigest() for raw in before.values()}

        status, output = self.capture_cli()
        report = json.loads(output)
        self.assertEqual(2, status)
        self.assertEqual("partial", report["scan_state"])
        self.assertEqual(1, report["files_rejected"])
        self.assertEqual(2, report["files_scanned"])
        self.assertIn("record_unscannable", report["partial_reasons"])
        for value in (secret, str(self.root), str(malformed), *hashes,
                      "Authorization: Bearer", "{invalid"):
            self.assertNotIn(value, output)
        for path, raw in before.items():
            self.assertEqual(raw, path.read_bytes())

    def test_oversize_file_is_rejected_without_partial_clean_result(self):
        chat = self.write_chat([{"metin": "benign"}])
        oversized = self.screen / "oversize.jsonl"
        oversized.write_bytes(b"x" * (scanner.MAX_FILE_BYTES + 1))
        oversized.chmod(0o600)
        self.write_screen("valid-agent", [self.screen_record("benign")])
        before = hashlib.sha256(oversized.read_bytes()).hexdigest()

        report = scanner.scan_fixture(self.root)
        self.assertEqual("partial", report["scan_state"])
        self.assertEqual(1, report["files_rejected"])
        self.assertIn("unsafe_or_oversized_file", report["partial_reasons"])
        self.assertEqual(before, hashlib.sha256(oversized.read_bytes()).hexdigest())
        encoded = json.dumps(report, sort_keys=True)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn(str(oversized), encoded)
        self.assertNotIn(before, encoded)
        self.assertEqual(b"x" * (scanner.MAX_FILE_BYTES + 1), oversized.read_bytes())
        self.assertTrue(chat.exists())

    def test_symlink_screen_input_is_rejected_and_not_followed(self):
        secret = "SYNTHETIC_SYMLINK_CANARY_123456"
        self.write_chat([{"metin": "benign"}])
        target = self.parent / "outside.jsonl"
        target.write_text(json.dumps(self.screen_record(secret)) + "\n",
                          encoding="utf-8")
        target.chmod(0o600)
        link = self.screen / "linked.jsonl"
        link.symlink_to(target)
        self.write_screen("valid-agent", [self.screen_record("benign")])
        target_before = target.read_bytes()

        status, output = self.capture_cli()
        report = json.loads(output)
        self.assertEqual(2, status)
        self.assertEqual("partial", report["scan_state"])
        self.assertEqual(1, report["files_rejected"])
        self.assertIn("unsafe_or_oversized_file", report["partial_reasons"])
        for value in (secret, str(self.root), str(link), str(target)):
            self.assertNotIn(value, output)
        self.assertEqual(target_before, target.read_bytes())
        self.assertTrue(link.is_symlink())
        self.assertEqual(2, report["files_scanned"])


if __name__ == "__main__":
    unittest.main()
