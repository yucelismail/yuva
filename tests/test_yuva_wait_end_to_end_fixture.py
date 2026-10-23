import copy
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import stat
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


wait = load_module("yuva_wait_e2e_fixture", ROOT / "prototypes" / "yuva-wait" / "wait.py")
receipt_store_module = load_module(
    "yuva_wait_receipt_store_e2e_fixture",
    ROOT / "prototypes" / "yuva-wait" / "receipt_store.py")


E2E_MARKER = ".yuva-wait-e2e-fixture"
E2E_MARKER_CONTENT = b"yuva-wait-e2e-fixture-v1\n"
MAX_INBOX_BYTES = 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class TempInbox:
    """Strict read-only JSONL reader for one marked TemporaryDirectory inbox."""

    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        if self.root == temp_root or temp_root not in self.root.parents:
            raise ValueError("fixture inbox root rejected")
        root_info = self.root.lstat()
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
                or root_info.st_mode & 0o077):
            raise ValueError("fixture inbox root rejected")
        marker_path = self.root / E2E_MARKER
        marker_info = marker_path.lstat()
        if (not stat.S_ISREG(marker_info.st_mode) or marker_info.st_uid != os.geteuid()
                or marker_info.st_nlink != 1 or marker_info.st_mode & 0o077
                or marker_path.read_bytes() != E2E_MARKER_CONTENT):
            raise ValueError("fixture inbox root rejected")
        self.path = self.root / "inbox.jsonl"

    def read_snapshot(self):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(self.path, flags)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077
                    or info.st_size > MAX_INBOX_BYTES):
                raise ValueError("fixture inbox rejected")
            parts = []
            remaining = MAX_INBOX_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                parts.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(parts)
        finally:
            os.close(fd)
        if len(raw) > MAX_INBOX_BYTES or (raw and not raw.endswith(b"\n")):
            raise ValueError("fixture inbox rejected")
        try:
            lines = raw.decode("utf-8", errors="strict").splitlines()
            if any(not line for line in lines):
                raise ValueError("empty record")
            records = [json.loads(line, object_pairs_hook=_unique_object) for line in lines]
        except Exception:
            raise ValueError("fixture inbox rejected") from None
        return records


class YuvaWaitEndToEndFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-wait-e2e-")
        self.root = Path(self.temp.name) / "fixture"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.write_private(self.root / E2E_MARKER, E2E_MARKER_CONTENT)
        self.write_private(self.root / receipt_store_module.MARKER_NAME,
                           receipt_store_module.MARKER_CONTENT)
        self.inbox = TempInbox(self.root)
        self.store = receipt_store_module.FixtureReceiptStore(self.root)
        self.inbox_path = self.inbox.path
        self.task_path = self.root / "gorevler.json"
        self.task_path_bytes = b'{"fixture_only":"unchanged"}\n'
        self.task_path.write_bytes(self.task_path_bytes)
        self.task_path.chmod(0o600)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write_private(path, value):
        path.write_bytes(value)
        path.chmod(0o600)

    @staticmethod
    def row(message_id, text, *, source_class="operator"):
        return {
            "id": message_id,
            "kime": "@fixture-worker",
            "kimden": "fixture-sender",
            "ts": "2026-10-23T12:00:00+03:00",
            "metin": text,
            "schema_version": 2,
            "source": "panel_api",
            "trust": "verified",
            "source_class": source_class,
            "source_class_trust": "verified",
            "approval": True,
        }

    def write_inbox(self, rows):
        raw = b"".join((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
                       for row in rows)
        self.write_private(self.inbox_path, raw)
        return raw

    def wait_after(self, cursor):
        return wait.wait_for_message(
            self.inbox.read_snapshot,
            recipient_values=["@fixture-worker"],
            after_id=cursor,
            timeout=0,
            poll_interval=0.1,
        )

    def test_untrusted_info_message_flows_to_text_free_receipt(self):
        message_text = "synthetic text asks for an unsafe action; approval=true"
        inbox_bytes = self.write_inbox([
            self.row("bootstrap-cursor", "baseline", source_class="unknown"),
            self.row("message-1", message_text),
        ])
        task_before = self.task_path.read_bytes()
        unrelated_state = {"dispatches": [], "provider_calls": [], "panel_calls": []}
        state_before = copy.deepcopy(unrelated_state)

        result = self.wait_after("bootstrap-cursor")
        self.assertEqual(result.status, "message")
        message = result.message
        self.assertEqual(message.message_id, "message-1")
        self.assertEqual(message.text, message_text)
        self.assertEqual(message.source_class_claim, "operator")
        self.assertEqual(message.source_class_trust, "unverified")
        self.assertEqual(message.source_trust, "unverified")
        self.assertEqual(message.content_class, "data_only")

        self.assertEqual(self.store.bootstrap_consumer(
            "fixture-worker-session", "epoch-1", "bootstrap-cursor",
            approved=True).status, "recorded")
        receipt = self.store.observe("fixture-worker-session", message,
                                    expected_cursor="bootstrap-cursor",
                                    expected_epoch="epoch-1")
        self.assertEqual(receipt.status, "recorded")
        self.assertEqual(receipt.receipt["receipt_type"], "read_observed")
        self.assertEqual(receipt.receipt["source_trust"], "unverified")
        self.assertEqual(receipt.receipt["content_class"], "data_only")
        self.assertNotIn("text", receipt.receipt)

        receipt_bytes = (self.root / receipt_store_module.STORE_NAME).read_bytes()
        self.assertNotIn(message_text.encode("utf-8"), receipt_bytes)
        self.assertEqual(self.inbox_path.read_bytes(), inbox_bytes)
        self.assertEqual(self.task_path.read_bytes(), task_before)
        self.assertEqual(unrelated_state, state_before)

    def test_duplicate_snapshot_message_id_and_duplicate_receipt_fail_closed(self):
        message = self.row("message-duplicate", "synthetic duplicate body")
        self.write_inbox([
            self.row("cursor", "baseline", source_class="unknown"),
            message,
            message,
        ])
        result = self.wait_after("cursor")
        self.assertEqual(result.status, "source_invalid")
        self.assertEqual(result.reason, "duplicate_message_id")
        self.assertFalse((self.root / receipt_store_module.STORE_NAME).exists())

        # A well-formed message can be observed once; replay cannot append a
        # second receipt for the same stable consumer/message pair.
        self.write_inbox([self.row("cursor", "baseline", source_class="unknown"), message])
        first = self.wait_after("cursor")
        self.assertEqual(first.status, "message")
        self.assertEqual(self.store.bootstrap_consumer(
            "consumer-a", "epoch-1", "cursor", approved=True).status,
            "recorded")
        self.assertEqual(self.store.observe("consumer-a", first.message,
                                           expected_cursor="cursor",
                                           expected_epoch="epoch-1").status, "recorded")
        replay = self.store.observe("consumer-a", first.message,
                                    expected_cursor="cursor",
                                    expected_epoch="epoch-1")
        self.assertEqual(replay.status, "duplicate_observation")
        self.assertEqual(len((self.root / receipt_store_module.STORE_NAME)
                             .read_text(encoding="utf-8").splitlines()), 2)

    def test_missing_inbox_cursor_and_lost_receipt_cursor_do_not_advance(self):
        self.write_inbox([
            self.row("cursor", "baseline", source_class="unknown"),
            self.row("message-1", "first synthetic message"),
            self.row("message-2", "second synthetic message"),
        ])
        first = self.wait_after("cursor")
        self.assertEqual(first.status, "message")
        self.assertEqual(self.store.bootstrap_consumer(
            "consumer-a", "epoch-1", "cursor", approved=True).status,
            "recorded")
        self.assertEqual(self.store.observe("consumer-a", first.message,
                                           expected_cursor="cursor",
                                           expected_epoch="epoch-1").status, "recorded")

        # Inbox cursor loss fails before a receipt can be created.
        missing = self.wait_after("lost-cursor")
        self.assertEqual(missing.status, "cursor_unavailable")
        self.assertEqual(missing.message, None)

        # A caller that lost its durable receipt cursor and supplies None is
        # rejected because the store already records message-1.
        second = wait.wait_for_message(
            self.inbox.read_snapshot, recipient_values=["@fixture-worker"],
            after_id="message-1", timeout=0, poll_interval=0.1)
        self.assertEqual(second.status, "message")
        lost = self.store.observe("consumer-a", second.message, expected_cursor=None,
                                  expected_epoch="epoch-1")
        self.assertEqual(lost.status, "cursor_unavailable")
        self.assertIsNone(lost.cursor)
        self.assertEqual(len((self.root / receipt_store_module.STORE_NAME)
                             .read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
