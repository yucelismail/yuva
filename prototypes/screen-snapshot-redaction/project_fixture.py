"""Fixture-only read-time redaction options for historical screen snapshots.

This prototype is deliberately disconnected from the panel and YUVA_DIR.
It reads only a marked, private fixture tree under the system temp directory.
"""

import json
import logging
import os
from pathlib import Path
import re
import stat
import tempfile


MAX_FILES = 128
MAX_FILE_BYTES = 1024 * 1024
MAX_ROWS_PER_FILE = 60
MAX_RECORD_BYTES = 16 * 1024
MARKER_NAME = ".yuva-screen-snapshot-fixture"
MARKER_CONTENT = b"yuva-screen-snapshot-fixture-v1\n"
_IDENTITY = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
_logger = logging.getLogger(__name__)


class FixtureInputError(ValueError):
    """Content-free rejection for an input outside the fixture contract."""


def _reject():
    raise FixtureInputError("fixture input rejected") from None


def _check_private_file(path):
    try:
        info = path.lstat()
    except OSError:
        _reject()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or info.st_mode & 0o077):
        _reject()
    return info


def _fixture_screen_dir(fixture_root):
    try:
        supplied = Path(fixture_root).absolute()
        resolved = supplied.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        _reject()
    if supplied != resolved or resolved == temp_root or temp_root not in resolved.parents:
        _reject()
    try:
        root_info = resolved.lstat()
        marker = resolved / MARKER_NAME
        marker_info = _check_private_file(marker)
        marker_bytes = marker.read_bytes()
        screen_dir = resolved / "ekran"
        screen_info = screen_dir.lstat()
    except (OSError, RuntimeError):
        _reject()
    if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.geteuid()
            or root_info.st_mode & 0o077 or marker_info.st_size != len(MARKER_CONTENT)
            or marker_bytes != MARKER_CONTENT or not stat.S_ISDIR(screen_info.st_mode)
            or screen_info.st_uid != os.geteuid() or screen_info.st_mode & 0o077):
        _reject()
    return screen_dir


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _load_redactor():
    """Load the production shared screen redactor without importing panel code."""
    import importlib.util

    module_path = Path(__file__).resolve().parents[2] / "yuva_screen_redaction.py"
    try:
        spec = importlib.util.spec_from_file_location(
            "yuva_screen_snapshot_fixture_redactor", module_path)
        if spec is None or spec.loader is None:
            _reject()
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        _reject()


def project_fixture_snapshot(fixture_root, action="redact"):
    """Project fixture screen rows using ``redact`` or ``reject`` policy.

    ``redact`` returns rows after the same shared redactor used by writers.
    ``reject`` omits a whole file if a row would change under that redactor.
    Any malformed, oversized, or unredactable row omits its entire file in
    either mode. Metadata and logs contain only constant reason codes/counts.
    The input JSONL is opened read-only and is never rewritten.
    """
    if action not in {"redact", "reject"}:
        raise ValueError("snapshot action must be redact or reject")

    screen_dir = _fixture_screen_dir(fixture_root)
    redactor = _load_redactor()
    output = {}
    reasons = set()
    redacted_rows = 0
    rejected_files = 0
    try:
        candidates = sorted(screen_dir.iterdir(), key=lambda path: path.name)
    except OSError:
        candidates = []
        reasons.add("directory_read_error")

    jsonl_files = [p for p in candidates if p.name.endswith(".jsonl")]
    if len(jsonl_files) > MAX_FILES:
        reasons.add("file_limit")
        jsonl_files = jsonl_files[:MAX_FILES]

    for path in jsonl_files:
        if path.name[:-6].startswith(".") or not _IDENTITY.fullmatch(path.name[:-6]):
            reasons.add("invalid_filename")
            rejected_files += 1
            continue
        try:
            info = _check_private_file(path)
            if info.st_size > MAX_FILE_BYTES:
                reasons.add("file_size_limit")
                rejected_files += 1
                continue
            with path.open("rb") as source:
                raw = source.read(MAX_FILE_BYTES + 1)
        except (OSError, FixtureInputError):
            reasons.add("file_read_error")
            rejected_files += 1
            continue
        if len(raw) > MAX_FILE_BYTES:
            reasons.add("file_size_limit")
            rejected_files += 1
            continue

        try:
            text = raw.decode("utf-8", errors="strict")
            lines = text.splitlines(keepends=True)
            if len(lines) > MAX_ROWS_PER_FILE:
                raise ValueError("row limit")
            if any(not line.endswith("\n") or len(line.encode("utf-8")) > MAX_RECORD_BYTES
                   for line in lines):
                raise ValueError("record boundary")
            records = []
            file_was_redacted = False
            changed_rows = 0
            for line in lines:
                record = json.loads(line, object_pairs_hook=_unique_object)
                safe_record = redactor.redact_screen_record(record)
                if safe_record != record:
                    file_was_redacted = True
                    changed_rows += 1
                records.append(safe_record)
        except Exception:
            # No exception detail, input line, filename, or secret reaches a sink.
            reasons.add("invalid_or_unredactable_record")
            rejected_files += 1
            continue

        if action == "reject" and file_was_redacted:
            reasons.add("sensitive_file_rejected")
            rejected_files += 1
            continue
        output[path.name[:-6]] = records
        if file_was_redacted:
            redacted_rows += changed_rows

    metadata = {
        "partial": bool(reasons),
        "redacted_records": redacted_rows,
        "rejected_files": rejected_files,
        "partial_reasons": sorted(reasons),
        "read_policy": action,
    }
    _logger.info("screen_snapshot_fixture partial=%s redacted_records=%d "
                 "rejected_files=%d policy=%s",
                 metadata["partial"], redacted_rows, rejected_files, action)
    return {"ekranlar": output, "ekranlar_meta": metadata}
