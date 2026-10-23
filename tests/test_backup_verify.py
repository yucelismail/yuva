import contextlib
import hashlib
import importlib.util
import io
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "backup_verify.py"
spec = importlib.util.spec_from_file_location(
    "yuva_backup_verify", TOOL_PATH,
    loader=SourceFileLoader("yuva_backup_verify", str(TOOL_PATH)))
backup_verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_verify)


class BackupVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.active = self.root / "active-yuva"
        self.active.mkdir(mode=0o700)
        self.backup_root = self.root / "backup"
        self.backup_root.mkdir(mode=0o700)
        self.archive = self.backup_root / "yuva-fixture.tar"
        self.contents = self._valid_contents()
        self._make_archive(self.contents)
        self.scratch = self.root / "scratch"
        self.scratch.mkdir(mode=0o700)
        self.scratch.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _valid_contents():
        state = {"kullanicilar": {"worker": {"rol": "isci"}}, "rev": 0}
        tasks = {"siradaki": 2, "gorevler": [{
            "id": 1, "baslik": "fixture task", "kimden": "owner",
            "durum": "pending", "assignee": None, "gecmis": []
        }]}
        return {
            "yuva/durum.json": json.dumps(state).encode(),
            "yuva/gorevler.json": json.dumps(tasks).encode(),
            "yuva/mesaj.jsonl": b'{"kimden":"worker","mesaj":"fixture"}\n',
            "yuva/ekran/worker.jsonl": b'{"tur":"sonuc","satir":"fixture"}\n',
            "yuva/.kilit": b"",
        }

    def _make_archive(self, contents, *, extra_members=()):
        with tarfile.open(self.archive, "w:") as tf:
            root = tarfile.TarInfo("yuva")
            root.type = tarfile.DIRTYPE
            root.mode = 0o700
            root.size = 0
            tf.addfile(root)
            for name, value in contents.items():
                info = tarfile.TarInfo(name)
                info.mode = 0o600 if name.endswith(".jsonl") or name.endswith(".kilit") else 0o644
                info.size = len(value)
                import io
                tf.addfile(info, io.BytesIO(value))
            for member in extra_members:
                tf.addfile(member)
        self.archive.chmod(0o600)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        checksum = Path(str(self.archive) + ".sha256")
        checksum.write_text(f"{digest}  {self.archive}\n", encoding="ascii")
        checksum.chmod(0o600)
        listing = Path(str(self.archive) + ".list")
        listing.write_text("fixture tar member listing\n", encoding="utf-8")
        listing.chmod(0o600)

    def _verify(self, **kwargs):
        return backup_verify.verify_backup(
            self.archive, active_data_root=self.active, **kwargs)

    def test_verify_checks_hash_modes_and_tar_metadata_without_writing(self):
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.backup_root.iterdir()}

        result = self._verify()

        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.backup_root.iterdir()}
        self.assertTrue(result["ok"])
        self.assertEqual(result["archive"]["member_count"], 6)
        self.assertEqual(result["archive"]["top_level"], "yuva")
        self.assertEqual(result["authenticity"],
                         "unverified; adjacent checksum is not an external trust anchor")
        self.assertFalse(result["listing_sidecar"]["compared_to_tar"])
        self.assertEqual(before, after)

    def test_checksum_mismatch_and_weak_archive_mode_fail(self):
        checksum = Path(str(self.archive) + ".sha256")
        checksum.write_text("0" * 64 + f"  {self.archive}\n", encoding="ascii")
        checksum.chmod(0o600)
        result = self._verify()
        self.assertFalse(result["ok"])
        self.assertFalse(result["checksum_sidecar"]["matches_archive"])

        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        checksum.write_text(f"{digest}  {self.archive}\n", encoding="ascii")
        self.archive.chmod(0o644)
        failed_mode = self._verify()
        self.assertFalse(failed_mode["ok"])
        self.assertEqual(failed_mode["archive"]["permission"], "fail")

    def test_expected_digest_pin_detects_archive_and_sidecar_changed_together(self):
        expected = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        matched = self._verify(expected_sha256=expected)
        self.assertTrue(matched["ok"])
        self.assertEqual(matched["expected_sha256"], {
            "provided": True, "matches_archive": True,
            "provenance": "caller_supplied_unverified",
        })
        self.assertEqual(matched["authenticity"],
                         "unverified; adjacent checksum is not an external trust anchor")

        changed = dict(self.contents)
        changed["yuva/durum.json"] = b'{"rev":999,"kullanicilar":{}}'
        self._make_archive(changed)  # Rewrites both archive and adjacent sidecar.
        result = self._verify(expected_sha256=expected)
        self.assertFalse(result["ok"])
        self.assertTrue(result["checksum_sidecar"]["matches_archive"])
        self.assertFalse(result["expected_sha256"]["matches_archive"])
        self.assertEqual(result["authenticity"],
                         "unverified; adjacent checksum is not an external trust anchor")

    def test_expected_digest_must_be_canonical_lowercase_sha256(self):
        for value in ("a" * 63, "A" * 64, "a" * 64 + "\n", "z" * 64):
            with self.subTest(value=value):
                with self.assertRaisesRegex(backup_verify.BackupError,
                                            "64 lowercase hexadecimal"):
                    self._verify(expected_sha256=value)

    def test_restore_check_pin_mismatch_refuses_before_creating_scratch(self):
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = backup_verify.main([
                "restore-check", "--archive", str(self.archive),
                "--scratch-root", str(self.scratch),
                "--destination-name", "pin-mismatch-cli",
                "--active-data-root", str(self.active),
                "--expected-sha256", "0" * 64,
            ])
        self.assertEqual(code, 2)
        self.assertFalse((self.scratch / "pin-mismatch-cli").exists())

        with self.assertRaisesRegex(backup_verify.BackupError,
                                    "verification did not pass"):
            backup_verify.restore_check(
                self.archive, scratch_root=self.scratch,
                destination_name="pin-mismatch", active_data_root=self.active,
                expected_sha256="0" * 64)
        self.assertFalse((self.scratch / "pin-mismatch").exists())

    def test_active_data_root_and_symlink_inputs_are_rejected(self):
        live_archive = self.active / "backup.tar"
        live_archive.write_bytes(self.archive.read_bytes())
        with self.assertRaisesRegex(backup_verify.BackupError, "outside the active"):
            backup_verify.verify_backup(live_archive, active_data_root=self.active)

        alias = self.backup_root / "alias.tar"
        alias.symlink_to(self.archive)
        with self.assertRaisesRegex(backup_verify.BackupError, "regular files"):
            backup_verify.verify_backup(alias, active_data_root=self.active)

    def test_unsafe_tar_member_types_and_paths_fail_closed(self):
        outside = tarfile.TarInfo("../outside")
        outside.size = 0
        self._make_archive(self.contents, extra_members=(outside,))
        with self.assertRaisesRegex(backup_verify.BackupError, "escapes"):
            self._verify()

        link = tarfile.TarInfo("yuva/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        link.size = 0
        self._make_archive(self.contents, extra_members=(link,))
        with self.assertRaisesRegex(backup_verify.BackupError, "symlinks"):
            self._verify()

    def test_restore_check_requires_new_explicit_private_scratch_target(self):
        result = backup_verify.restore_check(
            self.archive, scratch_root=self.scratch,
            destination_name="restore-fixture", active_data_root=self.active)
        restored = self.scratch / "restore-fixture" / "yuva"

        self.assertTrue(result["ok"])
        self.assertEqual(result["schema"]["durum.json"], "pass")
        self.assertEqual(result["schema"]["gorevler.json"], "pass")
        self.assertEqual(result["schema"]["jsonl_files"], 2)
        self.assertEqual((restored / "gorevler.json").read_bytes(),
                         self.contents["yuva/gorevler.json"])
        self.assertFalse(any(self.active.iterdir()))
        self.assertEqual((self.scratch / "restore-fixture").stat().st_mode & 0o777, 0o700)

        with self.assertRaisesRegex(backup_verify.BackupError, "already exists"):
            backup_verify.restore_check(
                self.archive, scratch_root=self.scratch,
                destination_name="restore-fixture", active_data_root=self.active)

    def test_restore_check_rejects_active_root_and_bad_schema(self):
        with self.assertRaisesRegex(backup_verify.BackupError, "outside active"):
            backup_verify.restore_check(
                self.archive, scratch_root=self.active,
                destination_name="restore-fixture", active_data_root=self.active)

        bad_contents = dict(self.contents)
        bad_contents["yuva/gorevler.json"] = b'{"siradaki": true, "gorevler": []}'
        self._make_archive(bad_contents)
        with self.assertRaisesRegex(backup_verify.BackupError, "siradaki"):
            backup_verify.restore_check(
                self.archive, scratch_root=self.scratch,
                destination_name="invalid-schema", active_data_root=self.active)
        self.assertTrue((self.scratch / "invalid-schema").exists())

    def test_restore_check_refuses_unpacked_size_limit_before_creating_destination(self):
        verified = self._verify()
        self.assertTrue(verified["restore_limits"]["within_limits"])
        self.assertGreater(verified["archive"]["member_bytes"], 1)

        with patch.object(backup_verify, "MAX_RESTORE_TOTAL_BYTES", 1):
            with self.assertRaisesRegex(backup_verify.BackupError, "size limits"):
                backup_verify.restore_check(
                    self.archive, scratch_root=self.scratch,
                    destination_name="too-large", active_data_root=self.active)

        self.assertFalse((self.scratch / "too-large").exists())
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_cli_exit_codes_distinguish_verify_from_restore_check(self):
        output = io.StringIO()
        expected = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        with contextlib.redirect_stdout(output):
            code = backup_verify.main([
                "verify", "--archive", str(self.archive),
                "--active-data-root", str(self.active),
                "--expected-sha256", expected,
            ])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result["ok"])
        self.assertTrue(result["expected_sha256"]["matches_archive"])


if __name__ == "__main__":
    unittest.main()
