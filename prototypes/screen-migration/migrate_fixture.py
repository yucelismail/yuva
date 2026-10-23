"""Fixture-only, one-file screen JSONL redaction migration prototype.

The CLI refuses roots outside the system temporary directory and requires an
explicit marker. It never discovers a Yuva data root or backup by itself.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
import secrets
import stat
import tempfile
import time
from pathlib import Path


FIXTURE_MARKER = ".yuva-screen-migration-fixture"
FIXTURE_MARKER_VALUE = b"yuva-screen-migration-fixture-v1\n"
LOCK_NAME = ".kilit"
SCREEN_DIR = "ekran"
MAX_FILE_BYTES = 64 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 5.0


class MigrationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _redactor():
    module_path = Path(__file__).resolve().parents[2] / "yuva_screen_redaction.py"
    spec = importlib.util.spec_from_file_location(
        "yuva_screen_migration_redaction", module_path)
    if spec is None or spec.loader is None:
        raise MigrationError("redactor_unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        raise MigrationError("redactor_unavailable") from None
    return module


def _safe_dir(fd: int, *, exact_mode: int | None = None) -> os.stat_result:
    info = os.fstat(fd)
    mode = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or mode & 0o077 or (exact_mode is not None and mode != exact_mode)):
        raise MigrationError("unsafe_directory")
    return info


def _open_fixture(root: str | os.PathLike[str]) -> tuple[int, int]:
    raw = Path(root)
    try:
        if raw.is_symlink():
            raise MigrationError("fixture_root_symlink")
        resolved = raw.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        if (resolved == temp_root
                or os.path.commonpath((str(temp_root), str(resolved))) != str(temp_root)):
            raise MigrationError("fixture_root_outside_temp")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        root_fd = os.open(resolved, flags)
    except MigrationError:
        raise
    except Exception:
        raise MigrationError("fixture_root_unavailable") from None

    try:
        _safe_dir(root_fd)
        marker_fd = os.open(
            FIXTURE_MARKER,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_fd)
        try:
            marker_info = os.fstat(marker_fd)
            if (not stat.S_ISREG(marker_info.st_mode)
                    or marker_info.st_uid != os.geteuid()
                    or stat.S_IMODE(marker_info.st_mode) & 0o077
                    or marker_info.st_nlink != 1
                    or os.read(marker_fd, len(FIXTURE_MARKER_VALUE) + 1)
                    != FIXTURE_MARKER_VALUE):
                raise MigrationError("fixture_marker_invalid")
        finally:
            os.close(marker_fd)

        screen_fd = os.open(
            SCREEN_DIR,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=root_fd)
        try:
            _safe_dir(screen_fd)
        except Exception:
            os.close(screen_fd)
            raise
        return root_fd, screen_fd
    except MigrationError:
        os.close(root_fd)
        raise
    except Exception:
        os.close(root_fd)
        raise MigrationError("fixture_layout_invalid") from None


@contextmanager
def _lock(root_fd: int, timeout: float):
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        created = False
        try:
            fd = os.open(LOCK_NAME, flags, 0o600, dir_fd=root_fd)
            created = True
        except FileExistsError:
            fd = os.open(
                LOCK_NAME,
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0), dir_fd=root_fd)
        if created:
            os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise MigrationError("unsafe_lock")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise MigrationError("lock_timeout")
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
        current = os.stat(LOCK_NAME, dir_fd=root_fd, follow_symlinks=False)
        locked = os.fstat(fd)
        if ((current.st_dev, current.st_ino) != (locked.st_dev, locked.st_ino)
                or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o600
                or current.st_nlink != 1):
            raise MigrationError("lock_path_changed")
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        if "fd" in locals():
            os.close(fd)


class _DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _parse_and_redact(raw: bytes, redactor) -> tuple[bytes, int, int]:
    if not raw:
        return raw, 0, 0
    if not raw.endswith(b"\n"):
        raise MigrationError("unterminated_record")
    output = []
    rows = redacted_fields = 0
    for line in raw.splitlines(keepends=True):
        if line.endswith(b"\r\n"):
            payload, ending = line[:-2], b"\r\n"
        elif line.endswith(b"\n"):
            payload, ending = line[:-1], b"\n"
        else:
            raise MigrationError("invalid_line_ending")
        if not payload:
            raise MigrationError("empty_record")
        try:
            record = json.loads(payload.decode("utf-8", errors="strict"),
                                object_pairs_hook=_object_without_duplicates)
            clean = redactor.redact_screen_record(record)
            encoded = (json.dumps(clean, ensure_ascii=False) + "\n").encode(
                "utf-8", errors="strict")
        except Exception:
            raise MigrationError("record_rejected") from None
        rows += 1
        redacted_fields += int(clean["ad"] != record["ad"])
        redacted_fields += int(clean["satir"] != record["satir"])
        output.append(encoded[:-1] + ending)
    return b"".join(output), rows, redacted_fields


def _read_full(fd: int, info: os.stat_result) -> bytes:
    if info.st_size > MAX_FILE_BYTES:
        raise MigrationError("file_too_large")
    chunks = []
    total = 0
    while True:
        try:
            chunk = os.read(fd, min(1024 * 1024, MAX_FILE_BYTES + 1 - total))
        except OSError:
            raise MigrationError("read_failed") from None
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise MigrationError("file_too_large")
    after = os.fstat(fd)
    if (total != info.st_size or after.st_size != info.st_size
            or after.st_mtime_ns != info.st_mtime_ns
            or (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino)):
        raise MigrationError("source_changed_during_read")
    return b"".join(chunks)


def _source_file(screen_fd: int, name: str) -> tuple[int, os.stat_result]:
    if (not isinstance(name, str) or name in ("", ".", "..")
            or Path(name).name != name or not name.endswith(".jsonl")
            or "/" in name or "\\" in name):
        raise MigrationError("invalid_file_name")
    try:
        entry = os.stat(name, dir_fd=screen_fd, follow_symlinks=False)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.geteuid()
                or entry.st_nlink != 1 or stat.S_IMODE(entry.st_mode) & 0o077
                or stat.S_IMODE(entry.st_mode) & 0o7000
                or entry.st_size > MAX_FILE_BYTES):
            raise MigrationError("unsafe_source_file")
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0), dir_fd=screen_fd)
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino)):
            os.close(fd)
            raise MigrationError("source_changed_before_open")
        return fd, opened
    except MigrationError:
        raise
    except Exception:
        raise MigrationError("source_unavailable") from None


def _xattrs(fd: int) -> dict[str, bytes]:
    try:
        names = os.listxattr(fd)
        return {name: os.getxattr(fd, name) for name in names}
    except Exception:
        raise MigrationError("metadata_read_failed") from None


def _write_temp(screen_fd: int, content: bytes, source_info: os.stat_result,
                xattrs: dict[str, bytes]) -> str:
    for _ in range(8):
        name = f".screen-migrate-{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                0o600, dir_fd=screen_fd)
            break
        except FileExistsError:
            continue
        except Exception:
            raise MigrationError("temp_create_failed") from None
    else:
        raise MigrationError("temp_name_exhausted")

    try:
        if os.geteuid() != source_info.st_uid:
            os.fchown(fd, source_info.st_uid, source_info.st_gid)
        elif os.fstat(fd).st_gid != source_info.st_gid:
            os.fchown(fd, -1, source_info.st_gid)
        for attr, value in xattrs.items():
            os.setxattr(fd, attr, value)
        os.fchmod(fd, stat.S_IMODE(source_info.st_mode))
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise MigrationError("temp_write_failed")
            view = view[written:]
        os.fsync(fd)
        os.utime(fd, ns=(source_info.st_atime_ns, source_info.st_mtime_ns))
        os.fsync(fd)
        if os.fstat(fd).st_size != len(content):
            raise MigrationError("temp_size_mismatch")
        return name
    except MigrationError:
        try:
            os.unlink(name, dir_fd=screen_fd)
        except OSError:
            pass
        raise
    except Exception:
        try:
            os.unlink(name, dir_fd=screen_fd)
        except OSError:
            pass
        raise MigrationError("temp_metadata_or_write_failed") from None
    finally:
        os.close(fd)


def _migrate_locked(screen_fd: int, file_name: str) -> dict[str, object]:
    source_fd, source_info = _source_file(screen_fd, file_name)
    try:
        original = _read_full(source_fd, source_info)
        source_xattrs = _xattrs(source_fd)
    finally:
        try:
            os.utime(source_fd, ns=(source_info.st_atime_ns,
                                     source_info.st_mtime_ns))
        except OSError:
            raise MigrationError("source_metadata_restore_failed") from None
        finally:
            os.close(source_fd)

    redactor = _redactor()
    rewritten, rows, findings = _parse_and_redact(original, redactor)
    file_id = f"{source_info.st_dev:x}:{source_info.st_ino:x}"
    if findings == 0:
        return {"status": "unchanged", "file_id": file_id,
                "rows": rows, "redacted_fields": 0}
    temp_name = _write_temp(screen_fd, rewritten, source_info, source_xattrs)
    replaced = False
    try:
        current = os.stat(file_name, dir_fd=screen_fd, follow_symlinks=False)
        if ((current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
                != (source_info.st_dev, source_info.st_ino, source_info.st_size,
                    source_info.st_mtime_ns)):
            raise MigrationError("source_replaced_before_commit")
        os.replace(temp_name, file_name,
                   src_dir_fd=screen_fd, dst_dir_fd=screen_fd)
        replaced = True
        try:
            os.fsync(screen_fd)
        except OSError:
            raise MigrationError("commit_unknown") from None
    except MigrationError:
        if not replaced:
            try:
                os.unlink(temp_name, dir_fd=screen_fd)
            except OSError:
                pass
        raise
    except Exception:
        if not replaced:
            try:
                os.unlink(temp_name, dir_fd=screen_fd)
            except OSError:
                pass
        raise MigrationError("replace_failed") from None
    return {"status": "updated", "file_id": file_id,
            "rows": rows, "redacted_fields": findings}


def migrate_file(fixture_root: str | os.PathLike[str], file_name: str,
                 *, lock_timeout: float = LOCK_TIMEOUT_SECONDS,
                 exposure_reported: bool = False) -> dict[str, object]:
    """Redact one fixture JSONL under the shared lock and atomic replacement."""
    if type(exposure_reported) is not bool:
        raise MigrationError("invalid_exposure_flag")
    if exposure_reported:
        # A real exposure is an incident/rotation workflow, not a bulk rewrite.
        # Stop before opening even the marked fixture source.
        raise MigrationError("credential_exposure_requires_rotation")
    if (not isinstance(lock_timeout, (int, float)) or isinstance(lock_timeout, bool)
            or not 0 <= lock_timeout <= 30):
        raise MigrationError("invalid_lock_timeout")
    root_fd, screen_fd = _open_fixture(fixture_root)
    try:
        with _lock(root_fd, float(lock_timeout)):
            return _migrate_locked(screen_fd, file_name)
    finally:
        os.close(screen_fd)
        os.close(root_fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", required=True)
    parser.add_argument("--file", required=True,
                        help="one direct *.jsonl filename under fixture ekran/")
    parser.add_argument(
        "--credential-exposure-reported", action="store_true",
        help="stop before reading; use owner-controlled credential rotation first")
    args = parser.parse_args(argv)
    try:
        result = migrate_file(args.fixture_root, args.file,
                              exposure_reported=args.credential_exposure_reported)
    except MigrationError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"status": "error", "code": "internal_error"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
