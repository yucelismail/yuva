"""Read-only secret-pattern scan for marked synthetic JSONL fixtures.

This prototype refuses normal Yuva roots and backups. Reports contain only
aggregate counters and fixed reason codes; no paths, records, values, or hashes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


MARKER = ".yuva-history-secret-scan-fixture"
MARKER_VALUE = b"yuva-history-secret-scan-fixture-v1\n"
MAX_FILES = 129  # one chat file plus at most 128 screen files
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_RECORD_BYTES = 16 * 1024
MAX_ROWS_PER_FILE = 10_000


class ScanError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject(code: str = "fixture_rejected"):
    raise ScanError(code) from None


def _redactor():
    module_path = Path(__file__).resolve().parents[2] / "yuva_screen_redaction.py"
    try:
        spec = importlib.util.spec_from_file_location(
            "yuva_history_secret_scan_redactor", module_path)
        if spec is None or spec.loader is None:
            _reject("redactor_unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except ScanError:
        raise
    except Exception:
        _reject("redactor_unavailable")


def _open_dir(path: str | os.PathLike[str]) -> int:
    try:
        supplied = Path(path)
        if supplied.is_symlink():
            _reject("fixture_root_symlink")
        resolved = supplied.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        if (resolved == temp_root
                or os.path.commonpath((str(temp_root), str(resolved))) != str(temp_root)):
            _reject("fixture_root_outside_temp")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(resolved, flags)
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            os.close(fd)
            _reject("unsafe_fixture_root")
        return fd
    except ScanError:
        raise
    except Exception:
        _reject("fixture_root_unavailable")


def _verify_marker(root_fd: int) -> None:
    try:
        fd = os.open(MARKER, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0), dir_fd=root_fd)
        try:
            info = os.fstat(fd)
            marker = os.read(fd, len(MARKER_VALUE) + 1)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                    or marker != MARKER_VALUE):
                _reject("fixture_marker_invalid")
        finally:
            os.close(fd)
    except ScanError:
        raise
    except Exception:
        _reject("fixture_marker_invalid")


def _open_child_dir(root_fd: int, name: str) -> int:
    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                     dir_fd=root_fd)
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            os.close(fd)
            _reject("unsafe_fixture_directory")
        return fd
    except ScanError:
        raise
    except Exception:
        _reject("fixture_layout_invalid")


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _read_candidate(directory_fd: int, name: str) -> bytes:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.geteuid()
                or entry.st_nlink != 1 or stat.S_IMODE(entry.st_mode) & 0o077
                or stat.S_IMODE(entry.st_mode) & 0o7000
                or entry.st_size > MAX_FILE_BYTES):
            _reject("unsafe_or_oversized_file")
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0), dir_fd=directory_fd)
    except ScanError:
        raise
    except Exception:
        _reject("file_unavailable")
    try:
        opened = os.fstat(fd)
        if ((opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino)
                or not stat.S_ISREG(opened.st_mode)):
            _reject("file_changed_before_read")
        chunks = []
        total = 0
        while True:
            part = os.read(fd, min(64 * 1024, MAX_FILE_BYTES + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if total > MAX_FILE_BYTES:
                _reject("file_oversized")
        after = os.fstat(fd)
        if (total != opened.st_size or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)):
            _reject("file_changed_during_read")
        return b"".join(chunks)
    except ScanError:
        raise
    except Exception:
        _reject("file_read_failed")
    finally:
        os.close(fd)


def _content_fields(record: object, kind: str, redactor) -> int:
    """Return changed-field count; never return scanned text to the caller."""
    if type(record) is not dict:
        _reject("record_shape_invalid")
    if kind == "screen":
        clean = redactor.redact_screen_record(record)
        return int(clean["ad"] != record["ad"]) + int(clean["satir"] != record["satir"])
    # Chat's historical schema has multiple versions. This scan intentionally
    # checks only user-facing content fields, not IDs, provenance or metadata.
    if "metin" not in record or type(record["metin"]) is not str:
        _reject("chat_content_field_invalid")
    fields = ["metin"]
    if "ad" in record:
        if type(record["ad"]) is not str:
            _reject("chat_content_field_invalid")
        fields.append("ad")
    changed = 0
    for field in fields:
        if redactor.redact_text(record[field]) != record[field]:
            changed += 1
    return changed


def _scan_bytes(raw: bytes, kind: str, redactor) -> tuple[int, int]:
    if not raw:
        return (0, 0)
    if not raw.endswith(b"\n"):
        _reject("unterminated_record")
    lines = raw.splitlines(keepends=True)
    if len(lines) > MAX_ROWS_PER_FILE:
        _reject("row_limit")
    rows = changed_fields = 0
    for line in lines:
        payload = line[:-2] if line.endswith(b"\r\n") else line[:-1]
        if not payload or len(line) > MAX_RECORD_BYTES:
            _reject("record_boundary_invalid")
        try:
            record = json.loads(payload.decode("utf-8", errors="strict"),
                                object_pairs_hook=_unique_object)
            changed_fields += _content_fields(record, kind, redactor)
        except ScanError:
            raise
        except Exception:
            _reject("record_unscannable")
        rows += 1
    return rows, changed_fields


def _empty_summary() -> dict:
    return {
        "schema": "yuva-history-secret-scan/v1",
        "scan_state": "rejected",
        "policy": "known_patterns_content_fields_only",
        "files_scanned": 0,
        "files_rejected": 0,
        "records_scanned": 0,
        "fields_with_known_credential_pattern": 0,
        "partial_reasons": [],
    }


def scan_fixture(fixture_root: str | os.PathLike[str]) -> dict:
    """Read marked fixture files and return aggregate, content-free counts."""
    summary = _empty_summary()
    reasons: set[str] = set()
    root_fd = _open_dir(fixture_root)
    screen_fd = None
    try:
        _verify_marker(root_fd)
        screen_fd = _open_child_dir(root_fd, "ekran")
        redactor = _redactor()
        candidates: list[tuple[int, str, str]] = []
        try:
            root_names = set(os.listdir(root_fd))
            if root_names - {MARKER, "mesaj.jsonl", "ekran"}:
                reasons.add("unexpected_fixture_entry")
            if "mesaj.jsonl" in root_names:
                candidates.append((root_fd, "mesaj.jsonl", "chat"))
            else:
                reasons.add("chat_file_missing")
            names = os.listdir(screen_fd)
        except Exception:
            reasons.add("directory_read_failed")
            names = []
        screen_names = sorted(name for name in names if name.endswith(".jsonl"))
        if len(screen_names) != len(names):
            reasons.add("unexpected_fixture_entry")
            summary["files_rejected"] += len(names) - len(screen_names)
        if len(screen_names) > MAX_FILES - 1:
            reasons.add("file_limit")
            screen_names = screen_names[:MAX_FILES - 1]
        for name in screen_names:
            if (name in {".", ".."} or "/" in name or "\\" in name
                    or name.startswith(".")):
                reasons.add("invalid_candidate_name")
                summary["files_rejected"] += 1
                continue
            candidates.append((screen_fd, name, "screen"))
        if not screen_names:
            reasons.add("screen_files_missing")
        if len(candidates) > MAX_FILES:
            reasons.add("file_limit")
            candidates = candidates[:MAX_FILES]
        for directory_fd, name, kind in candidates:
            try:
                raw = _read_candidate(directory_fd, name)
                rows, changed = _scan_bytes(raw, kind, redactor)
            except ScanError as error:
                summary["files_rejected"] += 1
                reasons.add(error.code)
                continue
            summary["files_scanned"] += 1
            summary["records_scanned"] += rows
            summary["fields_with_known_credential_pattern"] += changed
        if reasons:
            state = "partial"
        elif summary["fields_with_known_credential_pattern"]:
            state = "known_pattern_found"
        else:
            state = "no_known_pattern_detected"
        summary["scan_state"] = state
        summary["partial_reasons"] = sorted(reasons)
        return summary
    finally:
        if screen_fd is not None:
            os.close(screen_fd)
        os.close(root_fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", required=True)
    args = parser.parse_args(argv)
    try:
        report = scan_fixture(args.fixture_root)
        exit_code = 0 if report["scan_state"] in {
            "known_pattern_found", "no_known_pattern_detected"} else 2
    except ScanError as error:
        report = _empty_summary()
        report["partial_reasons"] = [error.code]
        exit_code = 2
    try:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    except Exception:
        print('{"scan_state":"rejected","partial_reasons":["report_failed"]}')
        return 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
