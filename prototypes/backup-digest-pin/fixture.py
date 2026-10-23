#!/usr/bin/env python3
"""Isolated synthetic fixture for caller-supplied backup digest pins.

This is a prototype/demo, not a production CLI and not a trust-anchor store.
It creates only synthetic tar data under a fresh system-temp directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
MARKER_NAME = ".yuva-backup-digest-pin-fixture"
MARKER_VALUE = b"yuva-backup-digest-pin-fixture-v1\n"
PIN_NAME = "expected-sha256.txt"
PIN_RE = re.compile(r"sha256:([0-9a-f]{64})\n\Z")


def _load_verifier():
    spec = importlib.util.spec_from_file_location(
        "yuva_backup_verify_fixture", REPO_ROOT / "backup_verify.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("fixture_verifier_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _require_fixture_root(root: Path, temp_root: Path) -> None:
    resolved = root.resolve(strict=True)
    resolved.relative_to(temp_root.resolve(strict=True))
    marker = root / MARKER_NAME
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError("fixture_marker_missing")
    if marker.read_bytes() != MARKER_VALUE:
        raise RuntimeError("fixture_marker_invalid")


def _write_archive(archive_path: Path, payload: bytes) -> None:
    with tarfile.open(archive_path, "w:") as tf:
        root = tarfile.TarInfo("yuva")
        root.type = tarfile.DIRTYPE
        root.mode = 0o700
        tf.addfile(root)

        state = tarfile.TarInfo("yuva/durum.json")
        state.mode = 0o600
        state.size = len(payload)
        tf.addfile(state, io.BytesIO(payload))
    archive_path.chmod(0o600)

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum = Path(os.fspath(archive_path) + ".sha256")
    checksum.write_text(f"{digest}  {archive_path}\n", encoding="ascii")
    checksum.chmod(0o600)

    listing = Path(os.fspath(archive_path) + ".list")
    listing.write_text("yuva/\nyuva/durum.json\n", encoding="utf-8")
    listing.chmod(0o600)


def _read_external_pin(pin_path: Path, temp_root: Path) -> tuple[str, str | None]:
    """Read a fixture-only pin outside backup/; never fall back to sidecar."""
    try:
        resolved = pin_path.resolve(strict=True)
        resolved.relative_to(temp_root.resolve(strict=True))
        st = pin_path.lstat()
        if (stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode)
                or st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600
                or st.st_size > 80):
            return "invalid", None
        raw = pin_path.read_text(encoding="ascii")
    except FileNotFoundError:
        return "missing", None
    except (OSError, UnicodeError, ValueError, RuntimeError):
        return "invalid", None
    match = PIN_RE.fullmatch(raw)
    if match is None:
        return "invalid", None
    return "provided", match.group(1)


def _evaluate(verifier, archive: Path, active_root: Path,
              pin_path: Path, temp_root: Path) -> dict[str, object]:
    checked = verifier.verify_backup(archive, active_data_root=active_root)
    pin_state, expected = _read_external_pin(pin_path, temp_root)
    if pin_state == "missing":
        comparison = "not_checked_no_pin"
    elif pin_state == "invalid":
        comparison = "not_checked_invalid_pin"
    else:
        comparison = ("match" if expected == checked["archive"]["sha256"]
                     else "mismatch")

    # A digest comparison is reported separately. It never upgrades source
    # provenance or authorizes restore, even when the caller-supplied pin matches.
    return {
        "preflight_ok": bool(checked["ok"]),
        "adjacent_checksum_matches": bool(
            checked["checksum_sidecar"]["matches_archive"]),
        "external_pin_input": pin_state,
        "external_pin_comparison": comparison,
        "authenticity": "unverified",
        "restore_authorized": False,
    }


def _case(name: str, result: dict[str, object]) -> dict[str, object]:
    return {"case": name, **result}


def run_fixture() -> list[dict[str, object]]:
    verifier = _load_verifier()
    with tempfile.TemporaryDirectory(prefix="yuva-backup-pin-fixture-") as raw:
        temp_root = Path(raw)
        temp_root.chmod(0o700)
        (temp_root / MARKER_NAME).write_bytes(MARKER_VALUE)
        (temp_root / MARKER_NAME).chmod(0o600)

        fixture = temp_root / "fixture"
        active = fixture / "active-yuva"
        backup = fixture / "backup"
        trust_input = fixture / "trust-input"
        for directory in (fixture, active, backup, trust_input):
            directory.mkdir(mode=0o700)
        (fixture / MARKER_NAME).write_bytes(MARKER_VALUE)
        (fixture / MARKER_NAME).chmod(0o600)
        _require_fixture_root(fixture, temp_root)

        archive = backup / "synthetic-yuva.tar"
        pin = trust_input / PIN_NAME
        original_payload = json.dumps(
            {"fixture": True, "generation": 1},
            separators=(",", ":"), sort_keys=True).encode("utf-8")
        _write_archive(archive, original_payload)

        # The harness simulates an independently supplied input by keeping this
        # fixture-only pin outside backup/. In a real deployment, a separate
        # trust domain and authenticated delivery are still required.
        original_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        pin.write_text(f"sha256:{original_digest}\n", encoding="ascii")
        pin.chmod(0o600)
        results = [_case("matching_external_pin", _evaluate(
            verifier, archive, active, pin, temp_root))]

        # Model an attacker replacing both archive and its adjacent checksum.
        # The separately retained fixture pin still represents the old archive.
        changed_payload = json.dumps(
            {"fixture": True, "generation": 2},
            separators=(",", ":"), sort_keys=True).encode("utf-8")
        _write_archive(archive, changed_payload)
        results.append(_case("archive_and_sidecar_replaced_pin_unchanged",
                             _evaluate(verifier, archive, active, pin, temp_root)))

        pin.unlink()
        results.append(_case("missing_external_pin", _evaluate(
            verifier, archive, active, pin, temp_root)))

        pin.write_text("not-a-sha256-pin\n", encoding="ascii")
        pin.chmod(0o600)
        results.append(_case("malformed_external_pin", _evaluate(
            verifier, archive, active, pin, temp_root)))

        pin.write_text(f"sha256:{'0' * 64}\n", encoding="ascii")
        pin.chmod(0o600)
        results.append(_case("wrong_external_pin", _evaluate(
            verifier, archive, active, pin, temp_root)))

        return results


def main() -> int:
    try:
        print(json.dumps({"fixture_only": True, "results": run_fixture()},
                         sort_keys=True))
        return 0
    except Exception as exc:
        # Keep failure output content-free. Fixture paths and input values are
        # intentionally omitted from the report.
        print(json.dumps({"fixture_only": True,
                          "error": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
