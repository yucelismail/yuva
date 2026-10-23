import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "yuva"
STORE_MODULE_PATH = ROOT / "panel" / "auth_store_v2.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_auth_init_store_test", STORE_MODULE_PATH,
    loader=SourceFileLoader("yuva_auth_init_store_test", str(STORE_MODULE_PATH)))
store_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = store_module
SPEC.loader.exec_module(store_module)


class AuthInitCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-auth-init-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.data_root = self.base / "yuva-data"
        self.data_root.mkdir(mode=0o700)
        self.env = os.environ.copy()
        self.env["YUVA_DIR"] = str(self.data_root)
        self.env["YUVA_AUTH_ENABLED"] = "0"

    def make_store_root(self, name="auth-root"):
        root = self.base / name
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        return root

    def run_init(self, root, *, instance="yuva-test", audience="yuva-test-api"):
        return subprocess.run(
            [sys.executable, str(CLI), "auth", "init", "--store-root", str(root),
             "--instance-id", instance, "--audience", audience],
            env=self.env, capture_output=True, text=True, timeout=10)

    def test_init_creates_empty_v2_state_and_stable_private_lock(self):
        root = self.make_store_root()

        result = self.run_init(root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("anahtar/enrollment oluşturulmadı", result.stdout)
        self.assertIn("YUVA_AUTH_ENABLED değiştirilmedi", result.stdout)
        state_path = root / store_module.STORE_NAME
        lock_path = root / store_module.LOCK_NAME
        self.assertEqual(os.stat(root).st_uid, os.geteuid())
        self.assertEqual(os.stat(root).st_mode & 0o777, 0o700)
        for path in (state_path, lock_path):
            self.assertEqual(os.stat(path).st_uid, os.geteuid())
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(path).st_nlink, 1)
        self.assertEqual(lock_path.stat().st_size, 0)
        state = store_module.AuthStateStore(root).read()
        self.assertEqual(state["version"], 2)
        self.assertEqual(state["instance_id"], "yuva-test")
        self.assertEqual(state["audience"], "yuva-test-api")
        self.assertEqual(state["generation"], 1)
        self.assertEqual(state["keys"], {})
        self.assertEqual(state["enrollments"], {})
        self.assertEqual(state["nonces"], {})
        self.assertEqual(state["rate_limits"], {})
        self.assertEqual({path.name for path in root.iterdir()},
                         {store_module.STORE_NAME, store_module.LOCK_NAME})

    def test_repeated_init_refuses_to_replace_existing_state_or_lock(self):
        root = self.make_store_root()
        first = self.run_init(root)
        self.assertEqual(first.returncode, 0, first.stderr)
        state_path = root / store_module.STORE_NAME
        lock_path = root / store_module.LOCK_NAME
        state_before = state_path.read_bytes()
        lock_before = (os.stat(lock_path).st_dev, os.stat(lock_path).st_ino,
                       lock_path.read_bytes())

        second = self.run_init(root, audience="different-audience")

        self.assertNotEqual(second.returncode, 0)
        self.assertIn("store_already_exists", second.stderr)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual((os.stat(lock_path).st_dev, os.stat(lock_path).st_ino,
                          lock_path.read_bytes()), lock_before)

    def test_state_symlink_is_never_followed_or_replaced(self):
        root = self.make_store_root()
        target = self.base / "outside-state"
        target.write_bytes(b"preserve-target")
        (root / store_module.STORE_NAME).symlink_to(target)

        result = self.run_init(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("store_already_exists", result.stderr)
        self.assertTrue((root / store_module.STORE_NAME).is_symlink())
        self.assertFalse((root / store_module.LOCK_NAME).exists())
        self.assertEqual(target.read_bytes(), b"preserve-target")

    def test_preexisting_state_bytes_are_preserved_without_creating_lock(self):
        root = self.make_store_root()
        state_path = root / store_module.STORE_NAME
        state_path.write_bytes(b"existing-state")
        state_path.chmod(0o600)

        result = self.run_init(root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("store_already_exists", result.stderr)
        self.assertEqual(state_path.read_bytes(), b"existing-state")
        self.assertFalse((root / store_module.LOCK_NAME).exists())

    def test_symlink_root_or_lock_and_unsafe_root_mode_fail_closed(self):
        actual_root = self.make_store_root("actual-root")
        linked_root = self.base / "linked-root"
        linked_root.symlink_to(actual_root, target_is_directory=True)
        result = self.run_init(linked_root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(actual_root.iterdir()), [])

        lock_root = self.make_store_root("lock-root")
        lock_target = self.base / "outside-lock"
        lock_target.write_bytes(b"do-not-touch")
        (lock_root / store_module.LOCK_NAME).symlink_to(lock_target)
        result = self.run_init(lock_root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lock_unavailable", result.stderr)
        self.assertFalse((lock_root / store_module.STORE_NAME).exists())
        self.assertEqual(lock_target.read_bytes(), b"do-not-touch")

        unsafe_root = self.make_store_root("unsafe-root")
        unsafe_root.chmod(0o750)
        result = self.run_init(unsafe_root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(unsafe_root.iterdir()), [])

    def test_invalid_identity_or_audience_creates_no_lock_or_store(self):
        for name, instance, audience in (
                ("bad-instance", "bad/id", "api"),
                ("bad-audience", "instance", "bad audience")):
            with self.subTest(name=name):
                root = self.make_store_root(name)
                result = self.run_init(root, instance=instance, audience=audience)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid_initial_state", result.stderr)
                self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
