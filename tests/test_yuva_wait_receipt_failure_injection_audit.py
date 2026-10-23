"""Independent #724 failure-injection audit of the #714 temp fixture store."""

from concurrent.futures import ThreadPoolExecutor
import fcntl
import importlib.util
import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


store_module = load_module(
    "yuva_wait_receipt_failure_audit_store",
    ROOT / "prototypes" / "yuva-wait" / "receipt_store.py")


class ReceiptStoreFailureInjectionAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-wait-fault-audit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "fixture"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        marker = self.root / store_module.MARKER_NAME
        marker.write_bytes(store_module.MARKER_CONTENT)
        marker.chmod(0o600)
        self.store = store_module.FixtureReceiptStore(self.root)

    def envelope(self, message_id, body="SYNTHETIC_BODY_MUST_NOT_PERSIST"):
        return {
            "message_id": message_id,
            "source_class_claim": "unknown",
            "source_class_trust": "unverified",
            "source_trust": "unverified",
            "content_class": "data_only",
            "text": body,
        }

    def bootstrap(self, consumer="consumer-a", cursor="cursor-0", epoch="epoch-1"):
        result = self.store.bootstrap_consumer(
            consumer, epoch, cursor, approved=True)
        self.assertEqual(result.status, "recorded")
        return result

    def receipt_path(self):
        return self.root / store_module.STORE_NAME

    def test_malformed_tail_and_duplicate_message_id_are_preserved_and_rejected(self):
        self.bootstrap()
        first = self.store.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(first.status, "recorded")
        path = self.receipt_path()
        valid = path.read_bytes()

        # A byte-truncated final record cannot be repaired or followed by append.
        partial = valid + b'{"partial":'
        path.write_bytes(partial)
        path.chmod(0o600)
        self.assertEqual(self.store.cursor("consumer-a").status, "store_corrupt")
        self.assertEqual(self.store.observe(
            "consumer-a", self.envelope("message-2"),
            expected_cursor="message-1", expected_epoch="epoch-1").status,
            "store_corrupt")
        self.assertEqual(path.read_bytes(), partial)

        # A structurally valid second event with a reused ID also corrupts the
        # chain and remains byte-for-byte untouched by the reader.
        events = [json.loads(line) for line in valid.splitlines()]
        duplicate = dict(events[-1])
        duplicate.update(sequence=3, previous_cursor="message-1")
        duplicate_bytes = valid + (
            json.dumps(duplicate, sort_keys=True, separators=(",", ":"))
            + "\n").encode()
        path.write_bytes(duplicate_bytes)
        path.chmod(0o600)
        self.assertEqual(self.store.cursor("consumer-a").status, "store_corrupt")
        self.assertEqual(path.read_bytes(), duplicate_bytes)

    def test_partial_append_is_commit_unknown_then_corrupt_no_retry(self):
        self.bootstrap()
        path = self.receipt_path()
        before = path.read_bytes()
        real_write = store_module.os.write
        calls = 0

        def partial_then_fail(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, bytes(data[:12]))
            raise OSError("synthetic append failure after a partial write")

        with mock.patch.object(store_module.os, "write", side_effect=partial_then_fail):
            result = self.store.observe(
                "consumer-a", self.envelope("message-1"),
                expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(result.status, "commit_unknown")
        after_unknown = path.read_bytes()
        self.assertTrue(after_unknown.startswith(before))
        self.assertNotIn(b"SYNTHETIC_BODY_MUST_NOT_PERSIST", after_unknown)
        self.assertEqual(self.store.cursor("consumer-a").status, "store_corrupt")
        second = self.store.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(second.status, "store_corrupt")
        self.assertEqual(path.read_bytes(), after_unknown)

    def test_file_fsync_uncertainty_readback_dedupes_without_second_append(self):
        self.bootstrap()
        path = self.receipt_path()
        before_lines = len(path.read_bytes().splitlines())
        with mock.patch.object(store_module.os, "fsync",
                               side_effect=OSError("synthetic receipt fsync error")):
            result = self.store.observe(
                "consumer-a", self.envelope("message-1"),
                expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(result.status, "commit_unknown")
        exact_receipt_bytes = path.read_bytes()

        restarted = store_module.FixtureReceiptStore(self.root)
        reconciled = restarted.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(reconciled.status, "duplicate_observation")
        self.assertEqual(path.read_bytes(), exact_receipt_bytes)
        self.assertEqual(len(exact_receipt_bytes.splitlines()), before_lines + 1)
        self.assertNotIn(b"SYNTHETIC_BODY_MUST_NOT_PERSIST", exact_receipt_bytes)

    def test_directory_fsync_uncertainty_bootstrap_readback_is_idempotent(self):
        real_fsync = store_module.os.fsync
        calls = 0

        def file_sync_then_directory_failure(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("synthetic fixture-root directory fsync error")
            return real_fsync(fd)

        with mock.patch.object(store_module.os, "fsync",
                               side_effect=file_sync_then_directory_failure):
            result = self.store.bootstrap_consumer(
                "consumer-a", "epoch-1", "cursor-0", approved=True)
        self.assertEqual(result.status, "commit_unknown")
        path = self.receipt_path()
        before = path.read_bytes()
        self.assertEqual(self.store.cursor("consumer-a").cursor, "cursor-0")
        self.assertEqual(self.store.bootstrap_consumer(
            "consumer-a", "epoch-1", "cursor-0", approved=True).status,
            "duplicate_bootstrap")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(before.splitlines()), 1)

    def test_same_message_id_with_changed_expected_cursor_returns_store_conflict(self):
        self.bootstrap()
        first = self.store.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(first.status, "recorded")

        exact_replay = self.store.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(exact_replay.status, "duplicate_observation")
        ledger_before_mismatch = self.receipt_path().read_bytes()

        changed_cursor = self.store.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor="stale-or-forged-cursor", expected_epoch="epoch-1")
        self.assertEqual(changed_cursor.status, "store_conflict")
        self.assertEqual(changed_cursor.cursor, "message-1")
        self.assertEqual(self.receipt_path().read_bytes(), ledger_before_mismatch)
        restarted = store_module.FixtureReceiptStore(self.root)
        self.assertEqual(restarted.cursor("consumer-a").cursor, "message-1")
        self.assertEqual(len(ledger_before_mismatch.splitlines()), 2)

    def test_restored_old_store_conflicts_for_new_and_duplicate_ids_without_write(self):
        self.bootstrap()
        self.store.observe("consumer-a", self.envelope("message-1"),
                           expected_cursor="cursor-0", expected_epoch="epoch-1")
        snapshot_after_first = self.receipt_path().read_bytes()
        self.store.observe("consumer-a", self.envelope("message-2"),
                           expected_cursor="message-1", expected_epoch="epoch-1")
        surviving_current_cursor = "message-2"

        # Restore a valid, internally consistent older snapshot while the
        # caller still has the later cursor outside the store.
        self.receipt_path().write_bytes(snapshot_after_first)
        self.receipt_path().chmod(0o600)
        new_after_restore = self.store.observe(
            "consumer-a", self.envelope("message-3"),
            expected_cursor=surviving_current_cursor, expected_epoch="epoch-1")
        self.assertEqual(new_after_restore.status, "cursor_conflict")
        self.assertEqual(new_after_restore.cursor, "message-1")

        # But the old-ID dedupe shortcut returns success and the regressed
        # cursor before it checks that surviving caller cursor.
        old_id_after_restore = self.store.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor=surviving_current_cursor, expected_epoch="epoch-1")
        self.assertEqual(old_id_after_restore.status, "store_conflict")
        self.assertEqual(old_id_after_restore.cursor, "message-1")
        self.assertEqual(self.receipt_path().read_bytes(), snapshot_after_first)

    def test_two_consumers_racing_on_same_message_each_gets_one_receipt(self):
        self.bootstrap("consumer-a")
        self.bootstrap("consumer-b")
        stores = [store_module.FixtureReceiptStore(self.root) for _ in range(2)]
        barrier = threading.Barrier(2)

        def observe(store, consumer):
            barrier.wait(timeout=5)
            return store.observe(
                consumer, self.envelope("shared-message"),
                expected_cursor="cursor-0", expected_epoch="epoch-1")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [
                pool.submit(observe, stores[0], "consumer-a"),
                pool.submit(observe, stores[1], "consumer-b"),
            ]
            outcomes = [future.result(timeout=10) for future in results]

        self.assertEqual([item.status for item in outcomes], ["recorded", "recorded"])
        self.assertEqual(self.store.cursor("consumer-a").cursor, "shared-message")
        self.assertEqual(self.store.cursor("consumer-b").cursor, "shared-message")
        events = [json.loads(line) for line in self.receipt_path().read_text().splitlines()]
        receipts = [event for event in events if event["event_type"] == "read_observed"]
        self.assertEqual({event["consumer_id"] for event in receipts},
                         {"consumer-a", "consumer-b"})
        self.assertEqual(len(receipts), 2)

    def test_lock_path_revalidation_oserror_closes_descriptor_and_allows_next_claim(self):
        lock_path = self.root / store_module.LOCK_NAME
        real_stat = store_module.os.stat

        def lock_descriptor_count():
            count = 0
            for entry in Path("/proc/self/fd").iterdir():
                try:
                    count += os.readlink(entry) == os.fspath(lock_path)
                except OSError:
                    continue
            return count

        descriptors_before = lock_descriptor_count()

        def fail_lock_revalidation(path, *args, **kwargs):
            if os.fspath(path) == os.fspath(lock_path):
                raise OSError("synthetic lock-path replacement/read error")
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(store_module.os, "stat",
                               side_effect=fail_lock_revalidation):
            with self.assertRaises(ValueError):
                self.store.cursor("consumer-a")

        self.assertEqual(lock_descriptor_count(), descriptors_before,
                         "revalidation failure leaked a lock descriptor")

        probe_fd = os.open(lock_path, os.O_RDWR)
        try:
            fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
        finally:
            os.close(probe_fd)
        second_claim = self.store.bootstrap_consumer(
            "consumer-a", "epoch-1", "cursor-0", approved=True)
        self.assertEqual(second_claim.status, "recorded")
        self.assertEqual(self.store.cursor("consumer-a").status, "ok")

    def test_receipt_close_error_is_commit_unknown_without_fd_leak_or_retry(self):
        self.bootstrap()
        receipt_path = self.receipt_path()
        real_close = store_module.os.close
        real_fsync = store_module.os.fsync
        injected = False
        after_fsync = False
        receipt_fd = None

        def track_fsync(fd):
            nonlocal after_fsync
            result = real_fsync(fd)
            after_fsync = True
            return result

        def fail_receipt_close_once(fd):
            nonlocal injected, receipt_fd
            try:
                target = os.readlink(f"/proc/self/fd/{fd}")
            except OSError:
                target = ""
            if (after_fsync and not injected
                    and target == os.fspath(receipt_path)):
                injected = True
                receipt_fd = fd
                # Model a close error reported after the kernel has released
                # the descriptor; retrying this number would be unsafe.
                real_close(fd)
                raise OSError("synthetic receipt fd close failure")
            return real_close(fd)

        with mock.patch.object(store_module.os, "fsync", side_effect=track_fsync), \
                mock.patch.object(store_module.os, "close",
                                  side_effect=fail_receipt_close_once):
            result = self.store.observe(
                "consumer-a", self.envelope("message-1"),
                expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertTrue(injected)
        self.assertEqual(result.status, "commit_unknown")
        self.assertIsNotNone(receipt_fd)
        with self.assertRaises(OSError):
            os.fstat(receipt_fd)
        self.assertEqual(len(receipt_path.read_bytes().splitlines()), 2)
        self.assertNotIn(b"SYNTHETIC_BODY_MUST_NOT_PERSIST",
                         receipt_path.read_bytes())

        leaked = []
        for entry in Path("/proc/self/fd").iterdir():
            try:
                if os.readlink(entry) == os.fspath(receipt_path):
                    leaked.append(int(entry.name))
            except OSError:
                continue
        self.assertFalse(leaked)
        self.assertEqual(self.store.cursor("consumer-a").cursor, "message-1")
        committed_bytes = receipt_path.read_bytes()
        replay = self.store.observe(
            "consumer-a", self.envelope("message-1"),
            expected_cursor="cursor-0", expected_epoch="epoch-1")
        self.assertEqual(replay.status, "duplicate_observation")
        self.assertEqual(receipt_path.read_bytes(), committed_bytes)


if __name__ == "__main__":
    unittest.main()
