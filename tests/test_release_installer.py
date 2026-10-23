import hashlib
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import release_manifest
import release_installer


class ReleaseInstallerTests(unittest.TestCase):
    def setUp(self):
        # INSTALL_ROOT validates every ancestor and rejects shared writable
        # parents such as /tmp; keep this disposable fixture under the private
        # runner home while each individual root remains temporary.
        self.temp = tempfile.TemporaryDirectory(
            prefix="yuva-release-installer-", dir=Path.home())
        self.root = Path(self.temp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Fixture"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email",
                        "fixture@example.invalid"], check=True)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "marker").write_text("leave this alone\n", encoding="utf-8")
        (self.data / "durum.json").write_text(json.dumps({
            "schema_version": 1, "kullanicilar": {}, "rev": 0,
        }), encoding="utf-8")
        (self.data / "gorevler.json").write_text(json.dumps({
            "schema_version": 1, "siradaki": 1, "gorevler": [],
        }), encoding="utf-8")
        self.marker_bytes = (self.data / "marker").read_bytes()
        self.install_root = self.root / "install"
        self.v1 = self._make_release("v1")

    def tearDown(self):
        self.temp.cleanup()
        self.assertFalse(self.root.exists(), "fixture temporary directory was not removed")

    def _write_source(self, relative, content, mode=0o644):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(mode)

    def _make_release(self, version, *, data_contract=release_manifest.DATA_CONTRACT):
        self._write_source("bin/yuva", f"#!/usr/bin/env python3\nprint('{version}')\n", 0o755)
        self._write_source("panel/server.py", f"VERSION = '{version}'\n")
        self._write_source("panel/ui.html", f"<title>{version}</title>\n")
        self._write_source("contrib/systemd/yuva-panel.service",
                           "[Service]\nExecStart=/usr/bin/python3 "
                           "%h/.local/opt/yuva/current/panel/server.py\n")
        self._write_source("README.md", f"fixture release {version}\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", version], check=True)
        payload = self.root / f"payload-{version}"
        payload.mkdir()
        for source in self.repo.rglob("*"):
            relative = source.relative_to(self.repo)
            if ".git" in relative.parts:
                continue
            target = payload / relative
            if source.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(os.readlink(source))
            elif source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                target.chmod(source.stat().st_mode & 0o777)
        manifest = release_manifest.create_manifest(self.repo, payload, "fixture://yuva")
        manifest["data_contract"]["schema_compatibility"] = data_contract
        raw = release_manifest._canonical_json(manifest)
        pin = hashlib.sha256(raw).hexdigest()
        return {"payload": payload, "manifest": raw, "pin": pin,
                "release_id": manifest["release_id"], "commit": manifest["source"]["commit"]}

    def _install(self, release):
        return release_installer.install_release(
            install_root=self.install_root, data_root=self.data,
            payload=release["payload"], manifest_bytes=release["manifest"],
            source_repo=self.repo, trusted_manifest_sha256=release["pin"])

    def test_install_stages_and_verifies_release_then_atomically_sets_current(self):
        result = self._install(self.v1)
        current = self.install_root / "current"
        self.assertEqual(os.readlink(current), f"releases/{self.v1['release_id']}")
        release = self.install_root / "releases" / self.v1["release_id"]
        self.assertEqual((release / "bin" / "yuva").read_bytes(),
                         (self.v1["payload"] / "bin" / "yuva").read_bytes())
        self.assertEqual((self.install_root / "manifests" /
                          f"{self.v1['release_id']}.manifest.json").read_bytes(),
                         self.v1["manifest"])
        self.assertTrue(result["source_verified"])
        self.assertEqual(result["current_release_id"], self.v1["release_id"])
        self.assertEqual((self.data / "marker").read_bytes(), self.marker_bytes)
        self.assertEqual(list((self.install_root / "releases").glob(".staging-*")), [])
        self.assertEqual(stat_mode(release), 0o555)

    def test_install_cli_uses_explicit_roots_and_external_manifest_pin(self):
        manifest_path = self.root / "manifest.json"
        manifest_path.write_bytes(self.v1["manifest"])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = release_installer.main([
                "install", "--install-root", str(self.install_root),
                "--data-root", str(self.data), "--payload", str(self.v1["payload"]),
                "--manifest", str(manifest_path), "--source-repo", str(self.repo),
                "--trusted-manifest-sha256", self.v1["pin"],
            ])
        self.assertEqual(code, 0)
        self.assertIn(self.v1["release_id"], output.getvalue())
        self.assertEqual(os.readlink(self.install_root / "current"),
                         f"releases/{self.v1['release_id']}")

    def test_dirty_source_and_bad_pin_do_not_create_install_root(self):
        (self.repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(release_installer.InstallError, "dirty, unpinned"):
            self._install(self.v1)
        self.assertFalse(self.install_root.exists())

        (self.repo / "untracked.txt").unlink()
        with self.assertRaisesRegex(release_installer.InstallError, "dirty, unpinned"):
            release_installer.install_release(
                install_root=self.install_root, data_root=self.data,
                payload=self.v1["payload"], manifest_bytes=self.v1["manifest"],
                source_repo=self.repo, trusted_manifest_sha256="0" * 64)
        self.assertFalse(self.install_root.exists())

    def test_existing_release_id_is_never_overwritten(self):
        self._install(self.v1)
        before = os.readlink(self.install_root / "current")
        with self.assertRaisesRegex(release_installer.InstallError, "never overwritten"):
            self._install(self.v1)
        self.assertEqual(os.readlink(self.install_root / "current"), before)
        self.assertEqual((self.data / "marker").read_bytes(), self.marker_bytes)

    def test_relative_install_root_is_rejected_without_writes(self):
        before_data = tree_digest(self.data)
        old_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with self.assertRaisesRegex(release_installer.InstallError,
                                        "INSTALL_ROOT must be an absolute path"):
                release_installer.install_release(
                    install_root=Path("relative-install"), data_root=self.data,
                    payload=self.v1["payload"], manifest_bytes=self.v1["manifest"],
                    source_repo=self.repo,
                    trusted_manifest_sha256=self.v1["pin"])
            self.assertFalse((self.root / "relative-install").exists())
            self.assertEqual(tree_digest(self.data), before_data)
        finally:
            os.chdir(old_cwd)

    def test_symlink_component_in_install_root_is_rejected_without_writes(self):
        target = self.root / "outside-install-target"
        target.mkdir(mode=0o700)
        sentinel = target / "sentinel.txt"
        sentinel.write_text("outside target remains unchanged\n")
        alias = self.root / "install-alias"
        alias.symlink_to(target, target_is_directory=True)
        before_target = tree_digest(target)
        before_data = tree_digest(self.data)

        with self.assertRaisesRegex(release_installer.InstallError,
                                    "real directories without symlink components"):
            release_installer.install_release(
                install_root=alias / "install", data_root=self.data,
                payload=self.v1["payload"], manifest_bytes=self.v1["manifest"],
                source_repo=self.repo,
                trusted_manifest_sha256=self.v1["pin"])

        self.assertEqual(tree_digest(target), before_target)
        self.assertEqual(tree_digest(self.data), before_data)

    def test_manifest_path_traversal_is_rejected_before_root_writes(self):
        canary = self.root / "outside-manifest-target"
        canary.write_text("outside target remains unchanged\n")
        before_canary = canary.read_bytes()
        before_data = tree_digest(self.data)
        manifest = json.loads(self.v1["manifest"])
        manifest["artifact"]["files"][0]["path"] = "../../outside-manifest-target"
        raw = release_manifest._canonical_json(manifest)

        with self.assertRaisesRegex(release_installer.InstallError,
                                    "release verification failed"):
            release_installer.install_release(
                install_root=self.install_root, data_root=self.data,
                payload=self.v1["payload"], manifest_bytes=raw,
                source_repo=self.repo,
                trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())

        self.assertFalse(self.install_root.exists())
        self.assertEqual(canary.read_bytes(), before_canary)
        self.assertEqual(tree_digest(self.data), before_data)

    def test_escaping_payload_symlink_is_rejected_without_writes(self):
        canary = self.root / "outside-symlink-target"
        canary.write_text("outside target remains unchanged\n")
        before_canary = canary.read_bytes()
        before_data = tree_digest(self.data)
        escape = self.v1["payload"] / "escape"
        escape.symlink_to("../../outside-symlink-target")
        try:
            with self.assertRaisesRegex(release_installer.InstallError,
                                        "release verification failed"):
                self._install(self.v1)
        finally:
            escape.unlink(missing_ok=True)

        self.assertFalse(self.install_root.exists())
        self.assertEqual(canary.read_bytes(), before_canary)
        self.assertEqual(tree_digest(self.data), before_data)

    def test_external_hardlinked_payload_is_copied_without_writing_target(self):
        self._write_hardlink_payload_for_test()
        external = self.root / "external-hardlink-source"
        before_external = external.read_bytes()
        before_data = tree_digest(self.data)

        result = self._install(self.v1)

        installed = (self.install_root / "releases" / result["release_id"]
                     / "README.md")
        release_tree = installed.parent
        manifest_files = json.loads(self.v1["manifest"])["artifact"]["files"]
        allowed_paths = {row["path"] for row in manifest_files}
        copied_paths = {
            path.relative_to(release_tree).as_posix()
            for path in release_tree.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        self.assertEqual(external.read_bytes(), before_external)
        self.assertNotEqual(os.stat(installed).st_ino, os.stat(external).st_ino)
        self.assertEqual(copied_paths, allowed_paths)
        self.assertEqual(tree_digest(self.data), before_data)
        self.assertEqual(os.readlink(self.install_root / "current"),
                         f"releases/{result['release_id']}")

    def _write_hardlink_payload_for_test(self):
        payload_readme = self.v1["payload"] / "README.md"
        payload_readme.unlink()
        external = self.root / "external-hardlink-source"
        external.write_bytes(b"fixture release v1\n")
        external.chmod(0o644)
        os.link(external, payload_readme)

    def test_preexisting_current_file_is_rejected_without_root_changes(self):
        self.install_root.mkdir(mode=0o700)
        current = self.install_root / "current"
        current.write_text("operator-owned conflicting path\n")
        before_root = tree_digest(self.install_root)
        before_data = tree_digest(self.data)

        with self.assertRaisesRegex(release_installer.InstallError,
                                    "current exists but is not a symlink"):
            self._install(self.v1)

        self.assertEqual(tree_digest(self.install_root), before_root)
        self.assertEqual(tree_digest(self.data), before_data)

    def test_preexisting_unsafe_current_symlink_is_rejected_without_root_changes(self):
        self.install_root.mkdir(mode=0o700)
        current = self.install_root / "current"
        current.symlink_to("../../outside-release-target")
        before_root = tree_digest(self.install_root)
        before_data = tree_digest(self.data)

        with self.assertRaisesRegex(release_installer.InstallError,
                                    "current target is not a canonical release path"):
            self._install(self.v1)

        self.assertEqual(tree_digest(self.install_root), before_root)
        self.assertEqual(tree_digest(self.data), before_data)

    def test_preexisting_staging_collision_is_preserved_without_writes(self):
        self._install(self.v1)
        v2 = self._make_release("v2")
        staging_name = "e" * 32
        staging = self.install_root / "releases" / f".staging-{staging_name}"
        staging.mkdir(mode=0o700)
        sentinel = staging / "operator-owned.txt"
        sentinel.write_text("must survive staging name collision\n")
        before_root = tree_digest(self.install_root)
        before_data = tree_digest(self.data)
        fixed_uuid = release_installer.uuid.UUID(staging_name)

        with patch.object(release_installer.uuid, "uuid4", return_value=fixed_uuid):
            with self.assertRaisesRegex(release_installer.InstallError,
                                        "staging path already exists"):
                self._install(v2)

        self.assertEqual(tree_digest(self.install_root), before_root)
        self.assertEqual(tree_digest(self.data), before_data)
        self.assertEqual(sentinel.read_text(), "must survive staging name collision\n")

    def test_preexisting_staging_symlink_collision_is_preserved(self):
        self._install(self.v1)
        v2 = self._make_release("v2")
        staging_name = "9" * 32
        target = self.root / "outside-staging-target"
        target.mkdir(mode=0o700)
        sentinel = target / "operator-owned.txt"
        sentinel.write_text("must not be written or removed\n")
        staging = self.install_root / "releases" / f".staging-{staging_name}"
        staging.symlink_to(target, target_is_directory=True)
        before_root = tree_digest(self.install_root)
        before_target = tree_digest(target)
        before_data = tree_digest(self.data)
        fixed_uuid = release_installer.uuid.UUID(staging_name)

        with patch.object(release_installer.uuid, "uuid4", return_value=fixed_uuid):
            with self.assertRaisesRegex(release_installer.InstallError,
                                        "staging path already exists"):
                self._install(v2)

        self.assertEqual(tree_digest(self.install_root), before_root)
        self.assertEqual(tree_digest(target), before_target)
        self.assertEqual(tree_digest(self.data), before_data)

    def test_atomic_publish_refuses_even_an_empty_existing_release_directory(self):
        source = self.root / "staging"
        destination = self.root / "release"
        source.mkdir()
        destination.mkdir()
        with self.assertRaisesRegex(release_installer.InstallError, "never overwritten"):
            release_installer._rename_noreplace(source, destination)
        self.assertTrue(source.is_dir())
        self.assertTrue(destination.is_dir())

    def test_install_and_rollback_keep_data_root_outside_release_tree(self):
        self._install(self.v1)
        v1_commit = self.v1["commit"]
        v2 = self._make_release("v2")
        self._install(v2)
        self.assertEqual(os.readlink(self.install_root / "current"),
                         f"releases/{v2['release_id']}")
        self.assertEqual(os.readlink(self.install_root / "previous"),
                         f"releases/{self.v1['release_id']}")

        rollback_source = self.root / "rollback-source"
        subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q",
                        "--detach", str(rollback_source), v1_commit], check=True)
        before_data = tree_digest(self.data)
        result = release_installer.rollback_release(
            install_root=self.install_root, data_root=self.data,
            source_repo=rollback_source,
            trusted_manifest_sha256=self.v1["pin"])
        self.assertEqual(os.readlink(self.install_root / "current"),
                         f"releases/{self.v1['release_id']}")
        self.assertEqual(os.readlink(self.install_root / "previous"),
                         f"releases/{v2['release_id']}")
        self.assertTrue(result["source_verified"])
        self.assertEqual(result["data_contract"], release_manifest.DATA_CONTRACT)
        self.assertEqual(result["data_schema"], {
            "durum": "v1", "gorevler": "v1",
            "mesajlar": "absent", "ekranlar": "absent",
        })
        self.assertEqual(tree_digest(self.data), before_data)
        self.assertEqual((self.data / "marker").read_bytes(), self.marker_bytes)
        subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "-f",
                        str(rollback_source)], check=True)

    def _install_rollback_pair(self):
        self._install(self.v1)
        v2 = self._make_release("v2")
        self._install(v2)
        rollback_source = self.root / "rollback-source-v1"
        subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q",
                        "--detach", str(rollback_source), self.v1["commit"]], check=True)
        return v2, rollback_source

    def _remove_rollback_source(self, source):
        subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "-f",
                        str(source)], check=True)

    def test_rollback_accepts_supported_legacy_actual_data_classes_read_only(self):
        _v2, rollback_source = self._install_rollback_pair()
        try:
            (self.data / "durum.json").write_text(json.dumps({
                "kullanicilar": {}, "rev": 3,
            }), encoding="utf-8")
            (self.data / "gorevler.json").write_text(json.dumps({
                "siradaki": 2, "gorevler": [{
                    "id": 1, "baslik": "legacy task", "kimden": "fixture",
                    "durum": "pending", "gecmis": [],
                }],
            }), encoding="utf-8")
            (self.data / "mesaj.jsonl").write_bytes(
                b'{"mesaj":"legacy"}\n'
                b'{"schema_version":1,"mesaj":"v1"}\n'
                b'{"schema_version":2,"mesaj":"v2"}\n')
            screen = self.data / "ekran"
            screen.mkdir(mode=0o700)
            (screen / "fixture.jsonl").write_bytes(b'{"tur":"ekran","satir":"ok"}\n')
            before_data = tree_digest(self.data)

            result = release_installer.rollback_release(
                install_root=self.install_root, data_root=self.data,
                source_repo=rollback_source,
                trusted_manifest_sha256=self.v1["pin"])

            self.assertEqual(result["data_schema"], {
                "durum": "legacy", "gorevler": "legacy",
                "mesajlar": "legacy/v1/v2",
                "ekranlar": "unversioned-json-object",
            })
            self.assertEqual(tree_digest(self.data), before_data)
        finally:
            self._remove_rollback_source(rollback_source)

    def test_rollback_data_gate_rejects_bad_unknown_and_unsupported_legacy_before_pointer(self):
        _v2, rollback_source = self._install_rollback_pair()
        try:
            current_before = os.readlink(self.install_root / "current")
            previous_before = os.readlink(self.install_root / "previous")
            valid_state = (self.data / "durum.json").read_bytes()
            valid_tasks = (self.data / "gorevler.json").read_bytes()
            cases = {
                "corrupt-json": (b"{invalid", None, None),
                "unknown-root-schema": (
                    valid_tasks.replace(b'"schema_version": 1',
                                        b'"schema_version": 99'), None, None),
                "unsupported-legacy-shape": (
                    b'{"siradaki":1,"gorevler":[{"id":1}]}',
                    b'{"mesaj":"legacy"}\n', None),
                "unknown-message-schema": (
                    valid_tasks, b'{"schema_version":99}\n', None),
                "unversioned-screen-contract-unknown": (
                    valid_tasks, None, b'{"schema_version":1,"satir":"x"}\n'),
            }
            message_path = self.data / "mesaj.jsonl"
            screen_dir = self.data / "ekran"
            for name, (task_value, message_value, screen_value) in cases.items():
                with self.subTest(case=name):
                    (self.data / "durum.json").write_bytes(valid_state)
                    (self.data / "gorevler.json").write_bytes(task_value)
                    if message_value is None:
                        message_path.unlink(missing_ok=True)
                    else:
                        message_path.write_bytes(message_value)
                    if screen_dir.exists():
                        shutil.rmtree(screen_dir)
                    if screen_value is not None:
                        screen_dir.mkdir(mode=0o700)
                        (screen_dir / "fixture.jsonl").write_bytes(screen_value)
                    before_data = tree_digest(self.data)

                    with self.assertRaises(release_installer.InstallError):
                        release_installer.rollback_release(
                            install_root=self.install_root, data_root=self.data,
                            source_repo=rollback_source,
                            trusted_manifest_sha256=self.v1["pin"])

                    self.assertEqual(os.readlink(self.install_root / "current"),
                                     current_before)
                    self.assertEqual(os.readlink(self.install_root / "previous"),
                                     previous_before)
                    self.assertEqual(tree_digest(self.data), before_data)

            (self.data / "durum.json").write_bytes(valid_state)
            (self.data / "gorevler.json").write_bytes(valid_tasks)
            message_path.unlink(missing_ok=True)
            if screen_dir.exists():
                shutil.rmtree(screen_dir)
            result = release_installer.rollback_release(
                install_root=self.install_root, data_root=self.data,
                source_repo=rollback_source,
                trusted_manifest_sha256=self.v1["pin"])
            self.assertEqual(result["current_release_id"], self.v1["release_id"])
        finally:
            self._remove_rollback_source(rollback_source)

    def test_rollback_rejects_unknown_or_unequal_current_and_target_contracts(self):
        _v2, rollback_source = self._install_rollback_pair()
        try:
            current_before = os.readlink(self.install_root / "current")
            previous_before = os.readlink(self.install_root / "previous")
            data_before = tree_digest(self.data)
            current_manifest_path = (self.install_root / "manifests" /
                                     f"{current_before.split('/')[-1]}"
                                     ".manifest.json")
            raw_current = current_manifest_path.read_bytes()
            current_manifest = json.loads(raw_current)
            current_manifest["data_contract"]["schema_compatibility"] = "unknown-contract"
            current_manifest_path.write_bytes(
                release_manifest._canonical_json(current_manifest))

            with self.assertRaisesRegex(release_installer.InstallError,
                                        "unsupported data contract"):
                release_installer.rollback_release(
                    install_root=self.install_root, data_root=self.data,
                    source_repo=rollback_source,
                    trusted_manifest_sha256=self.v1["pin"])
            self.assertEqual(os.readlink(self.install_root / "current"), current_before)
            self.assertEqual(os.readlink(self.install_root / "previous"), previous_before)
            self.assertEqual(tree_digest(self.data), data_before)

            current_manifest_path.write_bytes(raw_current)
            target_id = previous_before.split("/")[-1]
            target_manifest_path = (self.install_root / "manifests" /
                                    f"{target_id}.manifest.json")
            raw_target = target_manifest_path.read_bytes()
            target_manifest = json.loads(raw_target)
            target_manifest["data_contract"]["schema_compatibility"] = \
                "yuva-data-contract/v2"
            changed_target = release_manifest._canonical_json(target_manifest)
            target_manifest_path.write_bytes(changed_target)

            with self.assertRaisesRegex(release_installer.InstallError,
                                        "unsupported data contract"):
                release_installer.rollback_release(
                    install_root=self.install_root, data_root=self.data,
                    source_repo=rollback_source,
                    trusted_manifest_sha256=hashlib.sha256(changed_target).hexdigest())
            self.assertEqual(os.readlink(self.install_root / "current"), current_before)
            self.assertEqual(os.readlink(self.install_root / "previous"), previous_before)
            self.assertEqual(tree_digest(self.data), data_before)
        finally:
            self._remove_rollback_source(rollback_source)

    def test_data_root_overlap_and_unsafe_pointer_fail_closed(self):
        with self.assertRaisesRegex(release_installer.InstallError, "separate"):
            release_installer.install_release(
                install_root=self.data / "install", data_root=self.data,
                payload=self.v1["payload"], manifest_bytes=self.v1["manifest"],
                source_repo=self.repo, trusted_manifest_sha256=self.v1["pin"])
        self.assertFalse((self.data / "install").exists())

        self._install(self.v1)
        current = self.install_root / "current"
        current.unlink()
        current.symlink_to("../../outside")
        with self.assertRaisesRegex(release_installer.InstallError, "canonical release path"):
            release_installer.rollback_release(
                install_root=self.install_root, data_root=self.data,
                source_repo=self.repo, trusted_manifest_sha256=self.v1["pin"])
        self.assertEqual((self.data / "marker").read_bytes(), self.marker_bytes)

    def test_copy_and_staged_manifest_faults_preserve_current_and_data_hash(self):
        self._install(self.v1)
        before_pointer = os.readlink(self.install_root / "current")
        before_data = tree_digest(self.data)
        v2 = self._make_release("v2")

        def partial_copy(_source, destination, **_kwargs):
            (Path(destination) / "partial-copy-marker").write_text(
                "fixture partial copy\n", encoding="utf-8")
            raise OSError("injected copy interruption")

        with self.subTest(point="copy"):
            with patch.object(release_installer.shutil, "copytree",
                              side_effect=partial_copy):
                with self.assertRaisesRegex(OSError, "copy interruption"):
                    self._install(v2)
            self.assertEqual(os.readlink(self.install_root / "current"), before_pointer)
            self.assertEqual(tree_digest(self.data), before_data)
            self.assertEqual(list((self.install_root / "releases").glob(".staging-*")), [])

        original_verify = release_installer._verify
        calls = 0

        def fail_staged_verify(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise release_installer.InstallError("injected staged manifest failure")
            return original_verify(*args, **kwargs)

        with self.subTest(point="staged_manifest_verify"):
            with patch.object(release_installer, "_verify",
                              side_effect=fail_staged_verify):
                with self.assertRaisesRegex(release_installer.InstallError,
                                            "staged manifest failure"):
                    self._install(v2)
            self.assertEqual(calls, 2)
            self.assertEqual(os.readlink(self.install_root / "current"), before_pointer)
            self.assertEqual(tree_digest(self.data), before_data)
            self.assertEqual(list((self.install_root / "releases").glob(".staging-*")), [])

    def test_release_directory_fsync_fault_keeps_old_pointer_and_data(self):
        self._install(self.v1)
        before_pointer = os.readlink(self.install_root / "current")
        before_data = tree_digest(self.data)
        v2 = self._make_release("v2")
        def fail_first_fsync(fd):
            raise OSError("injected releases directory fsync failure")

        with patch.object(release_installer.os, "fsync", side_effect=fail_first_fsync):
            with self.assertRaisesRegex(OSError, "releases directory fsync"):
                self._install(v2)
        self.assertEqual(os.readlink(self.install_root / "current"), before_pointer)
        self.assertEqual(tree_digest(self.data), before_data)
        self.assertTrue((self.install_root / "releases" / v2["release_id"]).is_dir())
        self.assertFalse((self.install_root / "current").resolve().name == v2["release_id"])

    def test_current_pointer_replace_fault_is_commit_unknown_without_rollback(self):
        self._install(self.v1)
        before_pointer = os.readlink(self.install_root / "current")
        before_data = tree_digest(self.data)
        v2 = self._make_release("v2")
        real_replace = os.replace

        def fail_current_replace(source, destination):
            if Path(destination).name == "current":
                raise OSError("injected current pointer replace failure")
            return real_replace(source, destination)

        with patch.object(release_installer.os, "replace",
                          side_effect=fail_current_replace):
            with self.assertRaisesRegex(release_installer.CommitUnknown,
                                        "commit_unknown"):
                self._install(v2)
        self.assertEqual(os.readlink(self.install_root / "current"), before_pointer)
        self.assertEqual(tree_digest(self.data), before_data)

    def test_post_replace_pointer_fsync_fault_is_commit_unknown_no_auto_rollback(self):
        self._install(self.v1)
        before_data = tree_digest(self.data)
        v2 = self._make_release("v2")
        real_fsync = os.fsync
        calls = 0

        def fail_after_current_replace(fd):
            nonlocal calls
            calls += 1
            if calls == 7:
                raise OSError("injected post-replace current directory fsync failure")
            return real_fsync(fd)

        with patch.object(release_installer.os, "fsync",
                          side_effect=fail_after_current_replace):
            with self.assertRaisesRegex(release_installer.CommitUnknown,
                                        "directory durability is unknown"):
                self._install(v2)
        self.assertEqual(calls, 7)
        self.assertEqual(os.readlink(self.install_root / "current"),
                         f"releases/{v2['release_id']}")
        self.assertEqual(tree_digest(self.data), before_data)
        self.assertFalse(os.readlink(self.install_root / "current")
                         == f"releases/{self.v1['release_id']}")

    def test_pointer_fd_close_error_after_commit_reports_committed_state(self):
        self._install(self.v1)
        v2 = self._make_release("v2")
        before_data = tree_digest(self.data)
        real_open = os.open
        real_close = os.close
        real_replace = os.replace
        root_fds = set()
        current_replaced = False
        injected = False

        def tracked_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if Path(path) == self.install_root:
                root_fds.add(fd)
            return fd

        def track_current_replace(source, destination):
            nonlocal current_replaced
            result = real_replace(source, destination)
            if Path(destination).name == "current":
                current_replaced = True
            return result

        def close_after_current_commit(fd):
            nonlocal injected
            if fd in root_fds and current_replaced and not injected:
                injected = True
                real_close(fd)
                raise OSError("injected root descriptor close after commit")
            return real_close(fd)

        with patch.object(release_installer.os, "open", side_effect=tracked_open):
            with patch.object(release_installer.os, "replace",
                              side_effect=track_current_replace):
                with patch.object(release_installer.os, "close",
                                  side_effect=close_after_current_commit):
                    with self.assertRaisesRegex(
                            release_installer.CommitCleanupError,
                            "commit_complete.*inspect its exact target"):
                        self._install(v2)

        self.assertTrue(injected)
        self.assertEqual(os.readlink(self.install_root / "current"),
                         f"releases/{v2['release_id']}")
        self.assertEqual(os.readlink(self.install_root / "previous"),
                         f"releases/{self.v1['release_id']}")
        self.assertEqual(tree_digest(self.data), before_data)
        self.assertEqual(list((self.install_root / "releases").glob(".staging-*")), [])

    def test_lock_fd_close_error_after_success_reports_committed_state(self):
        before_data = tree_digest(self.data)
        real_open = os.open
        real_close = os.close
        real_replace = os.replace
        lock_fds = set()
        current_replaced = False
        injected = False

        def tracked_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if Path(path).name == release_installer.LOCK_NAME:
                lock_fds.add(fd)
            return fd

        def track_current_replace(source, destination):
            nonlocal current_replaced
            result = real_replace(source, destination)
            if Path(destination).name == "current":
                current_replaced = True
            return result

        def close_after_current_commit(fd):
            nonlocal injected
            if fd in lock_fds and current_replaced and not injected:
                injected = True
                real_close(fd)
                raise OSError("injected lock descriptor close after commit")
            return real_close(fd)

        with patch.object(release_installer.os, "open", side_effect=tracked_open):
            with patch.object(release_installer.os, "replace",
                              side_effect=track_current_replace):
                with patch.object(release_installer.os, "close",
                                  side_effect=close_after_current_commit):
                    with self.assertRaisesRegex(
                            release_installer.CommitCleanupError,
                            "commit_complete.*lock descriptor close failed"):
                        self._install(self.v1)

        self.assertTrue(injected)
        self.assertEqual(os.readlink(self.install_root / "current"),
                         f"releases/{self.v1['release_id']}")
        self.assertFalse((self.install_root / "previous").exists())
        self.assertEqual(tree_digest(self.data), before_data)


def stat_mode(path):
    return Path(path).stat().st_mode & 0o777


def tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*"),
                       key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        info = path.lstat()
        digest.update(rel + b"\0" + str(info.st_mode & 0o777).encode("ascii") + b"\0")
        if path.is_symlink():
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
