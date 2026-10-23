#!/usr/bin/env python3
"""Build and verify unsigned Yuva release manifests (stdlib only).

The manifest records content and source claims. It is not trusted unless an
operator pins its exact SHA-256 outside the payload and supplies that pin to
``verify``. No installation, symlink, or YUVA_DIR is changed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
import sys
import unicodedata


SCHEMA = "yuva-release-manifest/v1"
BUILDER = "yuva-release-manifest-tool/v1"
DATA_CONTRACT = "yuva-data-contract/v1"
REQUIRED_FILES = frozenset({
    "bin/yuva", "panel/server.py", "panel/ui.html",
    "contrib/systemd/yuva-panel.service",
})
ALLOWED_EXECUTABLES = frozenset({"bin/yuva"})
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
REPOSITORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class ManifestError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(repo), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ManifestError(f"git command unavailable or timed out: {type(e).__name__}") from e
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ManifestError(f"git {' '.join(args)} failed: {detail[:400]}")
    return result.stdout


def _safe_path(raw: str) -> str:
    if (not isinstance(raw, str) or not raw or "\x00" in raw
            or "\\" in raw or raw.startswith("/")):
        raise ManifestError("payload path must be a non-empty POSIX relative path")
    normalized = unicodedata.normalize("NFC", raw)
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError as e:
        raise ManifestError("payload path is not valid UTF-8") from e
    path = PurePosixPath(normalized)
    if (normalized != raw or any(part in ("", ".", "..") for part in raw.split("/"))
            or path.is_absolute() or path.as_posix() != raw):
        raise ManifestError(f"non-canonical or unsafe payload path: {raw!r}")
    return normalized


def _safe_symlink_target(path: str, target: str) -> None:
    if not target or "\x00" in target or target.startswith("/"):
        raise ManifestError(f"unsafe absolute or empty symlink target at {path}")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
    if resolved == ".." or resolved.startswith("../"):
        raise ManifestError(f"symlink escapes release root: {path} -> {target}")


def _payload_files(root: Path) -> list[dict[str, object]]:
    try:
        root_stat = root.lstat()
    except OSError as e:
        raise ManifestError(f"payload root unavailable: {type(e).__name__}") from e
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ManifestError("payload root must be a real directory, not a symlink")

    records: list[dict[str, object]] = []
    normalized_names: set[str] = set()
    directories: set[str] = {""}
    stack = [(root, "")]
    while stack:
        directory, prefix = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda e: os.fsencode(e.name))
        except OSError as e:
            raise ManifestError(f"payload directory unreadable: {type(e).__name__}") from e
        for entry in entries:
            raw_path = f"{prefix}/{entry.name}" if prefix else entry.name
            path = _safe_path(raw_path)
            if path in normalized_names:
                raise ManifestError(f"duplicate path after Unicode normalization: {path}")
            normalized_names.add(path)
            full = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as e:
                raise ManifestError(f"payload metadata unreadable: {path}") from e
            if stat.S_ISDIR(info.st_mode):
                directories.add(path)
                stack.append((full, path))
            elif stat.S_ISREG(info.st_mode):
                mode = stat.S_IMODE(info.st_mode)
                if mode & ~0o777:
                    raise ManifestError(f"unsupported regular file mode {mode:04o}: {path}")
                content = full.read_bytes()
                records.append({
                    "path": path, "type": "regular",
                    "mode": f"{mode:04o}",
                    "size": len(content), "sha256": _sha256(content),
                })
            elif stat.S_ISLNK(info.st_mode):
                try:
                    target = os.readlink(full)
                    target_bytes = os.fsencode(target)
                    target_text = target_bytes.decode("utf-8")
                except (OSError, UnicodeError) as e:
                    raise ManifestError(f"symlink target is not valid UTF-8: {path}") from e
                _safe_symlink_target(path, target_text)
                records.append({
                    "path": path, "type": "symlink", "mode": "",
                    "size": len(target_bytes), "sha256": _sha256(target_bytes),
                    "target": target_text,
                })
            else:
                raise ManifestError(f"unsupported payload file type: {path}")

    known = directories | {str(record["path"]) for record in records}
    for record in records:
        if record["type"] == "symlink":
            target = posixpath.normpath(posixpath.join(
                posixpath.dirname(str(record["path"])), str(record["target"])))
            if target not in known and not any(name.startswith(target + "/") for name in known):
                raise ManifestError(f"symlink target is missing from payload: {record['path']}")
    records.sort(key=lambda record: str(record["path"]).encode("utf-8"))
    return records


def _payload_digest(records: list[dict[str, object]]) -> str:
    rows = []
    for item in records:
        mode = str(item["mode"]) if item["type"] == "regular" else ""
        columns = (str(item["path"]), str(item["type"]), mode,
                   str(item["size"]), str(item["sha256"]))
        rows.append(b"\x00".join(field.encode("utf-8") for field in columns) + b"\n")
    return _sha256(b"".join(rows))


def _validate_release_file_policy(records: list[dict[str, object]]) -> None:
    by_path = {str(record["path"]): record for record in records}
    missing = sorted(REQUIRED_FILES - set(by_path))
    if missing:
        raise ManifestError("required release files missing: " + ", ".join(missing))
    cli = by_path["bin/yuva"]
    if cli["type"] != "regular" or cli["mode"] != "0755":
        raise ManifestError("required CLI bin/yuva must be a regular executable mode 0755")
    unexpected = sorted(
        str(record["path"]) for record in records
        if record["type"] == "regular" and record["mode"] == "0755"
        and str(record["path"]) not in ALLOWED_EXECUTABLES)
    if unexpected:
        raise ManifestError("unapproved executable payload files: " + ", ".join(unexpected))


def _source_state(repo_arg: Path, repository_id: str) -> dict[str, object]:
    canonical_id = repository_id if REPOSITORY_ID.fullmatch(repository_id or "") else None
    source: dict[str, object] = {
        "repository_id": canonical_id,
        "commit": None, "tree": None, "worktree_state": "unknown",
        "submodules": [],
    }
    repo = Path(repo_arg)
    try:
        top = Path(os.fsdecode(_git(repo, "rev-parse", "--show-toplevel")).strip()).resolve(strict=True)
        root = repo.resolve(strict=True)
        if top != root:
            raise ManifestError("source repository path must be the Git worktree root")
        commit = os.fsdecode(_git(repo, "rev-parse", "--verify", "HEAD^{commit}")).strip()
        tree = os.fsdecode(_git(repo, "rev-parse", "--verify", "HEAD^{tree}")).strip()
        status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all",
                      "--ignore-submodules=none")
        if not OBJECT_ID.fullmatch(commit) or not OBJECT_ID.fullmatch(tree):
            raise ManifestError("full Git commit and tree object IDs are required")
        source.update(commit=commit, tree=tree)
        modules_path = repo / ".gitmodules"
        submodules = []
        if modules_path.exists():
            output = _git(repo, "submodule", "status", "--recursive")
            for raw_line in output.decode("utf-8", "replace").splitlines():
                marker = raw_line[:1]
                submodules.append({"state": "pinned_clean" if marker == " " else "dirty_or_uninitialized",
                                   "entry": raw_line[1:].strip()[:256]})
        source["submodules"] = submodules
        clean = not status and all(row["state"] == "pinned_clean" for row in submodules)
        source["worktree_state"] = "clean" if clean else "dirty"
    except (OSError, ManifestError, UnicodeError):
        # Unknown source is inventory-only and can never become release eligible.
        pass
    return source


def _git_tree_files(repo: Path, commit: str) -> dict[str, tuple[str, str]]:
    raw = _git(repo, "ls-tree", "-r", "-z", "--full-tree", commit)
    files: dict[str, tuple[str, str]] = {}
    normalized: set[str] = set()
    for row in raw.split(b"\x00"):
        if not row:
            continue
        try:
            metadata, raw_path = row.split(b"\t", 1)
            mode_b, kind_b, oid_b = metadata.split(b" ", 2)
            path = _safe_path(raw_path.decode("utf-8"))
            mode, kind, oid = mode_b.decode("ascii"), kind_b.decode("ascii"), oid_b.decode("ascii")
        except (ValueError, UnicodeError) as e:
            raise ManifestError("Git tree contains a malformed or non-UTF-8 path") from e
        if path in normalized:
            raise ManifestError(f"duplicate Git path after Unicode normalization: {path}")
        normalized.add(path)
        if mode == "160000" or kind == "commit":
            raise ManifestError("submodule payloads are unsupported until explicitly pinned into the release")
        if mode not in ("100644", "100755", "120000") or kind != "blob":
            raise ManifestError(f"unsupported Git tree entry: {path}")
        files[path] = (mode, oid)
    return files


def _compare_payload_to_tree(repo: Path, payload: Path, source: dict[str, object],
                             records: list[dict[str, object]]) -> bool:
    commit = source.get("commit")
    if not isinstance(commit, str):
        return False
    tree_files = _git_tree_files(repo, commit)
    if set(tree_files) != {str(row["path"]) for row in records}:
        return False
    for row in records:
        path = str(row["path"])
        mode, oid = tree_files[path]
        expected_mode = {"100644": "0644", "100755": "0755", "120000": ""}[mode]
        if row["mode"] != expected_mode:
            return False
        actual = os.fsencode(os.readlink(payload / path)) if row["type"] == "symlink" else (payload / path).read_bytes()
        if actual != _git(repo, "cat-file", "blob", oid):
            return False
    return True


def create_manifest(repo: Path, payload: Path, repository_id: str) -> dict[str, object]:
    payload = Path(payload)
    source = _source_state(Path(repo), repository_id)
    records = _payload_files(payload)
    _validate_release_file_policy(records)
    source_match = False
    if source["commit"] is not None:
        try:
            source_match = _compare_payload_to_tree(Path(repo), payload, source, records)
        except ManifestError:
            source_match = False
    clean_source = source["worktree_state"] == "clean"
    payload_digest = _payload_digest(records)
    commit = source["commit"]
    reasons = []
    if not clean_source:
        reasons.append("source worktree is dirty or unknown")
    if not source_match:
        reasons.append("payload does not exactly match the selected Git commit")
    if source["repository_id"] is None:
        reasons.append("canonical repository identity was not supplied")
    # No signing key or outside pin is created by this tool. A generated
    # manifest is inventory only; verify may establish trust from an external pin.
    reasons.append("manifest has no signature or external trust anchor")
    return {
        "manifest_schema": SCHEMA,
        "product": "yuva",
        "release_id": f"{commit or 'unknown'}-{payload_digest}",
        "release_eligible": False,
        "release_reasons": reasons,
        "source": source,
        "artifact": {
            "format": "directory-tree/v1",
            "payload_digest": f"sha256:{payload_digest}",
            "payload_matches_source": source_match,
            "files": records,
        },
        "data_contract": {
            "data_root_in_artifact": False,
            "yuva_dir": "configured-separately",
            "schema_compatibility": DATA_CONTRACT,
        },
        "builder": BUILDER,
    }


def _validate_manifest_shape(manifest: object) -> dict[str, object]:
    if not isinstance(manifest, dict) or manifest.get("manifest_schema") != SCHEMA:
        raise ManifestError("unsupported or malformed manifest schema")
    source = manifest.get("source")
    artifact = manifest.get("artifact")
    if not isinstance(source, dict) or not isinstance(artifact, dict):
        raise ManifestError("manifest source/artifact object missing")
    commit, tree = source.get("commit"), source.get("tree")
    if ((commit is not None and (not isinstance(commit, str) or not OBJECT_ID.fullmatch(commit)))
            or (tree is not None and (not isinstance(tree, str) or not OBJECT_ID.fullmatch(tree)))
            or ((commit is None) != (tree is None))
            or source.get("worktree_state") not in ("clean", "dirty", "unknown")
            or (source.get("repository_id") is not None
                and (not isinstance(source.get("repository_id"), str)
                     or not REPOSITORY_ID.fullmatch(source["repository_id"])) )
            or not isinstance(source.get("submodules"), list)):
        raise ManifestError("invalid source identity/state fields")
    if manifest.get("product") != "yuva" or artifact.get("format") != "directory-tree/v1":
        raise ManifestError("unsupported manifest product/artifact format")
    records = artifact.get("files")
    if (not isinstance(records, list)
            or type(artifact.get("payload_matches_source")) is not bool):
        raise ManifestError("manifest artifact.files must be a list")
    required = {"path", "type", "mode", "size", "sha256"}
    seen: set[str] = set()
    previous = None
    for row in records:
        if not isinstance(row, dict) or not required <= set(row):
            raise ManifestError("malformed file record")
        path = _safe_path(row["path"])
        if path in seen:
            raise ManifestError(f"duplicate manifest path: {path}")
        seen.add(path)
        path_key = path.encode("utf-8")
        if previous is not None and path_key <= previous:
            raise ManifestError("manifest file records are not in canonical path order")
        previous = path_key
        if (row["type"] not in ("regular", "symlink")
                or not isinstance(row["size"], int) or isinstance(row["size"], bool)
                or row["size"] < 0 or not isinstance(row["sha256"], str)
                or not HEX64.fullmatch(row["sha256"])):
            raise ManifestError(f"invalid file record values: {path}")
        if row["type"] == "regular":
            if (not isinstance(row["mode"], str)
                    or not re.fullmatch(r"[0-7]{4}", row["mode"])
                    or int(row["mode"], 8) > 0o777 or "target" in row):
                raise ManifestError(f"invalid regular file mode/target: {path}")
            if set(row) != required:
                raise ManifestError(f"unexpected regular file record fields: {path}")
        else:
            if row["mode"] != "" or not isinstance(row.get("target"), str):
                raise ManifestError(f"invalid symlink record: {path}")
            if set(row) != required | {"target"}:
                raise ManifestError(f"unexpected symlink record fields: {path}")
            _safe_symlink_target(path, row["target"])
            target_bytes = row["target"].encode("utf-8")
            if row["size"] != len(target_bytes) or row["sha256"] != _sha256(target_bytes):
                raise ManifestError(f"symlink target digest/size mismatch: {path}")
    _validate_release_file_policy(records)
    expected_digest = f"sha256:{_payload_digest(records)}"
    if artifact.get("payload_digest") != expected_digest:
        raise ManifestError("manifest payload digest does not match its file records")
    data_contract = manifest.get("data_contract")
    if (not isinstance(data_contract, dict)
            or data_contract.get("data_root_in_artifact") is not False
            or data_contract.get("yuva_dir") != "configured-separately"
            or not isinstance(data_contract.get("schema_compatibility"), str)
            or not data_contract["schema_compatibility"]
            or len(data_contract["schema_compatibility"]) > 128):
        raise ManifestError("manifest must explicitly keep YUVA_DIR outside the artifact")
    expected_release_id = f"{commit or 'unknown'}-{expected_digest[len('sha256:'):]}"
    if manifest.get("release_id") != expected_release_id:
        raise ManifestError("release_id does not bind source commit and payload digest")
    if type(manifest.get("release_eligible")) is not bool:
        raise ManifestError("release_eligible must be a JSON boolean")
    return manifest


def verify_manifest(payload: Path, manifest_bytes: bytes, *, source_repo: Path | None = None,
                    trusted_manifest_sha256: str | None = None) -> dict[str, object]:
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise ManifestError("manifest is not valid UTF-8 JSON") from e
    if _canonical_json(manifest) != manifest_bytes:
        raise ManifestError("manifest JSON is not in canonical serialization")
    manifest = _validate_manifest_shape(manifest)
    manifest_sha256 = _sha256(manifest_bytes)
    records = _payload_files(Path(payload))
    _validate_release_file_policy(records)
    payload_match = records == manifest["artifact"]["files"]
    anchor_match = False
    if trusted_manifest_sha256 is not None:
        if trusted_manifest_sha256.startswith("sha256:"):
            trusted_manifest_sha256 = trusted_manifest_sha256[len("sha256:"):]
        if not HEX64.fullmatch(trusted_manifest_sha256):
            raise ManifestError("trusted manifest SHA-256 must be 64 lowercase hex digits")
        anchor_match = manifest_sha256 == trusted_manifest_sha256

    source_match = False
    if source_repo is not None:
        source = _source_state(source_repo, str(manifest["source"].get("repository_id") or ""))
        expected_source = manifest["source"]
        source_match = (
            source.get("repository_id") is not None
            and source["worktree_state"] == "clean"
            and source.get("commit") == expected_source.get("commit")
            and source.get("tree") == expected_source.get("tree")
            and source.get("repository_id") == expected_source.get("repository_id")
            and _compare_payload_to_tree(Path(source_repo), Path(payload), source, records)
            and manifest["artifact"]["payload_matches_source"] is True
        )
    verified = payload_match and source_match and anchor_match
    return {
        "manifest_sha256": manifest_sha256,
        "payload_match": payload_match,
        "source_match": source_match,
        "external_trust_anchor_match": anchor_match,
        "verified_release": verified,
        "release_eligible": verified,
    }


def _write_new(path: Path, data: bytes) -> None:
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ManifestError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Yuva unsigned manifest generator/offline verifier")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="inventory a scratch release payload")
    create.add_argument("--repo", type=Path, required=True)
    create.add_argument("--payload", type=Path, required=True)
    create.add_argument("--repository-id", required=True,
                        help="operator-selected canonical repository identity")
    create.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify", help="offline payload/source/trust verification")
    verify.add_argument("--payload", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--source-repo", type=Path,
                        help="clean local Git source required for source verification")
    verify.add_argument("--trusted-manifest-sha256",
                        help="externally pinned SHA-256; never read from the manifest")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            manifest = create_manifest(args.repo, args.payload, args.repository_id)
            output_bytes = _canonical_json(manifest)
            try:
                args.output.resolve(strict=False).relative_to(args.payload.resolve(strict=True))
            except ValueError:
                pass
            else:
                raise ManifestError("manifest output must be outside the payload tree")
            _write_new(args.output, output_bytes)
            print(json.dumps({"manifest": str(args.output),
                              "release_id": manifest["release_id"],
                              "release_eligible": False,
                              "release_reasons": manifest["release_reasons"]},
                             ensure_ascii=False, sort_keys=True))
            return 0
        raw = args.manifest.read_bytes()
        result = verify_manifest(args.payload, raw, source_repo=args.source_repo,
                                 trusted_manifest_sha256=args.trusted_manifest_sha256)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["verified_release"] else 1
    except (ManifestError, OSError, ValueError) as e:
        print(f"release manifest error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
