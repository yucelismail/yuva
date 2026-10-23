#!/usr/bin/env python3
"""Bounded, read-only inventory for an explicit Yuva INSTALL_ROOT.

This prototype reports only safe relative identifiers and filesystem metadata.
It never reads release/manifest contents, follows child symlinks, or changes
files, pointers, permissions, or directories. Unknown transaction ownership is
always HOLD.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import itertools
import json
import os
from pathlib import Path
import re
import stat
import sys


RELEASE_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})-[0-9a-f]{64}$")
STAGING_ID_RE = re.compile(r"^\.staging-([0-9a-f]{32})$")
POINTER_TMP_RE = re.compile(r"^\.(?:current|previous)\.([0-9a-f]{32})\.tmp$")
MANIFEST_SUFFIX = ".manifest.json"
DEFAULT_MAX_ENTRIES = 256
MAX_ENTRIES_LIMIT = 4096
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class InventoryError(ValueError):
    """Safe, path-free inventory error."""


@dataclass(frozen=True)
class _EntrySnapshot:
    name: str
    info: os.stat_result | None
    metadata_error: str | None = None


def _stat_at(parent_fd: int, name: str, *, missing_ok: bool = False):
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise InventoryError("required path is missing") from None
    except OSError as exc:
        raise InventoryError(f"path metadata unavailable ({type(exc).__name__})") from None


def _open_explicit_root(root_value: str | os.PathLike[str]
                        ) -> tuple[Path, int, os.stat_result]:
    try:
        root = Path(root_value).expanduser()
    except (TypeError, ValueError, RuntimeError):
        raise InventoryError("INSTALL_ROOT is invalid") from None
    if not root.is_absolute() or root == Path(root.anchor) or ".." in root.parts:
        raise InventoryError("INSTALL_ROOT must be an absolute canonical directory")

    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(root.anchor, os.O_RDONLY | directory_flag)
    except OSError as exc:
        raise InventoryError(f"INSTALL_ROOT unavailable ({type(exc).__name__})") from None
    try:
        for part in root.parts[1:]:
            try:
                next_fd = os.open(part, os.O_RDONLY | directory_flag | nofollow_flag,
                                  dir_fd=fd)
            except OSError as exc:
                raise InventoryError(
                    f"INSTALL_ROOT components must be real directories ({type(exc).__name__})") from None
            previous_fd = fd
            fd = next_fd
            try:
                os.close(previous_fd)
            except BaseException:
                # The close result is ambiguous. Try to release the newly
                # opened descriptor too, while preserving the original error.
                try:
                    os.close(fd)
                except OSError:
                    pass
                fd = -1
                raise
        return root, fd, os.fstat(fd)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        raise


def _metadata(info: os.stat_result) -> dict[str, object]:
    return {
        "type": ("directory" if stat.S_ISDIR(info.st_mode) else
                 "regular" if stat.S_ISREG(info.st_mode) else
                 "symlink" if stat.S_ISLNK(info.st_mode) else "other"),
        "owner_uid": info.st_uid,
        "owner_matches_current_uid": info.st_uid == os.geteuid(),
        "mode": f"{stat.S_IMODE(info.st_mode):04o}",
        "size_bytes": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "nlink": info.st_nlink,
    }


def _entries(directory_fd: int, limit: int) -> tuple[list[_EntrySnapshot], bool]:
    scan_fd = None
    try:
        scan_fd = os.dup(directory_fd)
        # scandir(fd) owns its iterator, but the caller retains responsibility
        # for closing the supplied descriptor.
        with os.scandir(scan_fd) as scan:
            entries = list(itertools.islice(scan, limit + 1))
            sampled = []
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                    error = None
                except OSError as exc:
                    info = None
                    error = type(exc).__name__
                sampled.append(_EntrySnapshot(entry.name, info, error))
    except OSError as exc:
        raise InventoryError(f"directory scan unavailable ({type(exc).__name__})") from None
    finally:
        if scan_fd is not None:
            os.close(scan_fd)
    return sampled[:limit], len(sampled) > limit


def _open_child_directory(parent_fd: int, name: str,
                          info: os.stat_result | None) -> tuple[int | None, str]:
    if info is None:
        return None, "missing"
    if stat.S_ISLNK(info.st_mode):
        return None, "symlink"
    if not stat.S_ISDIR(info.st_mode):
        return None, "wrong_type"
    fd = None
    try:
        try:
            fd = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        except OSError as exc:
            state = "symlink" if exc.errno == errno.ELOOP else "unavailable"
            return None, state
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            return None, "changed_during_scan"
        owned_fd = fd
        fd = None  # Transfer ownership to the caller only after validation.
        return owned_fd, "directory"
    finally:
        if fd is not None:
            os.close(fd)


def _pointer(root_fd: int, name: str, releases_fd: int | None) -> dict[str, object]:
    info = _stat_at(root_fd, name, missing_ok=True)
    if info is None:
        return {"name": name, "state": "missing"}
    metadata = _metadata(info)
    if not stat.S_ISLNK(info.st_mode):
        return {"name": name, "state": "unsafe_type", "metadata": metadata}
    try:
        target = os.readlink(name, dir_fd=root_fd)
    except OSError as exc:
        return {"name": name, "state": "unreadable", "error": type(exc).__name__}
    prefix = "releases/"
    release_id = target[len(prefix):] if target.startswith(prefix) else ""
    if (not RELEASE_ID_RE.fullmatch(release_id)
            or target != prefix + release_id):
        # Never echo an untrusted symlink target; it may name a path outside root.
        return {"name": name, "state": "unsafe_target", "target_omitted": True,
                "metadata": metadata}
    if releases_fd is None:
        return {"name": name, "state": "missing_or_unsafe_target",
                "release_id": release_id, "metadata": metadata}
    target_info = _stat_at(releases_fd, release_id, missing_ok=True)
    if (target_info is None or not stat.S_ISDIR(target_info.st_mode)
            or stat.S_ISLNK(target_info.st_mode)):
        return {"name": name, "state": "missing_or_unsafe_target",
                "release_id": release_id, "metadata": metadata}
    return {"name": name, "state": "valid", "release_id": release_id,
            "metadata": metadata}


def _manifest_metadata(manifests_fd: int, release_id: str) -> dict[str, object]:
    # release_id has already passed the strict canonical regex.
    info = _stat_at(manifests_fd, f"{release_id}{MANIFEST_SUFFIX}", missing_ok=True)
    if info is None:
        return {"state": "missing"}
    metadata = _metadata(info)
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1 or info.st_size > MAX_MANIFEST_BYTES):
        return {"state": "unsafe_metadata", "metadata": metadata}
    return {"state": "present_unverified", "metadata": metadata,
            "content_read": False}


def inventory_install_root(install_root: str | os.PathLike[str], *,
                           max_entries: int = DEFAULT_MAX_ENTRIES) -> dict[str, object]:
    """Inventory a caller-specified root without reading artifact contents."""
    if (type(max_entries) is not int or not 1 <= max_entries <= MAX_ENTRIES_LIMIT):
        raise InventoryError(f"max_entries must be between 1 and {MAX_ENTRIES_LIMIT}")
    root, root_fd, root_info = _open_explicit_root(install_root)
    try:
        return _inventory_open_root(root_fd, root_info, max_entries)
    finally:
        os.close(root_fd)


def _inventory_open_root(root_fd: int, root_info: os.stat_result,
                         max_entries: int) -> dict[str, object]:
    releases_info = _stat_at(root_fd, "releases", missing_ok=True)
    manifests_info = _stat_at(root_fd, "manifests", missing_ok=True)
    releases_fd = None
    manifests_fd = None
    try:
        releases_fd, releases_state = _open_child_directory(
            root_fd, "releases", releases_info)
        manifests_fd, manifests_state = _open_child_directory(
            root_fd, "manifests", manifests_info)
        return _inventory_collect(
            root_fd, root_info, max_entries,
            releases_info, releases_state, releases_fd,
            manifests_info, manifests_state, manifests_fd)
    finally:
        close_error = None
        for child_fd in (releases_fd, manifests_fd):
            if child_fd is None:
                continue
            try:
                os.close(child_fd)
            except BaseException as exc:
                if close_error is None:
                    close_error = exc
        if close_error is not None:
            raise close_error


def _inventory_collect(root_fd: int, root_info: os.stat_result, max_entries: int,
                       releases_info: os.stat_result | None, releases_state: str,
                       releases_fd: int | None,
                       manifests_info: os.stat_result | None, manifests_state: str,
                       manifests_fd: int | None) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "yuva-release-staging-inventory/v1",
        "install_root": "<explicit-root-redacted>",
        "root_metadata": _metadata(root_info),
        "active_installer_process": "unknown",
        "decision": "HOLD",
        "items": [],
        "pointers": [],
        "temporary_pointers": [],
        "unknown_entry_count": 0,
        "truncated": False,
    }
    root_metadata_trusted = (
        root_info.st_uid == os.geteuid()
        and stat.S_IMODE(root_info.st_mode) == 0o700)
    releases_metadata_trusted = (
        releases_state == "directory" and releases_info is not None
        and releases_info.st_uid == os.geteuid()
        and stat.S_IMODE(releases_info.st_mode) == 0o700)
    manifests_metadata_trusted = (
        manifests_state == "directory" and manifests_info is not None
        and manifests_info.st_uid == os.geteuid()
        and stat.S_IMODE(manifests_info.st_mode) == 0o700)
    report["root_metadata_matches_private_contract"] = root_metadata_trusted

    report["releases_directory"] = {
        "state": releases_state,
        "metadata_matches_private_contract": releases_metadata_trusted,
        **({"metadata": _metadata(releases_info)} if releases_info else {}),
    }
    report["manifests_directory"] = {
        "state": manifests_state,
        "metadata_matches_private_contract": manifests_metadata_trusted,
        **({"metadata": _metadata(manifests_info)} if manifests_info else {}),
    }

    lock_info = _stat_at(root_fd, ".installer.lock", missing_ok=True)
    report["installer_lock"] = (
        {"state": "missing", "process_state": "unknown"} if lock_info is None else
        {"state": "present_uninspected", "process_state": "unknown",
         "metadata": _metadata(lock_info)})

    pointers = [_pointer(root_fd, name, releases_fd)
                for name in ("current", "previous")]
    report["pointers"] = pointers
    referenced = {
        item["release_id"] for item in pointers
        if item.get("state") == "valid" and isinstance(item.get("release_id"), str)
    }

    root_entries, root_truncated = _entries(root_fd, max_entries)
    temporary_pointers = []
    unclassified_temps = 0
    for entry in root_entries:
        name = entry.name
        if not (name.startswith(".current.") or name.startswith(".previous.")):
            continue
        match = POINTER_TMP_RE.fullmatch(name)
        if match:
            if entry.info is None:
                temporary_pointers.append({
                    "kind": "temporary_pointer",
                    "metadata_error": entry.metadata_error or "OSError",
                    "decision": "HOLD",
                })
            else:
                temporary_pointers.append({
                    "kind": "temporary_pointer",
                    "pointer": "current" if name.startswith(".current.") else "previous",
                    "id": match.group(1),
                    "metadata": _metadata(entry.info), "decision": "HOLD",
                })
        else:
            unclassified_temps += 1
    report["temporary_pointers"] = temporary_pointers
    report["unclassified_temporary_pointer_count"] = unclassified_temps

    items: list[dict[str, object]] = []
    unknown_entries = 0
    releases_truncated = False
    if releases_fd is not None:
        release_entries, releases_truncated = _entries(releases_fd, max_entries)
        for entry in release_entries:
            name = entry.name
            staging_match = STAGING_ID_RE.fullmatch(name)
            if staging_match:
                info = entry.info
                if info is None:
                    items.append({"kind": "staging", "id": staging_match.group(1),
                                  "classification": "HOLD_UNKNOWN",
                                  "metadata_error": entry.metadata_error or "OSError",
                                  "decision": "HOLD"})
                    continue
                item = {
                    "kind": "staging", "id": staging_match.group(1),
                    "classification": "STAGING_STATE_UNKNOWN",
                    "metadata": _metadata(info),
                    "transaction_phase": "unknown",
                    "decision": "HOLD",
                }
                if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                        or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) not in (0o700, 0o555)
                        or not root_metadata_trusted or not releases_metadata_trusted):
                    item["classification"] = "HOLD_UNKNOWN"
                items.append(item)
                continue

            if RELEASE_ID_RE.fullmatch(name):
                info = entry.info
                if info is None:
                    items.append({"kind": "release", "release_id": name,
                                  "classification": "HOLD_UNKNOWN",
                                  "metadata_error": entry.metadata_error or "OSError",
                                  "decision": "HOLD"})
                    continue
                if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)):
                    items.append({"kind": "release", "release_id": name,
                                  "classification": "HOLD_UNKNOWN",
                                  "metadata": _metadata(info), "decision": "HOLD"})
                    continue
                receipt = (_manifest_metadata(manifests_fd, name)
                           if manifests_fd is not None and manifests_metadata_trusted else
                           {"state": "manifest_directory_unavailable"})
                release_metadata_trusted = (
                    info.st_uid == os.geteuid()
                    and stat.S_IMODE(info.st_mode) == 0o555
                    and root_metadata_trusted and releases_metadata_trusted)
                if not release_metadata_trusted:
                    classification = "HOLD_UNKNOWN"
                elif receipt["state"] == "missing":
                    classification = "PUBLISHED_RECEIPT_INCOMPLETE"
                elif receipt["state"] == "present_unverified":
                    classification = ("POINTER_REFERENCED" if name in referenced
                                      else "PUBLISHED_INACTIVE")
                else:
                    classification = "HOLD_UNKNOWN"
                items.append({
                    "kind": "release", "release_id": name,
                    "classification": classification,
                    "metadata": _metadata(info), "manifest_receipt": receipt,
                    "metadata_matches_release_contract": release_metadata_trusted,
                    "pointer_referenced": name in referenced,
                    "process_state": "unknown", "decision": "HOLD",
                })
                continue
            unknown_entries += 1

    report["items"] = items
    report["unknown_entry_count"] = unknown_entries
    report["truncated"] = bool(root_truncated or releases_truncated)
    report["inventory_limit"] = max_entries
    report["decision_reason"] = (
        "artifact ownership or installer process state is unverified; no action authorized")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only bounded inventory under an explicit INSTALL_ROOT")
    parser.add_argument("--install-root", required=True,
                        help="existing absolute real install root; never inferred from environment")
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES,
                        help=f"maximum direct entries per directory (1-{MAX_ENTRIES_LIMIT})")
    args = parser.parse_args(argv)
    try:
        report = inventory_install_root(args.install_root,
                                        max_entries=args.max_entries)
    except (InventoryError, OSError, ValueError) as exc:
        error = str(exc) if isinstance(exc, InventoryError) else type(exc).__name__
        print(json.dumps({"schema": "yuva-release-staging-inventory/v1",
                          "decision": "HOLD", "error": error},
                         ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
