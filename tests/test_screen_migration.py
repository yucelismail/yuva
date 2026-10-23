import fcntl
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATOR_PATH = REPO_ROOT / "prototypes" / "screen-migration" / "migrate_fixture.py"


def load_migrator():
    spec = importlib.util.spec_from_file_location(
        "yuva_screen_migration_test",
        MIGRATOR_PATH,
        loader=SourceFileLoader("yuva_screen_migration_test", str(MIGRATOR_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScreenMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="screen-migration-test-")
        self.root = Path(self.temp.name) / "fixture"
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        (self.root / ".yuva-screen-migration-fixture").write_bytes(
            b"yuva-screen-migration-fixture-v1\n")
        (self.root / ".yuva-screen-migration-fixture").chmod(0o600)
        self.screen_dir = self.root / "ekran"
        self.screen_dir.mkdir(mode=0o700)
        self.screen_dir.chmod(0o700)
        self.migrator = load_migrator()

    def tearDown(self):
        self.temp.cleanup()

    def _record(self, line):
        return {
            "ts": "2026-10-23T12:00:00+03:00",
            "kimlik": "fixture-agent",
            "ad": "Fixture Agent",
            "tur": "ekran",
            "satir": line,
        }

    def test_redacts_atomically_preserving_rows_owner_mode_and_timestamps(self):
        path = self.screen_dir / "fixture-agent.jsonl"
        synthetic = "Bearer SYNTHETIC_MIGRATION_TOKEN_123456789"
        records = [self._record("normal status " + synthetic),
                   self._record("benign second row")]
        path.write_bytes(b"".join(
            (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
            for row in records))
        path.chmod(0o600)
        backup_copy = self.root / "synthetic-backup.jsonl"
        backup_bytes = (json.dumps(self._record("Bearer SYNTHETIC_BACKUP_TOKEN_123456789"))
                        + "\n").encode("utf-8")
        backup_copy.write_bytes(backup_bytes)
        backup_copy.chmod(0o600)
        old_atime = 1_700_000_000_123_456_789
        old_mtime = 1_700_000_100_987_654_321
        os.utime(path, ns=(old_atime, old_mtime))
        xattr_name = "user.yuva_fixture_metadata"
        xattr_value = b"synthetic-metadata-only"
        try:
            os.setxattr(path, xattr_name, xattr_value)
        except OSError:
            xattr_name = None
        before = path.stat()

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = self.migrator.main([
                "--fixture-root", str(self.root), "--file", path.name])
        self.assertEqual(exit_code, 0)
        self.assertFalse(synthetic in stdout.getvalue())
        self.assertFalse(str(path) in stdout.getvalue())
        result = json.loads(stdout.getvalue())

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["redacted_fields"], 1)
        self.assertEqual(result["file_id"], f"{before.st_dev:x}:{before.st_ino:x}")
        after = path.stat()
        self.assertEqual(stat.S_IMODE(after.st_mode), stat.S_IMODE(before.st_mode))
        self.assertEqual((after.st_uid, after.st_gid), (before.st_uid, before.st_gid))
        self.assertEqual((after.st_atime_ns, after.st_mtime_ns), (old_atime, old_mtime))
        if xattr_name is not None:
            self.assertEqual(os.getxattr(path, xattr_name), xattr_value)
        rewritten = path.read_bytes()
        self.assertEqual(rewritten.count(b"\n"), 2)
        self.assertFalse(synthetic.encode("utf-8") in rewritten)
        self.assertEqual(backup_copy.read_bytes(), backup_bytes)
        self.assertFalse(list(self.root.glob("*.backup")))
        rows = [json.loads(line) for line in rewritten.splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertIn("normal status ", rows[0]["satir"])
        self.assertEqual(rows[1]["satir"], "benign second row")
        self.assertIn("[REDACTED:credential]", rows[0]["satir"])

        stable_bytes = path.read_bytes()
        stable_stat = path.stat()
        second = self.migrator.migrate_file(self.root, path.name)
        second_stat = path.stat()
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(second["rows"], 2)
        self.assertEqual(second["redacted_fields"], 0)
        self.assertEqual(path.read_bytes(), stable_bytes)
        self.assertEqual((second_stat.st_dev, second_stat.st_ino),
                         (stable_stat.st_dev, stable_stat.st_ino))
        self.assertEqual(second_stat.st_mtime_ns, stable_stat.st_mtime_ns)

    def test_malformed_input_fails_closed_without_replacing_source(self):
        path = self.screen_dir / "broken.jsonl"
        original = b'{"ts":"bad","satir":"SYNTHETIC_MUST_NOT_PRINT"}\n'
        path.write_bytes(original)
        path.chmod(0o600)
        before = path.stat()
        with self.assertRaises(self.migrator.MigrationError) as raised:
            self.migrator.migrate_file(self.root, path.name)
        self.assertEqual(raised.exception.code, "record_rejected")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual((path.stat().st_dev, path.stat().st_ino),
                         (before.st_dev, before.st_ino))
        self.assertEqual(list(self.screen_dir.glob(".screen-migrate-*.tmp")), [])
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = self.migrator.main([
                "--fixture-root", str(self.root), "--file", path.name])
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "status": "error", "code": "record_rejected"})
        self.assertFalse("SYNTHETIC_MUST_NOT_PRINT" in stdout.getvalue())

    def test_replace_failure_leaves_original_and_cleans_temp(self):
        path = self.screen_dir / "replace.jsonl"
        path.write_bytes((json.dumps(self._record(
            "token=synthetic-migration-value")) + "\n").encode())
        path.chmod(0o600)
        original = path.read_bytes()
        before = path.stat()
        with patch.object(self.migrator.os, "replace", side_effect=OSError):
            with self.assertRaises(self.migrator.MigrationError) as raised:
                self.migrator.migrate_file(self.root, path.name)
        self.assertEqual(raised.exception.code, "replace_failed")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual((path.stat().st_dev, path.stat().st_ino),
                         (before.st_dev, before.st_ino))
        self.assertEqual(list(self.screen_dir.glob(".screen-migrate-*.tmp")), [])

    def test_directory_fsync_failure_reports_unknown_without_retry(self):
        path = self.screen_dir / "commit-unknown.jsonl"
        synthetic = "api_key=SYNTHETIC_UNKNOWN_FIXTURE_123456789"
        path.write_bytes((json.dumps(self._record(synthetic)) + "\n").encode())
        path.chmod(0o600)
        real_fsync = os.fsync
        calls = 0

        def fail_directory_fsync(fd):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("synthetic directory fsync failure")
            return real_fsync(fd)

        with patch.object(self.migrator.os, "fsync", side_effect=fail_directory_fsync):
            with self.assertRaises(self.migrator.MigrationError) as raised:
                self.migrator.migrate_file(self.root, path.name)
        self.assertEqual(raised.exception.code, "commit_unknown")
        rewritten = path.read_bytes()
        self.assertFalse(synthetic.encode("utf-8") in rewritten)
        self.assertIn(b"[REDACTED:credential]", rewritten)
        self.assertEqual(list(self.screen_dir.glob(".screen-migrate-*.tmp")), [])

    def test_lock_timeout_refuses_write(self):
        path = self.screen_dir / "locked.jsonl"
        path.write_bytes((json.dumps(self._record(
            "api_key=SYNTHETIC_LOCK_FIXTURE_123456789")) + "\n").encode())
        path.chmod(0o600)
        original = path.read_bytes()
        lock_path = self.root / ".kilit"
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(self.migrator.MigrationError) as raised:
                self.migrator.migrate_file(self.root, path.name, lock_timeout=0)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        self.assertEqual(raised.exception.code, "lock_timeout")
        self.assertEqual(path.read_bytes(), original)

    def test_fixture_guard_rejects_non_temp_root_symlink_and_path_traversal(self):
        outside = self.migrator.migrate_file
        with self.assertRaises(self.migrator.MigrationError) as raised:
            outside(REPO_ROOT, "not-a-live-file.jsonl")
        self.assertEqual(raised.exception.code, "fixture_root_outside_temp")

        link = Path(self.temp.name) / "fixture-link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(self.migrator.MigrationError) as raised:
            outside(link, "fixture-agent.jsonl")
        self.assertEqual(raised.exception.code, "fixture_root_symlink")

        with self.assertRaises(self.migrator.MigrationError) as raised:
            outside(self.root, "../outside.jsonl")
        self.assertEqual(raised.exception.code, "invalid_file_name")

    def test_unknown_pattern_stays_unchanged_without_clean_claim(self):
        path = self.screen_dir / "unknown-pattern.jsonl"
        original = (json.dumps(self._record(
            "opaque_fixture_value=UNRECOGNIZED_SYNTHETIC_CANARY_123"))
            + "\n").encode("utf-8")
        path.write_bytes(original)
        path.chmod(0o600)
        before = path.stat()

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = self.migrator.main([
                "--fixture-root", str(self.root), "--file", path.name])
        result = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["status"], "unchanged")
        self.assertNotIn("clean", stdout.getvalue().lower())
        self.assertEqual(path.read_bytes(), original)
        after = path.stat()
        self.assertEqual((after.st_dev, after.st_ino, after.st_mtime_ns),
                         (before.st_dev, before.st_ino, before.st_mtime_ns))

    def test_reported_real_credential_stops_before_fixture_source_is_opened(self):
        path = self.screen_dir / "reported-exposure.jsonl"
        original = (json.dumps(self._record("synthetic-only fixture marker"))
                    + "\n").encode("utf-8")
        path.write_bytes(original)
        path.chmod(0o600)
        before = path.stat()
        stdout = io.StringIO()
        with patch.object(self.migrator, "_open_fixture",
                          side_effect=AssertionError("source access attempted")) as opened, \
                redirect_stdout(stdout):
            exit_code = self.migrator.main([
                "--fixture-root", str(self.root), "--file", path.name,
                "--credential-exposure-reported"])
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "status": "error", "code": "credential_exposure_requires_rotation"})
        opened.assert_not_called()
        self.assertEqual(path.read_bytes(), original)
        after = path.stat()
        self.assertEqual((after.st_dev, after.st_ino, after.st_mtime_ns),
                         (before.st_dev, before.st_ino, before.st_mtime_ns))
        self.assertEqual(list(self.screen_dir.glob(".screen-migrate-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
