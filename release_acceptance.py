#!/usr/bin/env python3
"""Fixture-only release, read-canary, backup, and rollback acceptance harness.

Every install/data/scratch path is created below one TemporaryDirectory and is
removed on exit. This harness never inspects or changes the host installation.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

import backup_verify
import release_installer
import release_manifest


KNOWN_DATA_CONTRACT = "yuva-data-contract/v1"
REQUIRED_GATES = (
    "source_release_hash", "cli_panel_target_match", "path_cli_target_match",
    "unit_panel_target_match", "unit_workdir_target_match", "unit_data_root_match",
    "shared_data_root", "readonly_canary", "backup_guard",
    "schema_compatibility", "rollback_pointer", "rollback_cli_panel_target_match",
    "fixture_writer_sequential", "payload_path_policy",
)


def evaluate_gates(evidence: dict[str, object]) -> dict[str, object]:
    """Unknown, missing, and non-True evidence all produce NO-GO."""
    failed = [name for name in REQUIRED_GATES if evidence.get(name) is not True]
    return {"decision": "NO-GO" if failed else "GO", "failed_gates": failed}


def schema_rollback_compatible(current: dict, rollback: dict) -> bool:
    current_contract = current.get("data_contract", {}).get("schema_compatibility")
    rollback_contract = rollback.get("data_contract", {}).get("schema_compatibility")
    return (current_contract == KNOWN_DATA_CONTRACT
            and rollback_contract == KNOWN_DATA_CONTRACT
            and current_contract == rollback_contract)


def _run(command: list[str], *, cwd: Path | None = None, env=None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False, timeout=20)
    if result.returncode:
        raise RuntimeError(f"fixture command failed: {Path(command[0]).name}"
                           f" (exit {result.returncode})")
    return result.stdout


def _write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def _make_release(root: Path, label: str) -> dict[str, object]:
    repo = root / f"source-{label}"
    repo.mkdir()
    _run(["git", "init", "-q", str(repo)])
    _run(["git", "-C", str(repo), "config", "user.name", "Yuva fixture"])
    _run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"])
    cli = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if sys.argv[1:] != ["--canary-readonly"]: raise SystemExit(2)
data = Path(os.environ["YUVA_DIR"]).resolve(strict=True)
tasks = json.loads((data / "gorevler.json").read_text(encoding="utf-8"))
messages = [json.loads(row) for row in (data / "mesaj.jsonl").read_text(encoding="utf-8").splitlines()]
print(json.dumps({"role":"cli", "release_root":str(Path(__file__).resolve().parents[1]),
 "data_root":str(data), "tasks":len(tasks["gorevler"]), "messages":len(messages)}))
'''
    panel = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if sys.argv[1:] != ["--canary-readonly"]: raise SystemExit(2)
data = Path(os.environ["YUVA_DIR"]).resolve(strict=True)
tasks = json.loads((data / "gorevler.json").read_text(encoding="utf-8"))
messages = [json.loads(row) for row in (data / "mesaj.jsonl").read_text(encoding="utf-8").splitlines()]
print(json.dumps({"role":"panel", "release_root":str(Path(__file__).resolve().parents[1]),
 "data_root":str(data), "tasks":len(tasks["gorevler"]), "messages":len(messages)}))
'''
    _write(repo / "bin/yuva", cli, 0o755)
    _write(repo / "panel/server.py", panel, 0o644)
    _write(repo / "panel/ui.html", f"<!doctype html><title>fixture {label}</title>\n")
    _write(repo / "contrib/systemd/yuva-panel.service",
           "[Unit]\nDescription=Yuva fixture panel\n\n[Service]\n"
           "Type=simple\n"
           "WorkingDirectory=%h/.local/opt/yuva/current\n"
           "Environment=YUVA_DIR=%h/yuva\n"
           "ExecStart=/usr/bin/python3 -u %h/.local/opt/yuva/current/"
           "panel/server.py --host 127.0.0.1 --port 8686\n")
    _write(repo / "README.md", f"release acceptance fixture {label}\n")
    _run(["git", "-C", str(repo), "add", "."])
    _run(["git", "-C", str(repo), "commit", "-qm", label])

    payload = root / f"payload-{label}"
    payload.mkdir()
    for source in repo.rglob("*"):
        relative = source.relative_to(repo)
        if ".git" in relative.parts:
            continue
        target = payload / relative
        if source.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(os.readlink(source), target)
        elif source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(source.stat().st_mode & 0o777)
    manifest = release_manifest.create_manifest(repo, payload, "fixture://yuva")
    manifest["data_contract"]["schema_compatibility"] = KNOWN_DATA_CONTRACT
    raw = release_manifest._canonical_json(manifest)
    return {"repo": repo, "payload": payload, "manifest": manifest, "raw": raw,
            "pin": hashlib.sha256(raw).hexdigest()}


def _payload_path_policy_checks(root: Path, repo: Path, payload: Path) -> dict[str, bool]:
    """Require manifest generation to reject malformed and unsafe link paths."""
    cases = {
        "malformed_path_rejected": lambda candidate: _write(
            candidate / "bad\\path", "malformed path\n"),
        "escaping_symlink_rejected": lambda candidate: os.symlink(
            "../../outside", candidate / "escape-link"),
        "dangling_symlink_rejected": lambda candidate: os.symlink(
            "missing-target", candidate / "dangling-link"),
    }
    results: dict[str, bool] = {}
    for name, mutate in cases.items():
        candidate = root / f"payload-policy-{name}"
        shutil.copytree(payload, candidate, symlinks=True)
        mutate(candidate)
        try:
            release_manifest.create_manifest(repo, candidate, "fixture://yuva")
        except release_manifest.ManifestError:
            results[name] = True
        else:
            results[name] = False
    return results


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        st = path.lstat()
        digest.update(relative + b"\0" + str(st.st_mode & 0o777).encode("ascii") + b"\0")
        if path.is_symlink():
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _unit_target_checks(unit_path: Path, *, home: Path, install_root: Path,
                        data_root: Path) -> dict[str, bool]:
    """Resolve fixture unit code/data paths; never query or start systemd."""
    fields: dict[str, list[str]] = {
        "WorkingDirectory": [], "ExecStart": [], "YUVA_DIR": [],
    }
    try:
        lines = unit_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {"unit_panel_current": False, "unit_workdir_current": False,
                "unit_data_fixture": False, "unit_data_external": False}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in ("WorkingDirectory", "ExecStart"):
            fields[key].append(value.strip())
        elif key == "Environment":
            try:
                tokens = shlex.split(value, comments=False, posix=True)
            except ValueError:
                continue
            fields["YUVA_DIR"].extend(
                token.partition("=")[2] for token in tokens
                if token.startswith("YUVA_DIR="))

    current = (install_root / "current").resolve(strict=True)
    unit_panel_current = False
    if len(fields["ExecStart"]) == 1:
        try:
            tokens = shlex.split(fields["ExecStart"][0], comments=False, posix=True)
            scripts = [token for token in tokens
                       if token.replace("%h", str(home)).endswith("/panel/server.py")]
            unit_panel_current = (
                len(scripts) == 1
                and Path(scripts[0].replace("%h", str(home))).resolve(strict=True)
                == current / "panel" / "server.py")
        except (OSError, RuntimeError, ValueError):
            unit_panel_current = False

    unit_workdir_current = False
    if len(fields["WorkingDirectory"]) == 1:
        try:
            value = fields["WorkingDirectory"][0].replace("%h", str(home))
            unit_workdir_current = Path(value).resolve(strict=True) == current
        except (OSError, RuntimeError, ValueError):
            unit_workdir_current = False

    unit_data = None
    if len(fields["YUVA_DIR"]) == 1:
        try:
            unit_data = Path(fields["YUVA_DIR"][0].replace("%h", str(home))) \
                .resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            pass
    data = data_root.resolve(strict=True)
    install = install_root.resolve(strict=True)
    separate = (not release_installer._path_is_within(data, install)
                and not release_installer._path_is_within(install, data))
    return {
        "unit_panel_current": unit_panel_current,
        "unit_workdir_current": unit_workdir_current,
        "unit_data_fixture": unit_data == data,
        "unit_data_external": unit_data is not None and separate
        and not release_installer._path_is_within(unit_data, install)
        and not release_installer._path_is_within(install, unit_data),
    }


def _make_backup(data_root: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(mode=0o700)
    archive = backup_dir / "fixture.tar"
    with tarfile.open(archive, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        tf.add(data_root, arcname="yuva", recursive=False)
        for path in sorted(data_root.rglob("*"), key=lambda item: item.as_posix()):
            tf.add(path, arcname=(Path("yuva") / path.relative_to(data_root)).as_posix(),
                   recursive=False)
    archive.chmod(0o600)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="ascii")
    Path(str(archive) + ".sha256").chmod(0o600)
    Path(str(archive) + ".list").write_text(
        "yuva/durum.json\nyuva/gorevler.json\nyuva/mesaj.jsonl\n", encoding="utf-8")
    Path(str(archive) + ".list").chmod(0o600)
    return archive


def run_fixture_harness() -> dict[str, object]:
    """Exercise release gates with synthetic source, data, backup, and roots."""
    with tempfile.TemporaryDirectory(prefix="yuva-release-acceptance-",
                                     dir=Path.home()) as temp:
        root = Path(temp)
        data = root / "yuva"
        data.mkdir(mode=0o700)
        (data / "durum.json").write_text(
            '{"schema_version":1,"kullanicilar":{},"rev":0}\n', encoding="utf-8")
        (data / "gorevler.json").write_text(
            '{"schema_version":1,"siradaki":2,"gorevler":[{"id":1,"baslik":"fixture",'
            '"kimden":"fixture","durum":"pending","gecmis":[]}]}\n', encoding="utf-8")
        (data / "mesaj.jsonl").write_text(
            '{"id":"fixture-1","kimden":"fixture","metin":"read only"}\n',
            encoding="utf-8")
        before = _tree_digest(data)

        v1 = _make_release(root, "v1")
        v2 = _make_release(root, "v2")
        payload_path_checks = _payload_path_policy_checks(root, v2["repo"], v2["payload"])
        install_root = root / ".local" / "opt" / "yuva"
        release_installer.install_release(
            install_root=install_root, data_root=data, payload=v1["payload"],
            manifest_bytes=v1["raw"], source_repo=v1["repo"],
            trusted_manifest_sha256=v1["pin"])
        release_installer.install_release(
            install_root=install_root, data_root=data, payload=v2["payload"],
            manifest_bytes=v2["raw"], source_repo=v2["repo"],
            trusted_manifest_sha256=v2["pin"])

        path_dir = root / ".local" / "bin"
        path_dir.mkdir(parents=True, mode=0o700)
        path_entry = path_dir / "yuva"
        path_entry.symlink_to("../opt/yuva/current/bin/yuva")
        path_value = str(path_dir)
        resolved_path_entry = shutil.which("yuva", path=path_value)
        path_cli = (Path(resolved_path_entry).resolve(strict=True)
                    if resolved_path_entry else None)
        unit_path = root / ".config" / "systemd" / "user" / "yuva-panel.service"
        unit_path.parent.mkdir(parents=True, mode=0o700)
        shutil.copyfile(install_root / "current" / "contrib" / "systemd"
                        / "yuva-panel.service", unit_path)

        current = (install_root / "current").resolve(strict=True)
        manifest_check = release_manifest.verify_manifest(
            current, v2["raw"], source_repo=v2["repo"],
            trusted_manifest_sha256=v2["pin"])
        unit_checks = _unit_target_checks(unit_path, home=root,
                                          install_root=install_root, data_root=data)
        unit_text = unit_path.read_text(encoding="utf-8")
        exec_start = next(line.partition("=")[2] for line in unit_text.splitlines()
                          if line.startswith("ExecStart="))
        exec_tokens = shlex.split(exec_start, comments=False, posix=True)
        unit_scripts = [token for token in exec_tokens
                        if token.replace("%h", str(root)).endswith("/panel/server.py")]
        if len(unit_scripts) != 1 or not unit_checks["unit_panel_current"]:
            raise RuntimeError("fixture unit does not select current panel")
        unit_panel_script = Path(unit_scripts[0].replace("%h", str(root)))
        cli_env = {
            **os.environ,
            "PATH": path_value + os.pathsep + str(Path(sys.executable).parent),
            "YUVA_DIR": str(data),
        }
        cli_result = json.loads(_run(["yuva", "--canary-readonly"], env=cli_env))
        panel_result = json.loads(_run([
            sys.executable, str(unit_panel_script), "--canary-readonly"], env=cli_env))
        cli_release_root = Path(cli_result["release_root"]).resolve()
        panel_release_root = Path(panel_result["release_root"]).resolve()
        target_checks = {
            "cli_current": cli_release_root == current,
            "panel_current": panel_release_root == current,
            "release_parent": current.parent == (install_root / "releases").resolve(),
            "path_entry_is_symlink": path_entry.is_symlink(),
            "path_entry_current_cli": path_cli == (current / "bin" / "yuva").resolve(),
            **unit_checks,
        }
        same_release = (target_checks["cli_current"]
                        and target_checks["panel_current"]
                        and target_checks["release_parent"])
        same_data = (Path(cli_result["data_root"]).resolve() == data.resolve()
                     and cli_result["data_root"] == panel_result["data_root"]
                     and not release_installer._path_is_within(data, install_root)
                     and not release_installer._path_is_within(install_root, data))
        readonly = (cli_result["tasks"] == 1 and cli_result["messages"] == 1
                    and panel_result["tasks"] == 1 and panel_result["messages"] == 1
                    and _tree_digest(data) == before)

        backup_path = _make_backup(data, root / "backup")
        backup_report = backup_verify.verify_backup(backup_path, active_data_root=data)
        scratch = root / "scratch"
        scratch.mkdir(mode=0o700)
        restore_report = backup_verify.restore_check(
            backup_path, scratch_root=scratch, destination_name="verified",
            active_data_root=data)
        try:
            backup_verify.verify_backup(data / "inside.tar", active_data_root=data)
            backup_refusal = False
        except backup_verify.BackupError:
            backup_refusal = True
        backup_ok = (backup_report["ok"] is True and restore_report["ok"] is True
                     and backup_refusal and _tree_digest(data) == before)

        current_manifest = v2["manifest"]
        rollback_manifest = v1["manifest"]
        schema_ok = schema_rollback_compatible(current_manifest, rollback_manifest)
        release_installer.rollback_release(
            install_root=install_root, data_root=data, source_repo=v1["repo"],
            trusted_manifest_sha256=v1["pin"])
        rollback_current = (install_root / "current").resolve(strict=True)
        rollback_manifest_check = release_manifest.verify_manifest(
            rollback_current, v1["raw"], source_repo=v1["repo"],
            trusted_manifest_sha256=v1["pin"])
        rollback_unit_checks = _unit_target_checks(
            unit_path, home=root, install_root=install_root, data_root=data)
        rollback_cli = json.loads(_run(["yuva", "--canary-readonly"], env=cli_env))
        rollback_panel = json.loads(_run([
            sys.executable, str(unit_panel_script), "--canary-readonly"], env=cli_env))
        rollback_target_checks = {
            "cli_current": Path(rollback_cli["release_root"]).resolve() == rollback_current,
            "panel_current": Path(rollback_panel["release_root"]).resolve() == rollback_current,
            "path_current_cli": (
                Path(shutil.which("yuva", path=path_value) or "").resolve(strict=True)
                == (rollback_current / "bin" / "yuva").resolve()),
            "unit_current_panel": rollback_unit_checks["unit_panel_current"],
            "unit_current_workdir": rollback_unit_checks["unit_workdir_current"],
        }
        rollback_ok = (
            os.readlink(install_root / "current")
            == f"releases/{v1['manifest']['release_id']}"
            and rollback_manifest_check.get("verified_release") is True
            and rollback_manifest_check.get("source_match") is True
            and _tree_digest(data) == before)
        rollback_canary_ok = (
            all(rollback_target_checks.values())
            and rollback_cli["data_root"] == rollback_panel["data_root"] == str(data)
            and rollback_cli["tasks"] == rollback_panel["tasks"] == 1
            and rollback_cli["messages"] == rollback_panel["messages"] == 1)

        evidence = {
            "source_release_hash": (manifest_check["verified_release"] is True
                                    and manifest_check["source_match"] is True),
            "cli_panel_target_match": same_release,
            "path_cli_target_match": (target_checks["path_entry_is_symlink"]
                                       and target_checks["path_entry_current_cli"]),
            "unit_panel_target_match": target_checks["unit_panel_current"],
            "unit_workdir_target_match": target_checks["unit_workdir_current"],
            "unit_data_root_match": (target_checks["unit_data_fixture"]
                                     and target_checks["unit_data_external"]),
            "shared_data_root": same_data,
            "readonly_canary": readonly,
            "backup_guard": backup_ok,
            "schema_compatibility": schema_ok,
            "rollback_pointer": rollback_ok,
            "rollback_cli_panel_target_match": rollback_canary_ok,
            "fixture_writer_sequential": True,
            "payload_path_policy": all(payload_path_checks.values()),
        }
        fixture = evaluate_gates(evidence)
        unknown_schema = not schema_rollback_compatible(
            {"data_contract": {"schema_compatibility": "unspecified"}}, rollback_manifest)
        unknown_writer = evaluate_gates({
            **evidence, "fixture_writer_sequential": "unknown"})
        report = {
            "scope": "temporary-fixture-only",
            "fixture_decision": fixture["decision"],
            "fixture_failed_gates": fixture["failed_gates"],
            "fixture_target_checks": target_checks,
            "rollback_target_checks": rollback_target_checks,
            "payload_path_checks": payload_path_checks,
            "unknown_schema_is_no_go": unknown_schema,
            "unknown_writer_decision": unknown_writer["decision"],
            "fixture_writer_scope": (
                "synthetic CLI/panel canaries run sequentially; this does not "
                "inspect or prove host writer/process identity"),
            "host_rollout_decision": "NO-GO",
            "host_rollout_blockers": ["fixture-generated pin is not an external trust anchor",
                                       "live writer/process identity not inspected or proved",
                                       "fixture evidence is not host acceptance"],
        }
    try:
        root.lstat()
    except FileNotFoundError:
        temporary_roots_removed = True
    except OSError:
        temporary_roots_removed = False
    else:
        temporary_roots_removed = False
    report["temporary_roots_removed_on_exit"] = temporary_roots_removed
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fixture",),
                        help="run the isolated temporary-root acceptance fixture")
    args = parser.parse_args(argv)
    del args
    try:
        report = run_fixture_harness()
    except Exception as error:
        print(json.dumps({"scope": "temporary-fixture-only", "fixture_decision": "NO-GO",
                          "error_type": type(error).__name__,
                          "host_rollout_decision": "NO-GO"}, sort_keys=True))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["fixture_decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
