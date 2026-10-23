import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI_COPY_FIXTURES = ROOT / "tests" / "fixtures" / "cli-copies"
RESTORE_CLI_COPIES = (
    CLI_COPY_FIXTURES / "restore-check.fixture-a" / "yuva" / "bin" / "yuva",
    CLI_COPY_FIXTURES / "restore-check.fixture-b" / "yuva" / "bin" / "yuva",
)
SPEC = importlib.util.spec_from_file_location(
    "yuva_backup_verify_restore_cli_guard", ROOT / "backup_verify.py",
    loader=SourceFileLoader("yuva_backup_verify_restore_cli_guard",
                            str(ROOT / "backup_verify.py")))
backup_verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_verify)
GUARD_SPEC = importlib.util.spec_from_file_location(
    "yuva_restore_check_cli_guard_patch",
    ROOT / "prototypes" / "restore_check_cli_guard" / "patch.py")
guard_patch = importlib.util.module_from_spec(GUARD_SPEC)
GUARD_SPEC.loader.exec_module(guard_patch)


class RestoreCheckCliWriteGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-restore-cli-guard-")
        self.root = Path(self.temp.name)
        self.backup_root = self.root / "backup-fixture"
        self.backup_root.mkdir(mode=0o700)
        self.active_root = self.root / "active-fixture"
        self.active_root.mkdir(mode=0o700)
        self.scratch_root = self.root / "restore-scratch"
        self.scratch_root.mkdir(mode=0o700)
        self.archive = self.backup_root / "synthetic.tar"

    def tearDown(self):
        self.temp.cleanup()

    def make_archive(self, cli_source: Path, task_bytes: bytes):
        with tarfile.open(self.archive, "w:") as archive:
            for name, mode, content in (
                ("yuva", 0o700, None),
                ("yuva/bin", 0o700, None),
                ("yuva/bin/yuva", 0o775, cli_source.read_bytes()),
                ("yuva/gorevler.json", 0o600, task_bytes),
            ):
                info = tarfile.TarInfo(name)
                info.mode = mode
                if content is None:
                    info.type = tarfile.DIRTYPE
                    info.size = 0
                    archive.addfile(info)
                else:
                    import io
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
        self.archive.chmod(0o600)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        Path(str(self.archive) + ".sha256").write_text(
            f"{digest}  {self.archive}\n", encoding="ascii")
        Path(str(self.archive) + ".sha256").chmod(0o600)
        Path(str(self.archive) + ".list").write_text(
            "synthetic restore-check listing\n", encoding="utf-8")
        Path(str(self.archive) + ".list").chmod(0o600)

    @staticmethod
    def task_bytes(kind):
        if kind == "corrupt":
            return b'{"schema_version":'
        if kind == "unknown":
            return b'{"schema_version":99,"siradaki":1,"gorevler":[]}'
        return b'{"schema_version":1,"siradaki":1,"gorevler":[]}'

    def restore_fixture(self, source, kind, name):
        self.make_archive(source, self.task_bytes(kind))
        try:
            result = backup_verify.restore_check(
                self.archive, scratch_root=self.scratch_root,
                destination_name=name, active_data_root=self.active_root)
        except (json.JSONDecodeError, backup_verify.BackupError) as error:
            result = error
        restored = self.scratch_root / name / "yuva"
        return result, restored

    def invoke_restored_cli(self, cli_path, data_root):
        env = dict(os.environ)
        env["YUVA_DIR"] = str(data_root)
        env["HOME"] = str(data_root.parent)
        return subprocess.run(
            [sys.executable, str(cli_path), "gorev", "ekle", "fixture task",
             "--from", "fixture-agent"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=10)

    def test_both_legacy_restore_copies_are_disabled_in_scratch_for_all_ledger_schemas(self):
        before = {path.relative_to(ROOT).as_posix():
                  hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in RESTORE_CLI_COPIES}
        for source_index, source in enumerate(RESTORE_CLI_COPIES):
            self.assertTrue(source.is_file(), source.relative_to(ROOT))
            for kind in ("corrupt", "v1", "unknown"):
                name = f"legacy-{source_index}-{kind}"
                with self.subTest(source=source.name, ledger=kind):
                    result, restored = self.restore_fixture(source, kind, name)
                    if kind == "v1":
                        self.assertTrue(result["ok"])
                        self.assertEqual(result["restore_cli_policy"],
                                         "task_mutations_disabled")
                    elif kind == "corrupt":
                        self.assertIsInstance(result, json.JSONDecodeError)
                    else:
                        self.assertIsInstance(result, backup_verify.BackupError)

                    task_ledger = restored / "gorevler.json"
                    original_ledger = task_ledger.read_bytes()
                    cli = restored / "bin" / "yuva"
                    self.assertEqual(cli.read_bytes(),
                                     backup_verify.RESTORE_CHECK_CLI_STUB)
                    self.assertEqual(stat.S_IMODE(cli.stat().st_mode), 0o500)
                    completed = self.invoke_restored_cli(cli, restored)
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn(b"inspection-only", completed.stderr)
                    self.assertEqual(task_ledger.read_bytes(), original_ledger)
                    self.assertFalse((restored / "durum.json").exists())
        after = {path.relative_to(ROOT).as_posix():
                 hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in RESTORE_CLI_COPIES}
        self.assertEqual(after, before)

    def test_path_guard_patch_blocks_both_historical_copy_paths_in_temporary_mirrors(self):
        source_hashes = {path.relative_to(ROOT).as_posix():
                         hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in RESTORE_CLI_COPIES}
        cases = {
            "corrupt": b'{"schema_version":',
            "v1": (b'{"schema_version":1,"siradaki":2,"gorevler":[]}'
                   b'\n'),
            "unknown": b'{"schema_version":99,"siradaki":2,"gorevler":[]}\n',
        }
        for source_index, source in enumerate(RESTORE_CLI_COPIES):
            for schema_name, ledger_bytes in cases.items():
                with self.subTest(source=source.name, schema=schema_name):
                    mirrored_cli = (self.root / source.parent.parent.parent.name
                                    / "yuva" / "bin" / "yuva")
                    mirrored_cli.parent.mkdir(parents=True, mode=0o700,
                                              exist_ok=True)
                    mirrored_cli.write_bytes(
                        guard_patch.guarded_source(source.read_bytes()))
                    mirrored_cli.chmod(0o700)
                    data_root = self.root / f"data-{source_index}-{schema_name}"
                    data_root.mkdir(mode=0o700)
                    ledger = data_root / "gorevler.json"
                    ledger.write_bytes(ledger_bytes)
                    before = {path.name: path.read_bytes()
                              for path in data_root.iterdir()}
                    env = dict(os.environ)
                    env["YUVA_DIR"] = str(data_root)
                    env["HOME"] = str(data_root.parent)
                    completed = subprocess.run(
                        [sys.executable, str(mirrored_cli), "gorev", "ekle",
                         "fixture task", "--from", "fixture-agent"],
                        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        check=False, timeout=10)
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn(b"restore-check CLI is inspection-only",
                                  completed.stderr)
                    after = {path.name: path.read_bytes()
                             for path in data_root.iterdir()}
                    self.assertEqual(after, before)
                    self.assertEqual({path.name for path in data_root.iterdir()},
                                     {"gorevler.json"})
        self.assertEqual({path.relative_to(ROOT).as_posix():
                          hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in RESTORE_CLI_COPIES}, source_hashes)

    def test_canonical_writer_keeps_v1_and_rejects_corrupt_or_unknown_schema(self):
        source = ROOT / "bin" / "yuva"
        for kind in ("v1", "corrupt", "unknown"):
            with self.subTest(ledger=kind), tempfile.TemporaryDirectory(
                    prefix="yuva-canonical-writer-") as temporary:
                root = Path(temporary)
                root.chmod(0o700)
                data_root = root / "data"
                data_root.mkdir(mode=0o700)
                cli_dir = root / "bin"
                cli_dir.mkdir(mode=0o700)
                cli = cli_dir / "yuva"
                shutil.copyfile(source, cli)
                shutil.copyfile(ROOT / "yuva_screen_redaction.py",
                                root / "yuva_screen_redaction.py")
                state = {
                    "schema_version": 1,
                    "kullanicilar": {"fixture-agent": {"rol": "isci"}},
                    "rev": 1,
                }
                (data_root / "durum.json").write_text(
                    json.dumps(state), encoding="utf-8")
                task_path = data_root / "gorevler.json"
                if kind == "corrupt":
                    task_path.write_bytes(b"{invalid")
                elif kind == "unknown":
                    task_path.write_text(
                        '{"schema_version":99,"siradaki":2,"gorevler":[]}',
                        encoding="utf-8")
                else:
                    task_path.write_text(json.dumps({
                        "schema_version": 1, "siradaki": 2,
                        "gorevler": [{"id": 1, "baslik": "fixture task",
                                      "kimden": "fixture-owner",
                                      "assignee": None,
                                      "durum": "pending", "gecmis": []}],
                    }), encoding="utf-8")
                before = task_path.read_bytes()
                env = dict(os.environ)
                env["YUVA_DIR"] = str(data_root)
                env["HOME"] = str(root)
                completed = subprocess.run(
                    [sys.executable, str(cli), "gorev", "al", "1",
                     "--from", "fixture-agent"],
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False, timeout=10)
                if kind == "v1":
                    self.assertEqual(completed.returncode, 0,
                                     completed.stderr.decode("utf-8", errors="replace"))
                    result = json.loads(task_path.read_text(encoding="utf-8"))
                    self.assertEqual(result["schema_version"], 1)
                    self.assertEqual(result["gorevler"][0]["assignee"],
                                     "fixture-agent")
                    self.assertNotEqual(task_path.read_bytes(), before)
                else:
                    self.assertEqual(completed.returncode, 2)
                    self.assertEqual(task_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
