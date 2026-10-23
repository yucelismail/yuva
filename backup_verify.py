#!/usr/bin/env python3
"""Read-only Yuva tar backup verifier and explicit scratch restore-check.

The adjacent sha256/list files are consistency metadata, not an independent
trust anchor. This tool never restores to the active YUVA_DIR.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import tempfile
import unicodedata


CHECKSUM_RE = re.compile(r"^(\\?)([0-9a-f]{64})  (.+)$")
EXPECTED_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SCRATCH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_SIDECAR_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 100_000
MAX_RESTORE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_RESTORE_MEMBER_BYTES = 64 * 1024 * 1024
TASK_STATUSES = frozenset({
    "pending", "assigned", "pending_gorevli_review",
    "pending_verification", "verified", "pending_revision", "dropped",
})
RESTORE_CHECK_CLI_STUB = (
    "#!/usr/bin/env python3\n"
    "\"\"\"Disabled CLI entry point in a scratch restore-check tree.\"\"\"\n"
    "import sys\n"
    "print('restore-check scratch is inspection-only; CLI commands are disabled', "
    "file=sys.stderr)\n"
    "raise SystemExit(2)\n"
).encode("utf-8")


class BackupError(ValueError):
    pass


@contextmanager
def _open_regular_nofollow(path: Path):
    path = Path(path)
    try:
        before = path.lstat()
    except OSError as e:
        raise BackupError(f"backup metadata unavailable ({type(e).__name__})") from e
    if not stat.S_ISREG(before.st_mode):
        raise BackupError("backup and sidecars must be regular files, not links or devices")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as e:
        raise BackupError(f"backup file could not be opened safely ({type(e).__name__})") from e
    try:
        after = os.fstat(fd)
        if (not stat.S_ISREG(after.st_mode)
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)):
            raise BackupError("backup path changed or is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            yield stream, after
    finally:
        os.close(fd)


def _hash_stream(stream) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    stream.seek(0)
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest(), size


def _secure_mode(st, *, archive: bool) -> tuple[str, str]:
    mode = stat.S_IMODE(st.st_mode)
    if st.st_uid != os.geteuid():
        return "fail", "file owner does not match effective user"
    if mode & 0o022:
        return "fail", "group/other write permission is set"
    if archive and mode != 0o600:
        return "fail", "archive mode must be exactly 0600"
    if not archive and mode & 0o077:
        return "warning", "metadata is group/other readable; restrict access"
    return "pass", "owner and permission checks passed"


def _inside(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve(strict=True).relative_to(Path(root).resolve(strict=False))
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _safe_member_name(name: str, is_dir: bool) -> str:
    if is_dir and name.endswith("/"):
        name = name.rstrip("/")
    if (not name or "\x00" in name or "\\" in name or name.startswith("/")):
        raise BackupError("tar contains an absolute or malformed member path")
    normalized = unicodedata.normalize("NFC", name)
    if normalized != name:
        raise BackupError("tar member path is not NFC-normalized")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts) or PurePosixPath(name).is_absolute():
        raise BackupError("tar member path escapes or aliases its root")
    return name


def _inspect_tar(stream) -> tuple[list[tarfile.TarInfo], str, int, int]:
    stream.seek(0)
    try:
        archive = tarfile.open(fileobj=stream, mode="r:")
    except (tarfile.TarError, OSError) as e:
        raise BackupError("archive is not a readable uncompressed tar") from e
    with archive:
        try:
            members = archive.getmembers()
        except (tarfile.TarError, OSError) as e:
            raise BackupError("tar member table is truncated or malformed") from e
        if not members:
            raise BackupError("archive has no members")
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise BackupError("archive member count exceeds verification limit")
        names: set[str] = set()
        roots: set[str] = set()
        total_size = 0
        largest_member_size = 0
        for member in members:
            name = _safe_member_name(member.name, member.isdir())
            if name in names:
                raise BackupError(f"duplicate tar member path: {name}")
            names.add(name)
            roots.add(name.split("/", 1)[0])
            if not (member.isdir() or member.isreg()):
                raise BackupError("symlinks, hardlinks and special tar members are not accepted")
            if member.mode & ~0o777:
                raise BackupError(f"tar member has special permission bits: {name}")
            if member.isdir() and member.size != 0:
                raise BackupError(f"directory member has non-zero size: {name}")
            if member.isdir() and member.mode & 0o500 != 0o500:
                raise BackupError(f"directory mode is not readable/searchable by its owner: {name}")
            if member.isreg() and not member.mode & 0o400:
                raise BackupError(f"regular file is not readable by its owner: {name}")
            if member.size < 0:
                raise BackupError(f"tar member has a negative size: {name}")
            total_size += member.size
            largest_member_size = max(largest_member_size, member.size)
        if len(roots) != 1:
            raise BackupError("archive must contain one top-level Yuva data directory")
        root = next(iter(roots))
        root_entry = next((m for m in members
                           if _safe_member_name(m.name, m.isdir()) == root), None)
        if root_entry is None or not root_entry.isdir():
            raise BackupError("archive is missing its top-level directory member")
        return members, root, total_size, largest_member_size


def _sidecar(path: Path, *, allow_restricted: bool = False) -> tuple[bytes, dict[str, object]]:
    with _open_regular_nofollow(path) as (stream, st):
        if st.st_size > MAX_SIDECAR_BYTES:
            raise BackupError("sidecar exceeds the metadata size limit")
        data = stream.read(MAX_SIDECAR_BYTES + 1)
        if len(data) > MAX_SIDECAR_BYTES:
            raise BackupError("sidecar grew beyond the metadata size limit")
    permission, detail = _secure_mode(st, archive=False)
    if permission == "fail":
        raise BackupError(f"sidecar permissions rejected: {detail}")
    return data, {"mode": f"{stat.S_IMODE(st.st_mode):04o}",
                  "permission": permission, "permission_detail": detail}


def _parse_checksum(data: bytes, archive: Path, actual: str) -> bool:
    try:
        text = data.decode("ascii")
    except UnicodeError as e:
        raise BackupError("SHA-256 sidecar must be ASCII") from e
    lines = text.splitlines()
    if len(lines) != 1:
        raise BackupError("SHA-256 sidecar must contain exactly one record")
    match = CHECKSUM_RE.fullmatch(lines[0])
    if not match:
        raise BackupError("SHA-256 sidecar has an unsupported format")
    _, expected, recorded_name = match.groups()
    allowed_names = {archive.name, os.fspath(archive), os.fspath(archive.resolve(strict=True))}
    if recorded_name not in allowed_names:
        raise BackupError("SHA-256 sidecar names a different archive")
    return expected == actual


def _active_root(value: Path | None) -> Path:
    if value is not None:
        return Path(value).resolve(strict=False)
    configured = os.environ.get("YUVA_DIR")
    return Path(configured).expanduser().resolve(strict=False) if configured else Path.home() / "yuva"


def _expected_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not EXPECTED_SHA256_RE.fullmatch(value):
        raise BackupError("expected SHA-256 must be exactly 64 lowercase hexadecimal characters")
    return value


def verify_backup(archive_path: Path, *, active_data_root: Path | None = None,
                  expected_sha256: str | None = None) -> dict[str, object]:
    """Read archive and adjacent sidecars; never extracts or writes files."""
    expected_sha256 = _expected_sha256(expected_sha256)
    archive_path = Path(archive_path)
    if not archive_path.is_absolute():
        archive_path = Path.cwd() / archive_path
    active_root = _active_root(active_data_root)
    if _inside(archive_path, active_root):
        raise BackupError("backup archive must be outside the active YUVA_DIR")
    checksum_path = Path(os.fspath(archive_path) + ".sha256")
    listing_path = Path(os.fspath(archive_path) + ".list")
    if _inside(checksum_path, active_root) or _inside(listing_path, active_root):
        raise BackupError("backup sidecars must be outside the active YUVA_DIR")

    with _open_regular_nofollow(archive_path) as (stream, st):
        archive_permission, archive_permission_detail = _secure_mode(st, archive=True)
        digest, size = _hash_stream(stream)
        members, top_level, total_member_bytes, largest_member_bytes = _inspect_tar(stream)
    checksum_bytes, checksum_meta = _sidecar(checksum_path)
    checksum_match = _parse_checksum(checksum_bytes, archive_path, digest)
    expected_match = None if expected_sha256 is None else expected_sha256 == digest
    listing_bytes, listing_meta = _sidecar(listing_path)
    if not listing_bytes:
        raise BackupError("tar member-list sidecar is empty")
    try:
        listing_bytes.decode("utf-8")
    except UnicodeError as e:
        raise BackupError("tar member-list sidecar is not UTF-8") from e

    ok = (archive_permission == "pass" and checksum_match
          and expected_match is not False)
    return {
        "ok": ok,
        "archive": {"size_bytes": size, "sha256": digest,
                    "mode": f"{stat.S_IMODE(st.st_mode):04o}",
                    "permission": archive_permission,
                    "permission_detail": archive_permission_detail,
                    "member_count": len(members),
                    "member_bytes": total_member_bytes,
                    "largest_member_bytes": largest_member_bytes,
                    "top_level": top_level},
        "restore_limits": {
            "within_limits": (total_member_bytes <= MAX_RESTORE_TOTAL_BYTES
                              and largest_member_bytes <= MAX_RESTORE_MEMBER_BYTES),
            "max_total_bytes": MAX_RESTORE_TOTAL_BYTES,
            "max_member_bytes": MAX_RESTORE_MEMBER_BYTES,
        },
        "checksum_sidecar": {**checksum_meta, "matches_archive": checksum_match},
        "expected_sha256": {
            "provided": expected_sha256 is not None,
            "matches_archive": expected_match,
            "provenance": "caller_supplied_unverified" if expected_sha256 is not None
            else "not_provided",
        },
        "listing_sidecar": {**listing_meta, "size_bytes": len(listing_bytes),
                             "sha256": hashlib.sha256(listing_bytes).hexdigest(),
                             "compared_to_tar": False},
        "authenticity": "unverified; adjacent checksum is not an external trust anchor",
    }


def _safe_extract(members: list[tarfile.TarInfo], archive: tarfile.TarFile,
                  destination: Path) -> None:
    directory_modes: list[tuple[Path, int]] = []
    for member in members:
        name = _safe_member_name(member.name, member.isdir())
        target = destination.joinpath(*PurePosixPath(name).parts)
        try:
            target.relative_to(destination)
        except ValueError as e:
            raise BackupError("restore target escaped selected destination") from e
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory_modes.append((target, member.mode & 0o777))
            continue
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            st = target.parent.lstat()
        except OSError as e:
            raise BackupError("restore parent directory is unavailable") from e
        if not stat.S_ISDIR(st.st_mode):
            raise BackupError("restore parent was replaced by a non-directory")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags, 0o600)
        except OSError as e:
            raise BackupError(f"restore output could not be created safely: {name}") from e
        source = archive.extractfile(member)
        if source is None:
            os.close(fd)
            raise BackupError(f"regular member has no data stream: {name}")
        try:
            with os.fdopen(fd, "wb") as out, source:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(target, member.mode & 0o777, follow_symlinks=False)
        except OSError as e:
            raise BackupError(f"restore write failed: {type(e).__name__}") from e
    for directory, mode in sorted(directory_modes,
                                  key=lambda item: len(item[0].parts), reverse=True):
        os.chmod(directory, mode, follow_symlinks=False)


def _validate_state(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BackupError("durum.json must be an object")
    _validate_schema_version(value, "durum.json", {1})
    users = value.get("kullanicilar", {})
    if not isinstance(users, dict) or any(not isinstance(row, dict) for row in users.values()):
        raise BackupError("durum.json kullanicilar must map IDs to objects")
    revision = value.get("rev", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise BackupError("durum.json rev must be a non-negative integer")


def _validate_tasks(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BackupError("gorevler.json must be an object")
    _validate_schema_version(value, "gorevler.json", {1})
    next_id = value.get("siradaki", 1)
    tasks = value.get("gorevler", [])
    if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id < 1:
        raise BackupError("gorevler.json siradaki must be a positive integer")
    if not isinstance(tasks, list):
        raise BackupError("gorevler.json gorevler must be a list")
    ids = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise BackupError("gorevler.json task row must be an object")
        task_id = task.get("id")
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1 or task_id in ids:
            raise BackupError("gorevler.json task ID must be unique positive integer")
        ids.add(task_id)
        if any(not isinstance(task.get(key), str) for key in ("baslik", "kimden", "durum")):
            raise BackupError(f"gorevler.json task #{task_id} has invalid text fields")
        if task["durum"] not in TASK_STATUSES:
            raise BackupError(f"gorevler.json task #{task_id} has unknown status")
        parent = task.get("ust_gorev_id")
        if parent is not None and (isinstance(parent, bool) or not isinstance(parent, int) or parent < 1):
            raise BackupError(f"gorevler.json task #{task_id} has invalid parent ID")
        history = task.get("gecmis", [])
        if not isinstance(history, list):
            raise BackupError(f"gorevler.json task #{task_id} history must be a list")


def _validate_schema_version(value: dict, name: str, supported: set[int]) -> None:
    version = value.get("schema_version", 1)
    if type(version) is not int or version not in supported:
        raise BackupError(f"{name} has an unsupported schema_version")


def _validate_jsonl(path: Path, *, versioned_messages: bool = False) -> int:
    count = 0
    with path.open("rb") as stream:
        for raw in stream:
            if len(raw) > 2 * 1024 * 1024:
                raise BackupError(f"JSONL record exceeds size limit: {path.name}")
            try:
                item = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as e:
                raise BackupError(f"invalid JSONL record in {path.name}") from e
            if not isinstance(item, dict):
                raise BackupError(f"JSONL record must be an object: {path.name}")
            if versioned_messages and "schema_version" in item:
                _validate_schema_version(item, path.name, {1, 2})
            count += 1
    return count


def _validate_restored_yuva(root: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    state = root / "durum.json"
    tasks = root / "gorevler.json"
    if state.exists():
        _validate_state(state)
        result["durum.json"] = "pass"
    else:
        result["durum.json"] = "not_present"
    if tasks.exists():
        _validate_tasks(tasks)
        result["gorevler.json"] = "pass"
    else:
        result["gorevler.json"] = "not_present"
    jsonl = []
    messages = root / "mesaj.jsonl"
    if messages.exists():
        jsonl.append(("mesaj.jsonl", _validate_jsonl(messages, versioned_messages=True)))
    screens = root / "ekran"
    if screens.exists():
        if not screens.is_dir() or screens.is_symlink():
            raise BackupError("ekran restore path must be a real directory")
        for path in sorted(screens.rglob("*.jsonl")):
            if path.is_symlink() or not path.is_file():
                raise BackupError("screen JSONL entries must be regular files")
            jsonl.append((path.relative_to(root).as_posix(), _validate_jsonl(path)))
    result["jsonl_records"] = sum(count for _, count in jsonl)
    result["jsonl_files"] = len(jsonl)
    return result


def _disable_restored_task_cli(root: Path) -> str:
    """Disable the copied Yuva CLI inside an inspection-only scratch restore.

    Historical backups can contain CLI copies whose task writer treats broken
    JSON as an empty default. The archive remains untouched and hash-verified;
    only the newly extracted scratch copy is replaced with a fail-closed stub.
    """
    path = root / "bin" / "yuva"
    try:
        before = path.lstat()
    except FileNotFoundError:
        return "not_present"
    if not stat.S_ISREG(before.st_mode):
        raise BackupError("restored bin/yuva must be a regular file")
    try:
        os.chmod(path, 0o600, follow_symlinks=False)
    except OSError as e:
        raise BackupError("restored CLI could not be disabled safely") from e
    flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as e:
        raise BackupError("restored CLI could not be disabled safely") from e
    try:
        after = os.fstat(fd)
        if (not stat.S_ISREG(after.st_mode)
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)):
            raise BackupError("restored CLI changed before it could be disabled")
        os.ftruncate(fd, 0)
        remaining = memoryview(RESTORE_CHECK_CLI_STUB)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("restored CLI stub write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        os.fchmod(fd, 0o500)
    except OSError as e:
        raise BackupError("restored CLI could not be disabled safely") from e
    finally:
        os.close(fd)
    return "task_mutations_disabled"


def _validate_scratch_root(path: Path, active_root: Path) -> Path:
    path = Path(path)
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as e:
        raise BackupError("scratch root must already exist") from e
    if (not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o700):
        raise BackupError("scratch root must be a real euid-owned mode-0700 directory")
    try:
        resolved.relative_to(active_root.resolve(strict=False))
    except ValueError:
        return resolved
    raise BackupError("scratch root must be outside active YUVA_DIR")


def restore_check(archive_path: Path, *, scratch_root: Path, destination_name: str,
                  active_data_root: Path | None = None,
                  expected_sha256: str | None = None) -> dict[str, object]:
    """Extract only into a new named directory below an explicit private scratch root."""
    if not SCRATCH_NAME_RE.fullmatch(destination_name) or destination_name in (".", ".."):
        raise BackupError("destination name must be one safe path component")
    active_root = _active_root(active_data_root)
    backup = verify_backup(archive_path, active_data_root=active_root,
                           expected_sha256=expected_sha256)
    if not backup["ok"]:
        raise BackupError("backup verification did not pass; restore-check refused")
    archive_meta = backup["archive"]
    if (archive_meta["member_bytes"] > MAX_RESTORE_TOTAL_BYTES
            or archive_meta["largest_member_bytes"] > MAX_RESTORE_MEMBER_BYTES):
        raise BackupError(
            "archive exceeds restore-check size limits; no scratch files were created")
    scratch = _validate_scratch_root(scratch_root, active_root)
    destination = scratch / destination_name
    if destination.exists() or destination.is_symlink():
        raise BackupError("restore destination already exists; no overwrite performed")
    destination.mkdir(mode=0o700)
    with _open_regular_nofollow(Path(archive_path)) as (stream, st):
        digest, _ = _hash_stream(stream)
        if digest != backup["archive"]["sha256"]:
            raise BackupError("archive changed after verification; restore-check refused")
        try:
            tf = tarfile.open(fileobj=stream, mode="r:")
        except (tarfile.TarError, OSError) as e:
            raise BackupError("archive could not be reopened for restore-check") from e
        with tf:
            members = tf.getmembers()
            # Re-check paths/types from the same open descriptor before writing.
            checked, top_level, _, _ = _inspect_tar(stream)
            if len(checked) != len(members):
                raise BackupError("archive changed during restore-check")
            _safe_extract(members, tf, destination)
    restored_root = destination / str(backup["archive"]["top_level"])
    if not restored_root.is_dir() or restored_root.is_symlink():
        raise BackupError("restored top-level Yuva directory is missing")
    restore_cli_policy = _disable_restored_task_cli(restored_root)
    schema = _validate_restored_yuva(restored_root)
    return {"ok": True, "destination_name": destination_name,
            "schema": schema, "archive_sha256": backup["archive"]["sha256"],
            "acl_xattr_restore": "not_performed",
            "restore_cli_policy": restore_cli_policy}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Yuva backup verifier; no active-root restore")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="read-only archive/hash/permission check")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--active-data-root", type=Path)
    verify.add_argument(
        "--expected-sha256",
        help="optional caller-supplied digest pin; provenance must be established separately")
    restore = sub.add_parser("restore-check", help="extract to a new private scratch directory")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--scratch-root", type=Path, required=True)
    restore.add_argument("--destination-name", required=True)
    restore.add_argument("--active-data-root", type=Path)
    restore.add_argument(
        "--expected-sha256",
        help="optional caller-supplied digest pin; mismatch refuses restore before extraction")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            result = verify_backup(args.archive, active_data_root=args.active_data_root,
                                   expected_sha256=args.expected_sha256)
        else:
            result = restore_check(
                args.archive, scratch_root=args.scratch_root,
                destination_name=args.destination_name,
                active_data_root=args.active_data_root,
                expected_sha256=args.expected_sha256)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 1
    except (BackupError, OSError, tarfile.TarError, json.JSONDecodeError) as e:
        print(f"backup verification error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
