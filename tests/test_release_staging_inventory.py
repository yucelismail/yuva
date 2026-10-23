import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import sys
import unittest
from unittest import mock
import uuid

import release_staging_inventory as inventory


def release_id(seed):
    return seed * 40 + "-" + ("f" if seed != "f" else "e") * 64


def filesystem_snapshot(root):
    result = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        for name in dirs + files:
            path = base / name
            info = path.lstat()
            key = path.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode):
                value = ("symlink", os.readlink(path), stat.S_IMODE(info.st_mode))
            elif stat.S_ISREG(info.st_mode):
                value = ("file", path.read_bytes(), stat.S_IMODE(info.st_mode))
            else:
                value = ("other", stat.S_IMODE(info.st_mode))
            result[key] = value
    return result


class ReleaseStagingInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-release-inventory-")
        self.root = Path(self.temp.name) / "install"
        self.root.mkdir(mode=0o700)
        self.releases = self.root / "releases"
        self.manifests = self.root / "manifests"
        self.releases.mkdir(mode=0o700)
        self.manifests.mkdir(mode=0o700)

    def tearDown(self):
        self.temp.cleanup()

    def test_lists_staging_orphan_inactive_and_pointer_release_without_contents(self):
        staging_uuid = uuid.uuid4().hex
        staging = self.releases / f".staging-{staging_uuid}"
        staging.mkdir(mode=0o700)
        (staging / "payload-secret.txt").write_text("fixture payload secret")

        missing_receipt_id = release_id("a")
        missing_receipt = self.releases / missing_receipt_id
        missing_receipt.mkdir(mode=0o555)
        missing_receipt.chmod(0o555)

        pointer_id = release_id("b")
        pointer_release = self.releases / pointer_id
        pointer_release.mkdir(mode=0o555)
        pointer_release.chmod(0o555)
        pointer_manifest = self.manifests / f"{pointer_id}.manifest.json"
        pointer_manifest.write_text("fixture manifest secret")
        pointer_manifest.chmod(0o600)
        (self.root / "current").symlink_to(f"releases/{pointer_id}")

        inactive_id = release_id("c")
        inactive = self.releases / inactive_id
        inactive.mkdir(mode=0o555)
        inactive.chmod(0o555)
        inactive_manifest = self.manifests / f"{inactive_id}.manifest.json"
        inactive_manifest.write_text("other fixture manifest secret")
        inactive_manifest.chmod(0o600)

        (self.root / ".installer.lock").write_text("lock contents are not inspected")
        before = filesystem_snapshot(self.root)

        report = inventory.inventory_install_root(self.root)

        self.assertEqual(filesystem_snapshot(self.root), before)
        self.assertEqual(report["install_root"], "<explicit-root-redacted>")
        self.assertEqual(report["active_installer_process"], "unknown")
        self.assertEqual(report["installer_lock"]["state"], "present_uninspected")
        self.assertEqual(report["decision"], "HOLD")
        items = {item.get("release_id", item.get("id")): item
                 for item in report["items"]}
        self.assertEqual(items[staging_uuid]["classification"], "STAGING_STATE_UNKNOWN")
        self.assertEqual(items[staging_uuid]["decision"], "HOLD")
        self.assertEqual(items[missing_receipt_id]["classification"],
                         "PUBLISHED_RECEIPT_INCOMPLETE")
        self.assertEqual(items[pointer_id]["classification"], "POINTER_REFERENCED")
        self.assertEqual(items[inactive_id]["classification"], "PUBLISHED_INACTIVE")
        self.assertEqual(items[pointer_id]["manifest_receipt"]["content_read"], False)

        rendered = json.dumps(report, ensure_ascii=False)
        for secret in ("fixture payload secret", "fixture manifest secret",
                       "other fixture manifest secret", "lock contents"):
            self.assertNotIn(secret, rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_never_echoes_unsafe_pointer_or_symlink_target(self):
        external = self.root.parent / "outside-secret"
        external.mkdir()
        link = self.root / "current"
        link.symlink_to(f"../{external.name}")
        staging_name = f".staging-{uuid.uuid4().hex}"
        (self.releases / staging_name).symlink_to(external, target_is_directory=True)
        before = filesystem_snapshot(self.root)

        report = inventory.inventory_install_root(self.root)

        self.assertEqual(filesystem_snapshot(self.root), before)
        current = next(item for item in report["pointers"] if item["name"] == "current")
        self.assertEqual(current["state"], "unsafe_target")
        self.assertTrue(current["target_omitted"])
        staged = next(item for item in report["items"] if item.get("id") == staging_name[9:])
        self.assertEqual(staged["classification"], "HOLD_UNKNOWN")
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(str(external), rendered)
        self.assertNotIn("outside-secret", rendered)

    def test_inventory_is_bounded_and_unknown_names_are_not_echoed(self):
        for index in range(5):
            (self.releases / f"unexpected-{index}-secret-name").write_text("ignored")
        before = filesystem_snapshot(self.root)

        report = inventory.inventory_install_root(self.root, max_entries=2)

        self.assertEqual(filesystem_snapshot(self.root), before)
        self.assertEqual(report["decision"], "HOLD")
        self.assertTrue(report["truncated"])
        self.assertLessEqual(len(report["items"]), 2)
        self.assertGreater(report["unknown_entry_count"], 0)
        self.assertNotIn("unexpected-", json.dumps(report))

    def test_child_directory_identity_race_is_hold_without_following_replacement(self):
        replacement = self.root.parent / "replacement-releases"
        replacement.mkdir(mode=0o700)
        (replacement / release_id("d")).mkdir(mode=0o700)
        before = filesystem_snapshot(self.root)
        before_fds = len(os.listdir("/proc/self/fd")) if Path("/proc/self/fd").is_dir() else None
        real_open = os.open

        def replace_after_metadata(path, flags, *args, **kwargs):
            if path == "releases" and kwargs.get("dir_fd") is not None:
                return real_open(replacement, flags)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(inventory.os, "open", side_effect=replace_after_metadata):
            report = inventory.inventory_install_root(self.root)

        self.assertEqual(filesystem_snapshot(self.root), before)
        self.assertEqual(report["decision"], "HOLD")
        self.assertEqual(report["releases_directory"]["state"], "changed_during_scan")
        self.assertEqual(report["items"], [])
        self.assertFalse((self.root / "current").exists())
        if before_fds is not None:
            self.assertEqual(len(os.listdir("/proc/self/fd")), before_fds)

    def test_missing_and_unsafe_manifest_metadata_remain_hold(self):
        missing_id = release_id("e")
        unsafe_mode_id = release_id("f")
        unsafe_link_id = release_id("9")
        for release in (missing_id, unsafe_mode_id, unsafe_link_id):
            (self.releases / release).mkdir(mode=0o555)
            (self.releases / release).chmod(0o555)

        unsafe_mode = self.manifests / f"{unsafe_mode_id}.manifest.json"
        unsafe_mode.write_text("synthetic manifest metadata only")
        unsafe_mode.chmod(0o644)
        outside_manifest = self.root.parent / "outside-manifest-secret"
        outside_manifest.write_text("must not be read")
        (self.manifests / f"{unsafe_link_id}.manifest.json").symlink_to(outside_manifest)
        before = filesystem_snapshot(self.root)

        report = inventory.inventory_install_root(self.root)

        self.assertEqual(filesystem_snapshot(self.root), before)
        self.assertEqual(report["decision"], "HOLD")
        items = {item["release_id"]: item for item in report["items"]}
        self.assertEqual(items[missing_id]["manifest_receipt"]["state"], "missing")
        self.assertEqual(items[missing_id]["classification"], "PUBLISHED_RECEIPT_INCOMPLETE")
        self.assertEqual(items[unsafe_mode_id]["manifest_receipt"]["state"], "unsafe_metadata")
        self.assertEqual(items[unsafe_mode_id]["classification"], "HOLD_UNKNOWN")
        self.assertEqual(items[unsafe_link_id]["manifest_receipt"]["state"], "unsafe_metadata")
        self.assertEqual(items[unsafe_link_id]["classification"], "HOLD_UNKNOWN")
        self.assertNotIn("must not be read", json.dumps(report))

    def test_cli_requires_explicit_root_and_errors_do_not_print_requested_path(self):
        missing = self.root / "missing-outside-detail"
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            code = inventory.main(["--install-root", str(missing)])

        self.assertEqual(code, 2)
        self.assertNotIn(str(missing), output.getvalue())
        self.assertIn('"decision":"HOLD"', output.getvalue())

    def test_symlink_component_in_explicit_root_is_rejected_without_following(self):
        outside = self.root.parent / "outside-root"
        outside.mkdir()
        alias = self.root.parent / "install-link"
        alias.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(inventory.InventoryError, "real directories"):
            inventory.inventory_install_root(alias)

    def test_symlinked_releases_directory_is_not_followed_for_pointer_lookup(self):
        root = self.root.parent / "install-with-release-link"
        root.mkdir(mode=0o700)
        outside = self.root.parent / "outside-releases"
        outside.mkdir(mode=0o700)
        target_id = release_id("d")
        (outside / target_id).mkdir(mode=0o700)
        (root / "releases").symlink_to(outside, target_is_directory=True)
        (root / "current").symlink_to(f"releases/{target_id}")

        report = inventory.inventory_install_root(root)

        current = next(item for item in report["pointers"] if item["name"] == "current")
        self.assertEqual(current["state"], "missing_or_unsafe_target")
        self.assertNotIn(str(outside), json.dumps(report))
        self.assertEqual(report["items"], [])

    @unittest.skipUnless(sys.platform.startswith("linux")
                         and Path("/proc/self/fd").is_dir(),
                         "requires Linux /proc/self/fd descriptor count")
    def test_repeated_inventory_keeps_process_descriptor_count_stable(self):
        def descriptor_count():
            return len(os.listdir("/proc/self/fd"))

        before = descriptor_count()
        for _ in range(40):
            report = inventory.inventory_install_root(self.root)
            self.assertEqual(report["decision"], "HOLD")
        after = descriptor_count()

        self.assertEqual(after, before)

    @unittest.skipUnless(sys.platform.startswith("linux")
                         and Path("/proc/self/fd").is_dir(),
                         "requires Linux /proc/self/fd descriptor count")
    def test_child_directory_fstat_error_closes_opened_descriptor(self):
        def descriptor_count():
            return len(os.listdir("/proc/self/fd"))

        parent_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            info = self.releases.lstat()
            before = descriptor_count()
            real_open = os.open
            real_fstat = os.fstat
            child_fds = set()

            def tracked_open(path, flags, *args, **kwargs):
                fd = real_open(path, flags, *args, **kwargs)
                if path == "releases" and kwargs.get("dir_fd") == parent_fd:
                    child_fds.add(fd)
                return fd

            def failing_fstat(fd):
                if fd in child_fds:
                    raise OSError("injected child fstat failure")
                return real_fstat(fd)

            with mock.patch.object(inventory.os, "open", side_effect=tracked_open):
                with mock.patch.object(inventory.os, "fstat", side_effect=failing_fstat):
                    with self.assertRaisesRegex(OSError, "injected child fstat"):
                        inventory._open_child_directory(parent_fd, "releases", info)

            self.assertEqual(descriptor_count(), before)
        finally:
            os.close(parent_fd)

    @unittest.skipUnless(sys.platform.startswith("linux")
                         and Path("/proc/self/fd").is_dir(),
                         "requires Linux /proc/self/fd descriptor count")
    def test_second_child_open_error_closes_first_child_descriptor(self):
        def descriptor_count():
            return len(os.listdir("/proc/self/fd"))

        before = descriptor_count()
        real_open_child = inventory._open_child_directory

        def fail_on_manifests(parent_fd, name, info):
            if name == "manifests":
                raise OSError("injected second child open failure")
            return real_open_child(parent_fd, name, info)

        with mock.patch.object(inventory, "_open_child_directory",
                               side_effect=fail_on_manifests):
            with self.assertRaisesRegex(OSError, "injected second child open"):
                inventory.inventory_install_root(self.root)

        self.assertEqual(descriptor_count(), before)

    @unittest.skipUnless(sys.platform.startswith("linux")
                         and Path("/proc/self/fd").is_dir(),
                         "requires Linux /proc/self/fd descriptor count")
    def test_explicit_root_traversal_close_error_closes_next_descriptor(self):
        def descriptor_count():
            return len(os.listdir("/proc/self/fd"))

        before = descriptor_count()
        real_open = os.open
        real_close = os.close
        traversal_fds = set()
        injected = False

        def tracked_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            traversal_fds.add(fd)
            return fd

        def close_then_raise(fd):
            nonlocal injected
            if fd in traversal_fds and not injected:
                injected = True
                real_close(fd)
                raise OSError("injected traversal close error")
            return real_close(fd)

        with mock.patch.object(inventory.os, "open", side_effect=tracked_open):
            with mock.patch.object(inventory.os, "close", side_effect=close_then_raise):
                with self.assertRaisesRegex(OSError, "injected traversal close"):
                    inventory.inventory_install_root(self.root)

        self.assertTrue(injected)
        self.assertEqual(descriptor_count(), before)

    @unittest.skipUnless(sys.platform.startswith("linux")
                         and Path("/proc/self/fd").is_dir(),
                         "requires Linux /proc/self/fd descriptor count")
    def test_child_cleanup_close_error_still_closes_other_child(self):
        def descriptor_count():
            return len(os.listdir("/proc/self/fd"))

        before = descriptor_count()
        real_open = os.open
        real_close = os.close
        child_fds = set()
        injected = False

        def tracked_open(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path in {"releases", "manifests"}:
                child_fds.add(fd)
            return fd

        def close_then_raise(fd):
            nonlocal injected
            if fd in child_fds and not injected:
                injected = True
                real_close(fd)
                raise OSError("injected child cleanup close error")
            return real_close(fd)

        with mock.patch.object(inventory.os, "open", side_effect=tracked_open):
            with mock.patch.object(inventory.os, "close", side_effect=close_then_raise):
                with self.assertRaisesRegex(OSError, "injected child cleanup close"):
                    inventory.inventory_install_root(self.root)

        self.assertTrue(injected)
        self.assertEqual(len(child_fds), 2)
        self.assertEqual(descriptor_count(), before)


if __name__ == "__main__":
    unittest.main()
