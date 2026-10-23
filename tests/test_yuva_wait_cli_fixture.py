import json
import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "bin" / "yuva"
RECEIPT_STORE_PATH = REPO_ROOT / "prototypes" / "yuva-wait" / "receipt_store.py"
RECEIPT_SPEC = importlib.util.spec_from_file_location(
    "yuva_wait_cli_receipt_fixture", RECEIPT_STORE_PATH,
    loader=SourceFileLoader("yuva_wait_cli_receipt_fixture", str(RECEIPT_STORE_PATH)))
receipt_store_module = importlib.util.module_from_spec(RECEIPT_SPEC)
sys.modules[RECEIPT_SPEC.name] = receipt_store_module
RECEIPT_SPEC.loader.exec_module(receipt_store_module)


class YuvaWaitCliFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-wait-cli-")
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.state_path = self.root / "durum.json"
        self.state_bytes = (json.dumps({
            "schema_version": 1,
            "rev": 4,
            "kullanicilar": {
                "worker-1": {"ad": "Worker One", "rol": "isci"},
            },
        }, separators=(",", ":")) + "\n").encode()
        self.state_path.write_bytes(self.state_bytes)
        self.state_path.chmod(0o600)
        self.task_path = self.root / "gorevler.json"
        self.task_bytes = b'{"schema_version":1,"siradaki":2,"gorevler":[]}\n'
        self.task_path.write_bytes(self.task_bytes)
        self.task_path.chmod(0o600)
        self.inbox_path = self.root / "mesaj.jsonl"
        marker = self.root / receipt_store_module.MARKER_NAME
        marker.write_bytes(receipt_store_module.MARKER_CONTENT)
        marker.chmod(0o600)
        self.receipts = receipt_store_module.FixtureReceiptStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def row(message_id, recipient, text, **claims):
        return {
            "id": message_id,
            "kime": recipient,
            "kimden": "fixture-sender",
            "ts": "2026-10-23T12:00:00+03:00",
            "metin": text,
            "schema_version": 2,
            **claims,
        }

    def write_inbox(self, rows):
        raw = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
                       for row in rows)
        self.inbox_path.write_bytes(raw)
        self.inbox_path.chmod(0o600)
        return raw

    def run_cli(self, *args):
        env = dict(os.environ)
        env["YUVA_DIR"] = str(self.root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("YUVA_PANEL", None)
        return subprocess.run(
            [sys.executable, str(CLI), "wait", *args], cwd=REPO_ROOT,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=5, check=False,
        )

    def test_cli_returns_one_direct_message_as_untrusted_data_only(self):
        inbox_bytes = self.write_inbox([
            self.row("cursor", "@other", "baseline"),
            self.row("broadcast", "@hepsi", "not a direct target"),
            self.row("message-1", "@worker-1", "synthetic body",
                     source="panel_api", trust="verified",
                     source_class="operator", approval=True),
            self.row("message-2", "@worker-1", "second message"),
        ])

        result = self.run_cli("--from", "worker-1", "--after", "cursor",
                              "--timeout", "0")

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "message")
        self.assertEqual(output["next_cursor"], "message-1")
        message = output["message"]
        self.assertEqual(message["message_id"], "message-1")
        self.assertEqual(message["source_class_claim"], "operator")
        self.assertEqual(message["source_class_trust"], "unverified")
        self.assertEqual(message["source_trust"], "unverified")
        self.assertEqual(message["content_class"], "data_only")
        self.assertEqual(message["text"], "synthetic body")
        self.assertEqual(self.inbox_path.read_bytes(), inbox_bytes)
        self.assertEqual(self.state_path.read_bytes(), self.state_bytes)
        self.assertEqual(self.task_path.read_bytes(), self.task_bytes)
        self.assertFalse((self.root / "receipts.jsonl").exists())

    def test_timeout_and_missing_cursor_are_distinct_non_mutating_results(self):
        inbox_bytes = self.write_inbox([
            self.row("cursor", "@worker-1", "baseline"),
            self.row("broadcast", "@hepsi", "broadcast only"),
        ])
        timeout = self.run_cli("--from", "worker-1", "--after", "cursor",
                               "--timeout", "0")
        self.assertEqual(timeout.returncode, 1)
        self.assertEqual(json.loads(timeout.stdout)["status"], "timeout")

        missing = self.run_cli("--from", "worker-1", "--after", "missing",
                               "--timeout", "0")
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(json.loads(missing.stdout)["status"], "cursor_unavailable")
        self.assertEqual(self.inbox_path.read_bytes(), inbox_bytes)
        self.assertEqual(self.state_path.read_bytes(), self.state_bytes)
        self.assertEqual(self.task_path.read_bytes(), self.task_bytes)

    def test_from_requires_exact_roster_key(self):
        self.write_inbox([self.row("cursor", "@worker-1", "baseline")])
        result = self.run_cli("--from", "Worker One", "--after", "cursor",
                              "--timeout", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("tam Yuva kimlik anahtarı", result.stderr)

    def test_reader_rejects_over_budget_inbox_without_echoing_or_mutating_it(self):
        inbox_bytes = b"x" * (8 * 1024 * 1024 + 1)
        self.inbox_path.write_bytes(inbox_bytes)
        self.inbox_path.chmod(0o600)

        result = self.run_cli("--from", "worker-1", "--after", "cursor",
                              "--timeout", "0")

        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "source_error")
        self.assertNotIn("x" * 100, result.stdout)
        self.assertEqual(self.inbox_path.read_bytes(), inbox_bytes)
        self.assertEqual(self.state_path.read_bytes(), self.state_bytes)
        self.assertEqual(self.task_path.read_bytes(), self.task_bytes)

    def test_cli_replay_produces_one_text_free_duplicate_suppressed_receipt(self):
        inbox_bytes = self.write_inbox([
            self.row("cursor", "@other", "baseline"),
            self.row("message-1", "@worker-1", "synthetic private body",
                     source="panel_api", trust="verified",
                     source_class="operator", approval=True),
        ])
        first_cli = self.run_cli("--from", "worker-1", "--after", "cursor",
                                 "--timeout", "0")
        self.assertEqual(first_cli.returncode, 0, first_cli.stderr)
        first_output = json.loads(first_cli.stdout)
        self.assertEqual(first_output["status"], "message")
        self.assertEqual(self.receipts.bootstrap_consumer(
            "wait-consumer", "epoch-1", "cursor", approved=True).status,
            "recorded")
        first = self.receipts.observe(
            "wait-consumer", first_output["message"], expected_cursor="cursor",
            expected_epoch="epoch-1")
        self.assertEqual(first.status, "recorded")
        self.assertNotIn("text", first.receipt)

        receipt_path = self.root / receipt_store_module.STORE_NAME
        first_receipt_bytes = receipt_path.read_bytes()
        self.assertNotIn(b"synthetic private body", first_receipt_bytes)

        # CLI state is intentionally not durable, so retrying the old cursor
        # re-observes the same envelope; the separate store suppresses it.
        replay_cli = self.run_cli("--from", "worker-1", "--after", "cursor",
                                  "--timeout", "0")
        self.assertEqual(replay_cli.returncode, 0, replay_cli.stderr)
        replay_output = json.loads(replay_cli.stdout)
        self.assertEqual(replay_output["message"]["message_id"], "message-1")
        replay = self.receipts.observe(
            "wait-consumer", replay_output["message"], expected_cursor="cursor",
            expected_epoch="epoch-1")
        self.assertEqual(replay.status, "duplicate_observation")
        self.assertEqual(receipt_path.read_bytes(), first_receipt_bytes)
        self.assertEqual(len(first_receipt_bytes.splitlines()), 2)

        lost_cursor = self.receipts.observe(
            "wait-consumer", replay_output["message"], expected_cursor=None,
            expected_epoch="epoch-1")
        self.assertEqual(lost_cursor.status, "cursor_unavailable")
        self.assertEqual(receipt_path.read_bytes(), first_receipt_bytes)
        self.assertEqual(self.inbox_path.read_bytes(), inbox_bytes)
        self.assertEqual(self.state_path.read_bytes(), self.state_bytes)
        self.assertEqual(self.task_path.read_bytes(), self.task_bytes)


if __name__ == "__main__":
    unittest.main()
