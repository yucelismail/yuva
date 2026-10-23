#!/usr/bin/env python3
"""Install and roll back verified Yuva releases under an explicit root.

This tool never moves or writes YUVA_DIR. It only changes an explicitly
provided INSTALL_ROOT and requires an external manifest SHA-256 pin.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import uuid

import release_manifest


RELEASE_ID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})-[0-9a-f]{64}$")
MANIFEST_DIR = "manifests"
RELEASE_DIR = "releases"
LOCK_NAME = ".installer.lock"
MANIFEST_SUFFIX = ".manifest.json"
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_TASK_BYTES = 16 * 1024 * 1024
MAX_MESSAGE_BYTES = 64 * 1024 * 1024
MAX_SCREEN_TOTAL_BYTES = 64 * 1024 * 1024
MAX_SCREEN_FILE_BYTES = 16 * 1024 * 1024
MAX_JSONL_RECORD_BYTES = 2 * 1024 * 1024
SUPPORTED_TASK_STATUSES = frozenset({
    "pending", "assigned", "pending_gorevli_review", "pending_verification",
    "pending_revision", "verified", "dropped",
})
SUPPORTED_MESSAGE_SCHEMAS = frozenset({1, 2})


class InstallError(ValueError):
    pass


class CommitUnknown(InstallError):
    """Pointer replacement may have committed; inspect state before retry."""


class CommitCleanupError(InstallError):
    """Commit completed, but descriptor cleanup failed; do not retry blindly."""


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _real_existing_dir(path: Path, label: str) -> Path:
    path = Path(path).expanduser()
    if not path.is_absolute():
        raise InstallError(f"{label} must be an absolute path")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except OSError as e:
            raise InstallError(f"{label} path unavailable ({type(e).__name__})") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise InstallError(f"{label} must use real directories without symlink components")
    return path.resolve(strict=True)


def _ensure_install_dir(path: Path, *, private: bool) -> Path:
    path = Path(path).expanduser()
    if not path.is_absolute():
        raise InstallError("INSTALL_ROOT must be an absolute path")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            except OSError as e:
                raise InstallError(f"INSTALL_ROOT directory creation failed ({type(e).__name__})") from None
            info = current.lstat()
        except OSError as e:
            raise InstallError(f"INSTALL_ROOT path unavailable ({type(e).__name__})") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise InstallError("INSTALL_ROOT must use real directories without symlink components")
        if current == path:
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise InstallError("INSTALL_ROOT must belong to this user with mode 0700")
        elif info.st_mode & 0o022:
            sticky_root_tmp = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if not sticky_root_tmp:
                raise InstallError("INSTALL_ROOT parent is group/world writable")
    return path.resolve(strict=True)


def _private_child(root: Path, name: str, *, create: bool) -> Path:
    path = root / name
    try:
        info = path.lstat()
    except FileNotFoundError:
        if not create:
            raise InstallError(f"required install directory missing: {name}") from None
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as e:
            raise InstallError(f"install directory creation failed ({type(e).__name__})") from None
        info = path.lstat()
    except OSError as e:
        raise InstallError(f"install directory unavailable ({type(e).__name__})") from None
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise InstallError(f"{name} must be a real owner-only directory with mode 0700")
    return path


@contextmanager
def _install_lock(root: Path):
    path = root / LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as e:
        raise InstallError(f"installer lock unavailable ({type(e).__name__})") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise InstallError("installer lock is not a private regular file")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    except BaseException:
        # Preserve the operation's primary error if releasing the lock also
        # reports an error. The commit/commit_unknown result is more useful.
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    else:
        # Normal exit means the install/rollback body completed. Do not report
        # a generic failure that could prompt a caller to repeat a committed
        # pointer transition.
        try:
            os.close(fd)
        except OSError as e:
            raise CommitCleanupError(
                "commit_complete: installer operation finished, but lock "
                f"descriptor close failed ({type(e).__name__}); inspect exact "
                "current/previous targets before any retry") from None


def _check_roots(install_root: Path, data_root: Path, *, create: bool) -> tuple[Path, Path]:
    root = (_ensure_install_dir(install_root, private=True) if create
            else _real_existing_dir(install_root, "INSTALL_ROOT"))
    data = _real_existing_dir(data_root, "YUVA_DIR")
    if _path_is_within(root, data) or _path_is_within(data, root):
        raise InstallError("INSTALL_ROOT and YUVA_DIR must be separate, non-nested roots")
    return root, data


def _pointer_release_id(root: Path, name: str, *, allow_missing: bool) -> str | None:
    path = root / name
    try:
        info = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise InstallError(f"{name} pointer is missing") from None
    except OSError as e:
        raise InstallError(f"{name} pointer unavailable ({type(e).__name__})") from None
    if not stat.S_ISLNK(info.st_mode):
        raise InstallError(f"{name} exists but is not a symlink; no change made")
    target = os.readlink(path)
    prefix = f"{RELEASE_DIR}/"
    release_id = target[len(prefix):] if target.startswith(prefix) else ""
    if not RELEASE_ID_RE.fullmatch(release_id) or target != prefix + release_id:
        raise InstallError(f"{name} target is not a canonical release path")
    return release_id


def _preflight_pointer(root: Path, name: str) -> None:
    """Reject existing pointer conflicts before creating install children/lock."""
    release_id = _pointer_release_id(root, name, allow_missing=True)
    if release_id is None:
        return
    releases = root / RELEASE_DIR
    try:
        releases_info = releases.lstat()
    except OSError:
        raise InstallError(f"{name} points to a missing release") from None
    if not stat.S_ISDIR(releases_info.st_mode) or stat.S_ISLNK(releases_info.st_mode):
        raise InstallError(f"{name} target is not a release directory")
    try:
        release_info = (releases / release_id).lstat()
    except OSError:
        raise InstallError(f"{name} points to a missing release") from None
    if not stat.S_ISDIR(release_info.st_mode) or stat.S_ISLNK(release_info.st_mode):
        raise InstallError(f"{name} target is not a release directory")


def _read_pointer(root: Path, name: str, *, allow_missing: bool) -> str | None:
    release_id = _pointer_release_id(root, name, allow_missing=allow_missing)
    if release_id is None:
        return None
    release = root / RELEASE_DIR / release_id
    try:
        release_info = release.lstat()
    except OSError:
        raise InstallError(f"{name} points to a missing release") from None
    if not stat.S_ISDIR(release_info.st_mode) or stat.S_ISLNK(release_info.st_mode):
        raise InstallError(f"{name} target is not a release directory")
    return release_id


def _atomic_pointer(root: Path, name: str, release_id: str) -> None:
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise InstallError("invalid full release ID")
    temp = root / f".{name}.{uuid.uuid4().hex}.tmp"
    try:
        os.symlink(f"{RELEASE_DIR}/{release_id}", temp)
        root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        switched = False
        try:
            try:
                os.fsync(root_fd)
            except OSError as e:
                raise InstallError(
                    f"{name} pointer was not switched; parent pre-sync failed "
                    f"({type(e).__name__})") from None
            try:
                os.replace(temp, root / name)
            except OSError as e:
                raise CommitUnknown(
                    f"commit_unknown: {name} pointer replace outcome is uncertain "
                    f"({type(e).__name__}); inspect its exact target before retry") from None
            switched = True
            try:
                os.fsync(root_fd)
            except OSError as e:
                raise CommitUnknown(
                    f"commit_unknown: {name} pointer was replaced but directory "
                    f"durability is unknown ({type(e).__name__}); inspect its exact "
                    "target before retry") from None
        except BaseException:
            # Keep the operation's established InstallError/CommitUnknown if
            # descriptor cleanup also fails; never reinterpret it as a setup
            # failure.
            try:
                os.close(root_fd)
            except OSError:
                pass
            raise
        else:
            try:
                os.close(root_fd)
            except OSError as e:
                if switched:
                    raise CommitCleanupError(
                        f"commit_complete: {name} pointer was replaced and its "
                        "directory fsync succeeded, but descriptor close failed "
                        f"({type(e).__name__}); inspect its exact target before "
                        "any retry") from None
                raise
    except (InstallError, CommitUnknown):
        try:
            temp.unlink()
        except OSError:
            pass
        raise
    except OSError as e:
        try:
            temp.unlink()
        except OSError:
            pass
        raise InstallError(
            f"{name} pointer setup failed before switch ({type(e).__name__})") from None


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish a release directory without replacing any target."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError):
        raise InstallError("atomic no-replace directory rename is unavailable") from None
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p,
                          ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise InstallError("release ID already exists; existing release is never overwritten")
        raise OSError(error, os.strerror(error), os.fspath(destination))


def _read_manifest(root: Path, release_id: str) -> bytes:
    if not RELEASE_ID_RE.fullmatch(release_id):
        raise InstallError("release ID must contain full commit and payload digests")
    path = root / MANIFEST_DIR / f"{release_id}{MANIFEST_SUFFIX}"
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1 or info.st_size > 4 * 1024 * 1024):
            raise InstallError("stored release manifest is not a private regular file")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            return stream.read(4 * 1024 * 1024 + 1)
    except InstallError:
        raise
    except OSError as e:
        raise InstallError(f"stored release manifest unavailable ({type(e).__name__})") from None
    finally:
        if fd is not None:
            os.close(fd)


def _manifest_data_contract(raw: bytes, expected_release_id: str) -> str:
    if len(raw) > 4 * 1024 * 1024:
        raise InstallError("stored release manifest exceeds 4 MiB limit")
    try:
        manifest = json.loads(raw.decode("utf-8"))
        if release_manifest._canonical_json(manifest) != raw:
            raise release_manifest.ManifestError("manifest is not canonical JSON")
        manifest = release_manifest._validate_manifest_shape(manifest)
    except (release_manifest.ManifestError, UnicodeError, ValueError, TypeError,
            RecursionError) as e:
        raise InstallError(
            f"rollback manifest contract is invalid ({type(e).__name__})") from None
    if manifest.get("release_id") != expected_release_id:
        raise InstallError("rollback manifest release ID does not match its pointer")
    contract = manifest["data_contract"]["schema_compatibility"]
    if contract != release_manifest.DATA_CONTRACT:
        raise InstallError("rollback manifest uses an unsupported data contract")
    return contract


def _read_bounded_regular(path: Path, label: str, limit: int, *, required: bool) -> bytes | None:
    try:
        before = path.lstat()
    except FileNotFoundError:
        if required:
            raise InstallError(f"YUVA_DIR compatibility check missing {label}") from None
        return None
    except OSError as e:
        raise InstallError(
            f"YUVA_DIR compatibility check cannot inspect {label} ({type(e).__name__})") from None
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise InstallError(f"YUVA_DIR compatibility check rejects {label} type/size")
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as e:
        raise InstallError(
            f"YUVA_DIR compatibility check cannot read {label} ({type(e).__name__})") from None
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode)
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
                or opened.st_size > limit):
            raise InstallError(f"YUVA_DIR compatibility check changed {label}")
        chunks = []
        total = 0
        while True:
            block = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > limit:
                raise InstallError(f"YUVA_DIR compatibility check exceeds {label} limit")
        after = os.fstat(fd)
        current = path.lstat()
        if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns,
             opened.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                 after.st_ctime_ns)
                or (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)
                or total != after.st_size):
            raise InstallError(f"YUVA_DIR compatibility check found changing {label}")
        return b"".join(chunks)
    except OSError as e:
        raise InstallError(
            f"YUVA_DIR compatibility check cannot read {label} ({type(e).__name__})") from None
    finally:
        os.close(fd)


def _json_object(raw: bytes, label: str) -> dict:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("non-finite JSON number")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as e:
        raise InstallError(f"YUVA_DIR compatibility check rejects {label} JSON") from None
    if not isinstance(value, dict):
        raise InstallError(f"YUVA_DIR compatibility check rejects {label} root type")
    return value


def _root_schema(value: dict, label: str) -> str:
    version = value.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise InstallError(f"YUVA_DIR compatibility check rejects {label} schema")
    return "legacy" if "schema_version" not in value else "v1"


def _validate_actual_data_root(data_root: Path) -> dict[str, str]:
    """Read-only, bounded acceptance for the v1 rollback data contract."""
    state_bytes = _read_bounded_regular(
        data_root / "durum.json", "durum.json", MAX_STATE_BYTES, required=True)
    task_bytes = _read_bounded_regular(
        data_root / "gorevler.json", "gorevler.json", MAX_TASK_BYTES, required=True)
    state = _json_object(state_bytes, "durum.json")
    tasks = _json_object(task_bytes, "gorevler.json")
    state_class = _root_schema(state, "durum.json")
    task_class = _root_schema(tasks, "gorevler.json")
    users = state.get("kullanicilar")
    revision = state.get("rev", 0)
    if (not isinstance(users, dict)
            or any(not isinstance(key, str) or not isinstance(row, dict)
                   for key, row in users.items())
            or type(revision) is not int or revision < 0):
        raise InstallError("YUVA_DIR compatibility check rejects durum.json shape")
    next_id = tasks.get("siradaki", 1)
    task_rows = tasks.get("gorevler", [])
    if (type(next_id) is not int or next_id < 1 or not isinstance(task_rows, list)):
        raise InstallError("YUVA_DIR compatibility check rejects gorevler.json shape")
    task_ids = set()
    for row in task_rows:
        if not isinstance(row, dict):
            raise InstallError("YUVA_DIR compatibility check rejects task row shape")
        task_id = row.get("id")
        if type(task_id) is not int or task_id < 1 or task_id in task_ids:
            raise InstallError("YUVA_DIR compatibility check rejects task ID")
        task_ids.add(task_id)
        if any(not isinstance(row.get(key), str)
               for key in ("baslik", "kimden", "durum")):
            raise InstallError("YUVA_DIR compatibility check rejects task fields")
        if row["durum"] not in SUPPORTED_TASK_STATUSES:
            raise InstallError("YUVA_DIR compatibility check rejects task status")
        parent = row.get("ust_gorev_id")
        if parent is not None and (type(parent) is not int or parent < 1):
            raise InstallError("YUVA_DIR compatibility check rejects task parent ID")
        if not isinstance(row.get("gecmis", []), list):
            raise InstallError("YUVA_DIR compatibility check rejects task history")

    message_bytes = _read_bounded_regular(
        data_root / "mesaj.jsonl", "mesaj.jsonl", MAX_MESSAGE_BYTES, required=False)
    if message_bytes is None:
        message_class = "absent"
    else:
        for line_number, line in enumerate(message_bytes.splitlines(), 1):
            if not line or len(line) > MAX_JSONL_RECORD_BYTES:
                raise InstallError("YUVA_DIR compatibility check rejects mesaj.jsonl record")
            message = _json_object(line, "mesaj.jsonl record")
            version = message.get("schema_version", 1)
            if type(version) is not int or version not in SUPPORTED_MESSAGE_SCHEMAS:
                raise InstallError(
                    f"YUVA_DIR compatibility check rejects mesaj.jsonl schema at line {line_number}")
        message_class = "legacy/v1/v2"

    screen_class = "absent"
    screen_root = data_root / "ekran"
    try:
        screen_info = screen_root.lstat()
    except FileNotFoundError:
        screen_info = None
    except OSError as e:
        raise InstallError(
            f"YUVA_DIR compatibility check cannot inspect ekran ({type(e).__name__})") from None
    if screen_info is not None:
        if not stat.S_ISDIR(screen_info.st_mode):
            raise InstallError("YUVA_DIR compatibility check rejects ekran directory type")
        total_screen_bytes = 0
        for directory, dirs, files in os.walk(screen_root, topdown=True, followlinks=False):
            base = Path(directory)
            dirs.sort()
            files.sort()
            for name in dirs:
                if (base / name).is_symlink():
                    raise InstallError("YUVA_DIR compatibility check rejects ekran symlink")
            for name in files:
                path = base / name
                try:
                    info = path.lstat()
                except OSError as e:
                    raise InstallError(
                        f"YUVA_DIR compatibility check cannot inspect ekran entry "
                        f"({type(e).__name__})") from None
                if not stat.S_ISREG(info.st_mode):
                    raise InstallError("YUVA_DIR compatibility check rejects ekran entry type")
                if path.suffix != ".jsonl":
                    continue
                raw = _read_bounded_regular(
                    path, "ekran JSONL", MAX_SCREEN_FILE_BYTES, required=True)
                total_screen_bytes += len(raw)
                if total_screen_bytes > MAX_SCREEN_TOTAL_BYTES:
                    raise InstallError("YUVA_DIR compatibility check exceeds ekran limit")
                for line_number, line in enumerate(raw.splitlines(), 1):
                    if not line or len(line) > MAX_JSONL_RECORD_BYTES:
                        raise InstallError("YUVA_DIR compatibility check rejects ekran record")
                    record = _json_object(line, "ekran JSONL record")
                    if "schema_version" in record:
                        raise InstallError(
                            "YUVA_DIR compatibility check rejects versioned ekran record")
        screen_class = "unversioned-json-object"
    return {"durum": state_class, "gorevler": task_class,
            "mesajlar": message_class, "ekranlar": screen_class}


def _verify(payload: Path, raw_manifest: bytes, source_repo: Path,
            trusted_manifest_sha256: str) -> tuple[str, dict[str, object]]:
    if len(raw_manifest) > 4 * 1024 * 1024:
        raise InstallError("manifest exceeds 4 MiB limit")
    try:
        result = release_manifest.verify_manifest(
            payload, raw_manifest, source_repo=source_repo,
            trusted_manifest_sha256=trusted_manifest_sha256)
        manifest = release_manifest._validate_manifest_shape(
            json.loads(raw_manifest.decode("utf-8")))
    except (release_manifest.ManifestError, OSError, ValueError, TypeError,
            UnicodeError, RecursionError) as e:
        raise InstallError(f"release verification failed ({type(e).__name__}): {e}") from None
    release_id = manifest.get("release_id")
    if not isinstance(release_id, str) or not RELEASE_ID_RE.fullmatch(release_id):
        raise InstallError("manifest release ID is not canonical and complete")
    if result.get("verified_release") is not True:
        raise InstallError("release is dirty, unpinned, or does not exactly match its source")
    return release_id, result


def _write_exclusive(path: Path, data: bytes, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def _freeze_directories(root: Path) -> None:
    directories = [root]
    for path, dirs, _files in os.walk(root, topdown=True, followlinks=False):
        base = Path(path)
        directories.extend(base / name for name in dirs
                           if not (base / name).is_symlink())
    for directory in reversed(directories):
        directory.chmod(0o555)


def install_release(*, install_root: Path, data_root: Path, payload: Path,
                    manifest_bytes: bytes, source_repo: Path,
                    trusted_manifest_sha256: str) -> dict[str, object]:
    payload = Path(payload).expanduser().resolve(strict=True)
    source_repo = Path(source_repo).expanduser().resolve(strict=True)
    release_id, first = _verify(payload, manifest_bytes, source_repo,
                                trusted_manifest_sha256)
    requested_root = Path(install_root).expanduser()
    if not requested_root.is_absolute():
        raise InstallError("INSTALL_ROOT must be an absolute path")
    root_candidate = requested_root.resolve(strict=False)
    data_candidate = _real_existing_dir(Path(data_root), "YUVA_DIR")
    for external in (payload, source_repo, data_candidate):
        if _path_is_within(root_candidate, external) or _path_is_within(external, root_candidate):
            raise InstallError("INSTALL_ROOT, payload, source repository, and YUVA_DIR must be separate")
    root, _data = _check_roots(Path(install_root), Path(data_root), create=True)
    if _path_is_within(payload, root) or _path_is_within(root, payload):
        raise InstallError("scratch payload and INSTALL_ROOT must be separate")
    if _path_is_within(source_repo, root) or _path_is_within(root, source_repo):
        raise InstallError("source repository and INSTALL_ROOT must be separate")
    # A pre-existing file or unsafe link at either pointer name is a conflict,
    # not a reason to create releases/manifests or a lock beside it.
    _preflight_pointer(root, "current")
    _preflight_pointer(root, "previous")
    releases = _private_child(root, RELEASE_DIR, create=True)
    manifests = _private_child(root, MANIFEST_DIR, create=True)
    with _install_lock(root):
        current_id = _read_pointer(root, "current", allow_missing=True)
        _read_pointer(root, "previous", allow_missing=True)
        final = releases / release_id
        manifest_path = manifests / f"{release_id}{MANIFEST_SUFFIX}"
        if final.exists() or final.is_symlink() or manifest_path.exists() or manifest_path.is_symlink():
            raise InstallError("release ID already exists; existing release is never overwritten")
        staging = releases / f".staging-{uuid.uuid4().hex}"
        try:
            # Exclusive creation establishes ownership before any cleanup path
            # can remove this name. A pre-existing staging entry is preserved.
            staging.mkdir(mode=0o700)
        except FileExistsError:
            raise InstallError("staging path already exists; no change made") from None
        moved = False
        try:
            shutil.copytree(payload, staging, symlinks=True,
                            copy_function=shutil.copy2, dirs_exist_ok=True)
            _, staged = _verify(staging, manifest_bytes, source_repo,
                                trusted_manifest_sha256)
            _freeze_directories(staging)
            _rename_noreplace(staging, final)
            moved = True
            releases_fd = os.open(releases, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(releases_fd)
            finally:
                os.close(releases_fd)
            _write_exclusive(manifest_path, manifest_bytes)
            manifests_fd = os.open(manifests, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(manifests_fd)
            finally:
                os.close(manifests_fd)
            if current_id:
                _atomic_pointer(root, "previous", current_id)
            _atomic_pointer(root, "current", release_id)
        except Exception:
            if not moved:
                shutil.rmtree(staging, ignore_errors=True)
            raise
    return {"release_id": release_id, "previous_release_id": current_id,
            "current_release_id": release_id, "payload_verified": True,
            "source_verified": first["source_match"] and staged["source_match"],
            "manifest_sha256": first["manifest_sha256"], "data_root_changed": False}


def rollback_release(*, install_root: Path, data_root: Path, source_repo: Path,
                     trusted_manifest_sha256: str,
                     release_id: str | None = None) -> dict[str, object]:
    root, data = _check_roots(Path(install_root), Path(data_root), create=False)
    source_repo = Path(source_repo).expanduser().resolve(strict=True)
    if _path_is_within(source_repo, root) or _path_is_within(root, source_repo):
        raise InstallError("source repository and INSTALL_ROOT must be separate")
    releases = _private_child(root, RELEASE_DIR, create=False)
    manifests = _private_child(root, MANIFEST_DIR, create=False)
    del releases, manifests
    with _install_lock(root):
        current_id = _read_pointer(root, "current", allow_missing=False)
        target_id = release_id or _read_pointer(root, "previous", allow_missing=False)
        if target_id == current_id:
            raise InstallError("rollback target is already current")
        if not target_id or not RELEASE_ID_RE.fullmatch(target_id):
            raise InstallError("rollback requires a full release ID")
        target = root / RELEASE_DIR / target_id
        current_manifest = _read_manifest(root, current_id)
        try:
            current_payload_check = release_manifest.verify_manifest(
                root / RELEASE_DIR / current_id, current_manifest)
        except (release_manifest.ManifestError, OSError, ValueError, TypeError,
                UnicodeError, RecursionError) as e:
            raise InstallError(
                f"current release manifest/payload check failed ({type(e).__name__})") from None
        if current_payload_check.get("payload_match") is not True:
            raise InstallError("current release manifest does not match its payload")
        raw_manifest = _read_manifest(root, target_id)
        _, verified = _verify(target, raw_manifest, source_repo,
                              trusted_manifest_sha256)
        current_contract = _manifest_data_contract(current_manifest, current_id)
        target_contract = _manifest_data_contract(raw_manifest, target_id)
        if current_contract != target_contract:
            raise InstallError("current and rollback target data contracts differ")
        data_schema = _validate_actual_data_root(data)
        _atomic_pointer(root, "previous", current_id)
        _atomic_pointer(root, "current", target_id)
    return {"current_release_id": target_id, "previous_release_id": current_id,
            "payload_verified": True, "source_verified": verified["source_match"],
            "manifest_sha256": verified["manifest_sha256"], "data_root_changed": False,
            "data_contract": target_contract, "data_schema": data_schema}


def _read_manifest_arg(path: Path) -> bytes:
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
            raise InstallError("manifest must be a regular file no larger than 4 MiB")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            return stream.read(4 * 1024 * 1024 + 1)
    except InstallError:
        raise
    except OSError as e:
        raise InstallError(f"manifest unavailable ({type(e).__name__})") from None
    finally:
        if fd is not None:
            os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install/rollback verified Yuva releases")
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install", help="verify and atomically install a release")
    install.add_argument("--install-root", type=Path, required=True)
    install.add_argument("--data-root", type=Path, required=True)
    install.add_argument("--payload", type=Path, required=True)
    install.add_argument("--manifest", type=Path, required=True)
    install.add_argument("--source-repo", type=Path, required=True)
    install.add_argument("--trusted-manifest-sha256", required=True)
    rollback = sub.add_parser("rollback", help="atomically switch to a verified prior release")
    rollback.add_argument("--install-root", type=Path, required=True)
    rollback.add_argument("--data-root", type=Path, required=True)
    rollback.add_argument("--source-repo", type=Path, required=True,
                          help="clean checkout at the rollback release commit")
    rollback.add_argument("--trusted-manifest-sha256", required=True)
    rollback.add_argument("--release-id", help="full ID; defaults to previous pointer")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            result = install_release(
                install_root=args.install_root, data_root=args.data_root,
                payload=args.payload, manifest_bytes=_read_manifest_arg(args.manifest),
                source_repo=args.source_repo,
                trusted_manifest_sha256=args.trusted_manifest_sha256)
        else:
            result = rollback_release(
                install_root=args.install_root, data_root=args.data_root,
                source_repo=args.source_repo,
                trusted_manifest_sha256=args.trusted_manifest_sha256,
                release_id=args.release_id)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (InstallError, OSError, ValueError) as e:
        print(f"release installer error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
