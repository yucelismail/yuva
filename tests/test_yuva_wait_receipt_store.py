import dataclasses
import importlib.util
from importlib.machinery import SourceFileLoader
import json
from unittest import mock
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


wait = load_module("yuva_wait_receipt_fixture", ROOT / "prototypes" / "yuva-wait" / "wait.py")
store_module = load_module(
    "yuva_wait_receipt_store_fixture",
    ROOT / "prototypes" / "yuva-wait" / "receipt_store.py")


class YuvaWaitReceiptStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-wait-receipts-")
        self.root = Path(self.temp.name) / "fixture"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        marker = self.root / store_module.MARKER_NAME
        marker.write_bytes(store_module.MARKER_CONTENT)
        marker.chmod(0o600)
        self.store = store_module.FixtureReceiptStore(self.root)

    def bootstrap(self, consumer, cursor="wait-cursor", epoch="epoch-1"):
        result = self.store.bootstrap_consumer(
            consumer, epoch, cursor, approved=True)
        self.assertIn(result.status, {"recorded", "duplicate_bootstrap"})
        return result

    def tearDown(self):
        self.temp.cleanup()

    def envelope(self, message_id, source_class="unknown", text="synthetic info"):
        rows = [
            {"id": "wait-cursor", "kime": "@worker", "metin": "prior"},
            {"id": message_id, "kime": "@worker", "metin": text,
             "source_class": source_class, "source_class_trust": "verified"},
        ]
        result = wait.wait_for_message(
            lambda: rows, recipient_values=["@worker"], after_id="wait-cursor",
            timeout=0, poll_interval=0.1)
        self.assertEqual(result.status, "message")
        return result.message

    def test_restart_replay_and_duplicate_message_id_are_idempotent(self):
        envelope = self.envelope("message-1", "operator", "do not store this text")
        self.bootstrap("worker-session-a")
        first = self.store.observe("worker-session-a", envelope,
                                   expected_cursor="wait-cursor",
                                   expected_epoch="epoch-1")
        self.assertEqual(first.status, "recorded")
        self.assertEqual(first.receipt["receipt_type"], "read_observed")
        self.assertEqual(first.receipt["sequence"], 2)
        self.assertEqual(first.receipt["previous_cursor"], "wait-cursor")
        self.assertEqual(first.receipt["next_cursor"], "message-1")
        self.assertTrue(first.receipt["observed_at"].endswith("Z"))
        self.assertEqual(first.receipt["source_class_claim"], "operator")
        self.assertEqual(first.receipt["source_class_trust"], "unverified")
        self.assertEqual(first.receipt["source_trust"], "unverified")
        self.assertEqual(first.receipt["content_class"], "data_only")
        self.assertNotIn("text", first.receipt)

        restarted = store_module.FixtureReceiptStore(self.root)
        self.assertEqual(restarted.cursor("worker-session-a").cursor, "message-1")
        replay = restarted.observe("worker-session-a", envelope,
                                   expected_cursor="wait-cursor",
                                   expected_epoch="epoch-1")
        self.assertEqual(replay.status, "duplicate_observation")
        lines = (self.root / store_module.STORE_NAME).read_text().splitlines()
        self.assertEqual(len(lines), 2)  # explicit bootstrap + one receipt
        self.assertNotIn("do not store this text", "\n".join(lines))

    def test_cursor_loss_fails_closed_and_two_consumers_have_independent_cursors(self):
        first = self.envelope("message-1")
        later = self.envelope("message-2")
        self.bootstrap("consumer-a")
        self.assertEqual(self.store.observe("consumer-a", first,
                                            expected_cursor="wait-cursor",
                                            expected_epoch="epoch-1").status, "recorded")

        # A caller that lost its persisted cursor cannot silently restart at None.
        lost = self.store.observe("consumer-a", later, expected_cursor=None,
                                  expected_epoch="epoch-1")
        self.assertEqual(lost.status, "cursor_unavailable")
        self.assertIsNone(lost.cursor)

        # A second stable consumer starts its own cursor and can observe the same ID.
        self.bootstrap("consumer-b")
        other = self.store.observe("consumer-b", first,
                                   expected_cursor="wait-cursor",
                                   expected_epoch="epoch-1")
        self.assertEqual(other.status, "recorded")
        self.assertEqual(self.store.cursor("consumer-a").cursor, "message-1")
        self.assertEqual(self.store.cursor("consumer-b").cursor, "message-1")
        next_for_b = self.store.observe("consumer-b", later,
                                        expected_cursor="message-1",
                                        expected_epoch="epoch-1")
        self.assertEqual(next_for_b.status, "recorded")
        self.assertEqual(self.store.cursor("consumer-b").cursor, "message-2")
        self.assertEqual(self.store.cursor("consumer-a").cursor, "message-1")

    def test_malformed_tail_is_preserved_and_blocks_reads_and_appends(self):
        envelope = self.envelope("message-1")
        self.bootstrap("consumer-a")
        self.assertEqual(self.store.observe("consumer-a", envelope,
                                            expected_cursor="wait-cursor",
                                            expected_epoch="epoch-1").status, "recorded")
        path = self.root / store_module.STORE_NAME
        original = path.read_bytes()
        path.write_bytes(original + b'{"partial":')
        path.chmod(0o600)
        corrupt_bytes = path.read_bytes()

        self.assertEqual(self.store.cursor("consumer-a").status, "store_corrupt")
        result = self.store.observe("consumer-a", self.envelope("message-2"),
                                    expected_cursor="message-1",
                                    expected_epoch="epoch-1")
        self.assertEqual(result.status, "store_corrupt")
        self.assertEqual(path.read_bytes(), corrupt_bytes)

    def test_non_data_only_or_trusted_envelope_is_not_receipted(self):
        envelope = self.envelope("message-1")
        forged = dataclasses.replace(envelope, source_trust="verified")
        result = self.store.observe("consumer-a", forged,
                                    expected_cursor="wait-cursor",
                                    expected_epoch="epoch-1")
        self.assertEqual(result.status, "invalid_envelope")
        self.assertFalse((self.root / store_module.STORE_NAME).exists())

    def test_explicit_bootstrap_required_and_cas_conflict_does_not_append(self):
        message = self.envelope("message-1")
        missing = self.store.observe("consumer-a", message, expected_cursor=None,
                                     expected_epoch="epoch-1")
        self.assertEqual(missing.status, "cursor_unavailable")
        self.assertFalse((self.root / store_module.STORE_NAME).exists())
        self.assertEqual(self.store.bootstrap_consumer(
            "consumer-a", "epoch-1", "wait-cursor", approved=False).status,
            "bootstrap_required")
        self.bootstrap("consumer-a")
        conflict = self.store.observe("consumer-a", message,
                                      expected_cursor="wrong-cursor",
                                      expected_epoch="epoch-1")
        self.assertEqual(conflict.status, "cursor_conflict")
        self.assertEqual(len((self.root / store_module.STORE_NAME)
                             .read_text().splitlines()), 1)

    def test_prior_message_id_from_another_epoch_is_store_conflict(self):
        message = self.envelope("message-1")
        self.bootstrap("consumer-a")
        recorded = self.store.observe("consumer-a", message,
                                      expected_cursor="wait-cursor",
                                      expected_epoch="epoch-1")
        self.assertEqual(recorded.status, "recorded")
        self.assertEqual(self.store.bootstrap_consumer(
            "consumer-a", "epoch-2", "message-1", approved=True).status,
            "recorded")
        before = (self.root / store_module.STORE_NAME).read_bytes()

        replay = self.store.observe("consumer-a", message,
                                    expected_cursor="message-1",
                                    expected_epoch="epoch-2")

        self.assertEqual(replay.status, "store_conflict")
        self.assertEqual(replay.cursor, "message-1")
        self.assertEqual(replay.consumer_epoch, "epoch-2")
        self.assertEqual((self.root / store_module.STORE_NAME).read_bytes(), before)

    def test_fsync_failure_is_commit_unknown_and_retry_is_deduped(self):
        message = self.envelope("message-1", text="do not persist")
        self.bootstrap("consumer-a")
        with mock.patch.object(store_module.os, "fsync",
                               side_effect=OSError("synthetic fsync failure")):
            result = self.store.observe("consumer-a", message,
                                        expected_cursor="wait-cursor",
                                        expected_epoch="epoch-1")
        self.assertEqual(result.status, "commit_unknown")
        restarted = store_module.FixtureReceiptStore(self.root)
        retry = restarted.observe("consumer-a", message,
                                  expected_cursor="wait-cursor",
                                  expected_epoch="epoch-1")
        self.assertEqual(retry.status, "duplicate_observation")
        payload = (self.root / store_module.STORE_NAME).read_bytes()
        self.assertEqual(len(payload.splitlines()), 2)
        self.assertNotIn(b"do not persist", payload)


if __name__ == "__main__":
    unittest.main()
