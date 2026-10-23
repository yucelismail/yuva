import hashlib
import contextlib
import importlib.util
import io
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tarfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPO_ROOT / "release_manifest.py"
spec = importlib.util.spec_from_file_location(
    "yuva_release_manifest", TOOL_PATH,
    loader=SourceFileLoader("yuva_release_manifest", str(TOOL_PATH)))
release_manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_manifest)


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git_home = self.root / "git-home"
        self.git_home.mkdir()
        self.git_env = os.environ.copy()
        self.git_env.update({
            "HOME": str(self.git_home),
            "XDG_CONFIG_HOME": str(self.git_home / ".config"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        self.repo = self.root / "source"
        self.repo.mkdir()
        self._git(self.repo, "init", "-q")
        self._git(self.repo, "config", "user.name", "Fixture")
        self._git(self.repo, "config", "user.email", "fixture@example.invalid")
        self._write_source("bin/yuva", "#!/usr/bin/env python3\nprint('fixture')\n", 0o755)
        self._write_source("panel/server.py", "print('panel')\n")
        self._write_source("panel/ui.html", "<!doctype html><title>fixture</title>\n")
        self._write_source("contrib/systemd/yuva-panel.service", "[Service]\nExecStart=fixture\n")
        self._write_source("README.md", "fixture release\n")
        (self.repo / "bin" / "yuva-help").symlink_to("yuva")
        self._git(self.repo, "add", ".")
        self._git(self.repo, "commit", "-qm", "fixture")
        self.payload = self.root / "payload"
        self._export_payload()

    def tearDown(self):
        self.temp.cleanup()

    def _write_source(self, relative, content, mode=0o644):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(mode)

    def _git(self, repo, *args, **kwargs):
        """Run Git only against a repository rooted in this test's temp dir."""
        repo = Path(repo).resolve()
        if repo != self.root and self.root not in repo.parents:
            raise AssertionError("release manifest Git fixture escaped its temp root")
        kwargs.setdefault("check", True)
        kwargs.setdefault("env", self.git_env)
        return subprocess.run(["git", "-C", str(repo), *args], **kwargs)

    def _export_payload(self):
        self.payload.mkdir()
        for source in self.repo.rglob("*"):
            relative = source.relative_to(self.repo)
            if ".git" in relative.parts:
                continue
            target = self.payload / relative
            if source.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(os.readlink(source))
            elif source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
                target.chmod(source.stat().st_mode & 0o777)

    def _manifest(self):
        return release_manifest.create_manifest(
            self.repo, self.payload, "fixture://yuva")

    def _new_git_repo(self, path, relative, content):
        path.mkdir()
        self._git(path, "init", "-q")
        self._git(path, "config", "user.name", "Fixture")
        self._git(path, "config", "user.email", "fixture@example.invalid")
        file_path = path / relative
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        self._git(path, "add", ".")
        self._git(path, "commit", "-qm", "fixture")
        return file_path

    def _replace_payload(self, name):
        shutil.rmtree(self.payload)
        self.payload = self.root / name
        self._export_payload()

    def _bytes(self, manifest):
        return release_manifest._canonical_json(manifest)

    def test_clean_source_payload_is_deterministic_but_not_trusted_by_default(self):
        manifest = self._manifest()
        raw = self._bytes(manifest)

        self.assertEqual(manifest["manifest_schema"], "yuva-release-manifest/v1")
        self.assertEqual(manifest["data_contract"]["schema_compatibility"],
                         release_manifest.DATA_CONTRACT)
        self.assertTrue(manifest["artifact"]["payload_matches_source"])
        self.assertFalse(manifest["release_eligible"])
        self.assertEqual(raw, self._bytes(self._manifest()))
        without_anchor = release_manifest.verify_manifest(self.payload, raw, source_repo=self.repo)
        self.assertTrue(without_anchor["payload_match"])
        self.assertTrue(without_anchor["source_match"])
        self.assertFalse(without_anchor["verified_release"])

        anchor = hashlib.sha256(raw).hexdigest()
        pinned = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=anchor)
        self.assertTrue(pinned["external_trust_anchor_match"])
        self.assertTrue(pinned["verified_release"])
        self.assertTrue(pinned["release_eligible"])

    def test_dirty_worktree_never_becomes_release_eligible(self):
        manifest = self._manifest()
        (self.repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        raw = self._bytes(manifest)
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())

        self.assertEqual(manifest["source"]["worktree_state"], "clean")
        self.assertFalse(result["source_match"])
        self.assertFalse(result["verified_release"])

    def test_dirty_source_at_generation_is_inventory_only(self):
        (self.repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

        manifest = self._manifest()

        self.assertEqual(manifest["source"]["worktree_state"], "dirty")
        self.assertTrue(manifest["artifact"]["payload_matches_source"])
        self.assertFalse(manifest["release_eligible"])

    def test_payload_drift_and_external_anchor_mismatch_do_not_verify(self):
        manifest = self._manifest()
        raw = self._bytes(manifest)
        (self.payload / "README.md").write_text("changed\n", encoding="utf-8")

        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())

        self.assertFalse(result["payload_match"])
        self.assertFalse(result["verified_release"])
        bad_anchor = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256="0" * 64)
        self.assertFalse(bad_anchor["external_trust_anchor_match"])

    def test_payload_file_set_mode_and_content_drift_fail_closed(self):
        manifest = self._manifest()
        raw = self._bytes(manifest)
        pin = hashlib.sha256(raw).hexdigest()
        readme = self.payload / "README.md"
        original_bytes = readme.read_bytes()
        original_mode = readme.stat().st_mode & 0o777

        extra = self.payload / "unlisted-extra.txt"
        extra.write_text("not in manifest\n", encoding="utf-8")
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=pin)
        self.assertFalse(result["payload_match"])
        self.assertFalse(result["verified_release"])
        extra.unlink()

        readme.chmod(0o600 if original_mode != 0o600 else 0o644)
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=pin)
        self.assertFalse(result["payload_match"])
        self.assertFalse(result["verified_release"])
        readme.chmod(original_mode)

        readme.write_text("changed payload content\n", encoding="utf-8")
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=pin)
        self.assertFalse(result["payload_match"])
        self.assertFalse(result["verified_release"])
        readme.write_bytes(original_bytes)
        readme.chmod(original_mode)

        source_readme = self.repo / "README.md"
        original_source = source_readme.read_bytes()
        source_readme.write_text("dirty source content\n", encoding="utf-8")
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=pin)
        self.assertFalse(result["source_match"])
        self.assertFalse(result["verified_release"])
        source_readme.write_bytes(original_source)

    def test_manifest_file_set_order_and_canonical_byte_tampering_fail_closed(self):
        original = self._manifest()
        raw = self._bytes(original)
        pin = hashlib.sha256(raw).hexdigest()

        with self.assertRaisesRegex(release_manifest.ManifestError,
                                    "canonical serialization"):
            release_manifest.verify_manifest(
                self.payload, raw + b" ", source_repo=self.repo,
                trusted_manifest_sha256=pin)

        reordered = json.loads(raw)
        reordered["artifact"]["files"].reverse()
        with self.assertRaisesRegex(release_manifest.ManifestError,
                                    "canonical path order"):
            release_manifest.verify_manifest(
                self.payload, self._bytes(reordered), source_repo=self.repo,
                trusted_manifest_sha256=hashlib.sha256(
                    self._bytes(reordered)).hexdigest())

        changed_set = json.loads(raw)
        records = changed_set["artifact"]["files"]
        records.append({
            "path": "zz-fixture-extra.txt", "type": "regular", "mode": "0644",
            "size": 0, "sha256": hashlib.sha256(b"").hexdigest(),
        })
        records.sort(key=lambda row: row["path"].encode("utf-8"))
        digest = "sha256:" + release_manifest._payload_digest(records)
        changed_set["artifact"]["payload_digest"] = digest
        changed_set["release_id"] = (
            f"{changed_set['source']['commit']}-{digest[len('sha256:'):]}")
        changed_set["artifact"]["payload_matches_source"] = True
        changed_raw = self._bytes(changed_set)
        result = release_manifest.verify_manifest(
            self.payload, changed_raw, source_repo=self.repo,
            # This is a fixture-local digest, not an independent trust anchor.
            trusted_manifest_sha256=hashlib.sha256(changed_raw).hexdigest())
        self.assertFalse(result["payload_match"])
        self.assertFalse(result["verified_release"])

    def test_missing_extra_and_escaping_symlink_payloads_are_rejected(self):
        manifest = self._manifest()
        (self.payload / "extra.txt").write_text("untracked payload\n", encoding="utf-8")
        result = release_manifest.verify_manifest(
            self.payload, self._bytes(manifest), source_repo=self.repo,
            trusted_manifest_sha256=hashlib.sha256(self._bytes(manifest)).hexdigest())
        self.assertFalse(result["payload_match"])

        escaping = self.payload / "escape"
        escaping.symlink_to("../../outside")
        with self.assertRaises(release_manifest.ManifestError):
            release_manifest._payload_files(self.payload)

        (self.payload / "extra.txt").unlink()
        escaping.unlink()
        (self.payload / "README.md").unlink()
        self.assertFalse(release_manifest.verify_manifest(
            self.payload, self._bytes(manifest), source_repo=self.repo,
            trusted_manifest_sha256=hashlib.sha256(self._bytes(manifest)).hexdigest())["payload_match"])

    def test_missing_required_asset_cannot_generate_or_verify_eligible_manifest(self):
        manifest = self._manifest()
        raw = self._bytes(manifest)
        (self.payload / "panel" / "server.py").unlink()

        with self.assertRaisesRegex(release_manifest.ManifestError,
                                    "required release files missing"):
            self._manifest()
        with self.assertRaisesRegex(release_manifest.ManifestError,
                                    "required release files missing"):
            release_manifest.verify_manifest(
                self.payload, raw, source_repo=self.repo,
                trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())

    def test_git_archive_export_ignore_payload_is_not_eligible(self):
        self._write_source("assets/optional.txt", "tracked but export-ignored\n")
        self._write_source(".gitattributes", "assets/optional.txt export-ignore\n")
        self._git(self.repo, "add", ".")
        self._git(self.repo, "commit", "-qm", "add export-ignore fixture")

        archive = self.root / "export-ignore.tar"
        self._git(self.repo, "archive", "--format=tar",
                  f"--output={archive}", "HEAD")
        shutil.rmtree(self.payload)
        self.payload = self.root / "payload-from-git-archive"
        self.payload.mkdir()
        with tarfile.open(archive, "r:") as exported:
            exported.extractall(self.payload)

        manifest = self._manifest()
        raw = self._bytes(manifest)
        self.assertFalse((self.payload / "assets" / "optional.txt").exists())
        self.assertEqual(manifest["source"]["worktree_state"], "clean")
        self.assertFalse(manifest["artifact"]["payload_matches_source"])
        self.assertFalse(manifest["release_eligible"])
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())
        self.assertFalse(result["verified_release"])
        self.assertFalse(result["source_match"])

    def test_ignored_and_untracked_payload_entries_are_not_eligible(self):
        self._write_source(".gitignore", "ignored-only.bin\n")
        self._git(self.repo, "add", ".gitignore")
        self._git(self.repo, "commit", "-qm", "ignore fixture payloads")
        (self.repo / "ignored-only.bin").write_text("ignored payload\n", encoding="utf-8")
        self._replace_payload("payload-with-ignored-file")
        ignored_manifest = self._manifest()
        self.assertEqual(ignored_manifest["source"]["worktree_state"], "clean")
        self.assertFalse(ignored_manifest["artifact"]["payload_matches_source"])
        self.assertFalse(ignored_manifest["release_eligible"])

        (self.repo / "untracked.bin").write_text("untracked payload\n", encoding="utf-8")
        self._replace_payload("payload-with-ignored-and-untracked")
        manifest = self._manifest()
        raw = self._bytes(manifest)
        self.assertEqual(manifest["source"]["worktree_state"], "dirty")
        self.assertFalse(manifest["artifact"]["payload_matches_source"])
        self.assertFalse(manifest["release_eligible"])
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())
        self.assertFalse(result["verified_release"])

    def test_gitlink_and_dirty_nested_submodule_are_not_eligible(self):
        leaf_repo = self.root / "leaf-submodule"
        self._new_git_repo(leaf_repo, "leaf.txt", "leaf fixture\n")

        middle_repo = self.root / "middle-submodule"
        middle_repo.mkdir()
        self._git(middle_repo, "init", "-q")
        self._git(middle_repo, "config", "user.name", "Fixture")
        self._git(middle_repo, "config", "user.email", "fixture@example.invalid")
        self._git(middle_repo, "-c", "protocol.file.allow=always",
                  "submodule", "add", str(leaf_repo), "nested/leaf",
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._git(middle_repo, "add", ".gitmodules", "nested/leaf")
        self._git(middle_repo, "commit", "-qm", "add nested submodule")

        self._git(self.repo, "-c", "protocol.file.allow=always",
                  "submodule", "add", str(middle_repo), "vendor/middle",
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._git(self.repo, "add", ".gitmodules", "vendor/middle")
        self._git(self.repo, "commit", "-qm", "add nested gitlink fixture")
        self._git(self.repo, "-c", "protocol.file.allow=always",
                  "submodule", "update", "--init", "--recursive",
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self._replace_payload("payload-with-gitlink")
        manifest = self._manifest()
        self.assertEqual(manifest["source"]["worktree_state"], "clean")
        self.assertTrue(manifest["source"]["submodules"])
        self.assertTrue(all(row["state"] == "pinned_clean"
                            for row in manifest["source"]["submodules"]))
        self.assertFalse(manifest["artifact"]["payload_matches_source"])
        self.assertFalse(manifest["release_eligible"])
        with self.assertRaisesRegex(release_manifest.ManifestError, "submodule payloads are unsupported"):
            release_manifest.verify_manifest(
                self.payload, self._bytes(manifest), source_repo=self.repo,
                trusted_manifest_sha256=hashlib.sha256(self._bytes(manifest)).hexdigest())

        nested_file = self.repo / "vendor" / "middle" / "nested" / "leaf" / "leaf.txt"
        nested_file.write_text("dirty nested submodule\n", encoding="utf-8")
        dirty_source = release_manifest._source_state(self.repo, "fixture://yuva")
        self.assertEqual(dirty_source["worktree_state"], "dirty")
        dirty_manifest = self._manifest()
        self.assertFalse(dirty_manifest["release_eligible"])

    def test_unapproved_executable_is_rejected(self):
        extra = self.payload / "bin" / "unexpected-tool"
        extra.write_text("#!/bin/sh\n", encoding="utf-8")
        extra.chmod(0o755)

        with self.assertRaisesRegex(release_manifest.ManifestError,
                                    "unapproved executable"):
            self._manifest()

    def test_unknown_source_and_manifest_tampering_are_not_verified(self):
        manifest = release_manifest.create_manifest(
            self.root / "no-source", self.payload, "fixture://unknown")
        self.assertIsNone(manifest["source"]["commit"])
        self.assertFalse(manifest["release_eligible"])

        source_manifest = self._manifest()
        raw = self._bytes(source_manifest)
        source_manifest["artifact"]["files"][0]["sha256"] = "0" * 64
        tampered = self._bytes(source_manifest)
        with self.assertRaises(release_manifest.ManifestError):
            release_manifest.verify_manifest(
                self.payload, tampered, source_repo=self.repo,
                trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())

    def test_noncanonical_repository_identity_stays_unverified(self):
        manifest = release_manifest.create_manifest(
            self.repo, self.payload, "/home/fixture/source")
        raw = self._bytes(manifest)
        result = release_manifest.verify_manifest(
            self.payload, raw, source_repo=self.repo,
            trusted_manifest_sha256=hashlib.sha256(raw).hexdigest())

        self.assertIsNone(manifest["source"]["repository_id"])
        self.assertFalse(result["source_match"])
        self.assertFalse(result["verified_release"])

    def test_cli_creates_non_overwriting_inventory_and_verifies_external_pin(self):
        output = self.root / "manifest.json"
        with contextlib.redirect_stdout(io.StringIO()):
            created = release_manifest.main([
                "create", "--repo", str(self.repo), "--payload", str(self.payload),
                "--repository-id", "fixture://yuva", "--output", str(output),
            ])
        raw = output.read_bytes()
        pin = hashlib.sha256(raw).hexdigest()

        with contextlib.redirect_stdout(io.StringIO()):
            untrusted = release_manifest.main([
                "verify", "--payload", str(self.payload), "--manifest", str(output),
                "--source-repo", str(self.repo),
            ])
            trusted = release_manifest.main([
                "verify", "--payload", str(self.payload), "--manifest", str(output),
                "--source-repo", str(self.repo), "--trusted-manifest-sha256", pin,
            ])

        self.assertEqual(created, 0)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(untrusted, 1)
        self.assertEqual(trusted, 0)
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            overwrite = release_manifest.main([
                "create", "--repo", str(self.repo), "--payload", str(self.payload),
                "--repository-id", "fixture://yuva", "--output", str(output),
            ])
        self.assertEqual(overwrite, 2)


if __name__ == "__main__":
    unittest.main()
