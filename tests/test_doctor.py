import importlib.util
from importlib.machinery import SourceFileLoader
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import release_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "bin" / "yuva"


def load_cli():
    name = "yuva_doctor_under_test"
    spec = importlib.util.spec_from_file_location(
        name, CLI_PATH, loader=SourceFileLoader(name, str(CLI_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.home / ".local" / "opt" / "yuva"
        self.release = self.install / "releases" / "release-a"
        (self.release / "bin").mkdir(parents=True)
        (self.release / "panel").mkdir()
        (self.release / "bin" / "yuva").write_text("fixture", encoding="utf-8")
        (self.release / "bin" / "yuva").chmod(0o755)
        (self.release / "panel" / "server.py").write_text("fixture", encoding="utf-8")
        (self.install / "current").symlink_to(self.release)
        self.user_bin = self.home / ".local" / "bin" / "yuva"
        self.user_bin.parent.mkdir(parents=True)
        self.user_bin.symlink_to(self.install / "current" / "bin" / "yuva")
        self.data = self.home / "yuva"
        self.data.mkdir(mode=0o700)
        (self.data / "durum.json").write_text(
            '{"schema_version":1,"kullanicilar":{}}', encoding="utf-8")
        (self.data / "gorevler.json").write_text(
            '{"schema_version":1,"gorevler":[]}', encoding="utf-8")
        (self.data / "mesaj.jsonl").write_text(
            '{"schema_version":2,"metin":"private fixture body"}\n', encoding="utf-8")
        self.template = self.root / "template.service"
        self.unit = self.home / ".config" / "systemd" / "user" / "yuva-panel.service"
        self.template.parent.mkdir(parents=True, exist_ok=True)
        self.unit.parent.mkdir(parents=True)
        unit_text = (
            "[Service]\n"
            "WorkingDirectory=%h/.local/opt/yuva/current\n"
            "Environment=YUVA_DIR=%h/yuva SECRET=fixture-secret\n"
            "ExecStart=/usr/bin/python3 -u %h/.local/opt/yuva/current/panel/server.py --port 8686\n"
        )
        self.template.write_text(unit_text, encoding="utf-8")
        self.unit.write_text(unit_text, encoding="utf-8")
        self.proc_tcp = self.root / "tcp"
        self.proc_tcp.write_text(
            "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n",
            encoding="ascii")
        self.cli = load_cli()

    def tearDown(self):
        self.temp.cleanup()

    def report(self, **overrides):
        options = {
            "home": self.home,
            "cli_path": self.install / "current" / "bin" / "yuva",
            "code_root": self.install / "current",
            "data_root": self.data,
            "install_root": self.install,
            "template_path": self.template,
            "installed_unit": self.unit,
            "user_bin_path": self.user_bin,
            "tcp_paths": (self.proc_tcp,),
            "port": 8765,
        }
        options.update(overrides)
        return self.cli.doctor_raporu(**options)

    def _prepare_rollback_manifests(self, current_contract="yuva-data-contract/v1",
                                   previous_contract="yuva-data-contract/v1"):
        """Build two bounded, secure synthetic release pointers and manifests."""
        commit, tree = "a" * 40, "b" * 40
        files = {
            "bin/yuva": (b"fixture cli", "0755"),
            "contrib/systemd/yuva-panel.service": (b"fixture unit", "0644"),
            "panel/server.py": (b"fixture panel", "0644"),
            "panel/ui.html": (b"fixture ui", "0644"),
        }
        records = []
        for name, (content, mode) in sorted(files.items()):
            records.append({"path": name, "type": "regular", "mode": mode,
                            "size": len(content),
                            "sha256": hashlib.sha256(content).hexdigest()})
        payload_digest = release_manifest._payload_digest(records)
        current_id = f"{commit}-{payload_digest}"
        previous_id = f"{'c' * 40}-{payload_digest}"

        self.install.chmod(0o700)
        releases = self.install / "releases"
        releases.chmod(0o700)
        current_release = releases / current_id
        if not current_release.exists():
            current_release.mkdir()
            (current_release / "bin").mkdir()
            (current_release / "panel").mkdir()
            current_cli = current_release / "bin" / "yuva"
            current_cli.write_text("fixture", encoding="utf-8")
            current_cli.chmod(0o755)
            (current_release / "panel" / "server.py").write_text("fixture", encoding="utf-8")
        previous_release = releases / previous_id
        (previous_release / "bin").mkdir(parents=True, exist_ok=True)
        (previous_release / "panel").mkdir(exist_ok=True)
        (previous_release / "bin" / "yuva").write_text("fixture", encoding="utf-8")
        (previous_release / "panel" / "server.py").write_text("fixture", encoding="utf-8")

        current_pointer = self.install / "current"
        current_pointer.unlink()
        current_pointer.symlink_to(f"releases/{current_id}")
        previous_pointer = self.install / "previous"
        if previous_pointer.is_symlink() or previous_pointer.exists():
            previous_pointer.unlink()
        previous_pointer.symlink_to(f"releases/{previous_id}")
        manifests = self.install / "manifests"
        manifests.mkdir(mode=0o700, exist_ok=True)
        manifests.chmod(0o700)

        def manifest(release_id, data_contract):
            document = {
                "manifest_schema": release_manifest.SCHEMA,
                "product": "yuva",
                "release_id": release_id,
                "release_eligible": False,
                "release_reasons": ["fixture only"],
                "source": {"repository_id": "fixture://yuva",
                           "commit": release_id.split("-", 1)[0],
                           "tree": tree, "worktree_state": "clean", "submodules": []},
                "artifact": {"format": "directory-tree/v1",
                             "payload_digest": f"sha256:{payload_digest}",
                             "payload_matches_source": False, "files": records},
                "data_contract": {"data_root_in_artifact": False,
                                  "yuva_dir": "configured-separately",
                                  "schema_compatibility": data_contract},
                "builder": release_manifest.BUILDER,
            }
            path = manifests / f"{release_id}.manifest.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            path.chmod(0o600)

        manifest(current_id, current_contract)
        manifest(previous_id, previous_contract)
        return current_id, previous_id

    def test_reports_preconditions_without_reading_payloads_or_secrets(self):
        rows = self.report()
        by_key = {key: (state, detail) for key, state, detail in rows}

        self.assertEqual(by_key["current"][0], "pass")
        self.assertEqual(by_key["supported_cli_entry"][0], "pass")
        self.assertEqual(by_key["data_root"][0], "pass")
        self.assertEqual(by_key["unit_template"][0], "pass")
        self.assertEqual(by_key["installed_unit"][0], "pass")
        self.assertEqual(by_key["cli_panel_release_alignment"][0], "pass")
        self.assertEqual(by_key["legacy_writer_inventory"][0], "pass")
        self.assertEqual(by_key["writer_schema"][0], "pass")
        self.assertEqual(by_key["panel_port_8765"][0], "no_listener_observed")
        self.assertEqual(by_key["auth_runtime"][0], "unknown")
        self.assertEqual(by_key["presence"][0], "unknown")
        self.assertNotIn("fixture-secret", repr(rows))
        self.assertNotIn("private fixture body", repr(rows))

    def test_detects_listener_and_does_not_claim_its_owner(self):
        self.proc_tcp.write_text(
            "header\n0: 0100007F:223D 00000000:0000 0A 00000000:00000000 "
            "00:00000000 00000000 1000 0 1\n", encoding="ascii")

        by_key = {key: (state, detail) for key, state, detail in self.report()}

        self.assertEqual(by_key["panel_port_8765"][0], "occupied")
        self.assertIn("süreç sahibi doğrulanmadı", by_key["panel_port_8765"][1])

    def test_fails_closed_for_bad_current_and_data_permissions(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "bin").mkdir()
        (outside / "panel").mkdir()
        (outside / "bin" / "yuva").write_text("fixture", encoding="utf-8")
        (outside / "panel" / "server.py").write_text("fixture", encoding="utf-8")
        (self.install / "current").unlink()
        (self.install / "current").symlink_to(outside)
        self.data.chmod(0o755)

        by_key = {key: (state, detail) for key, state, detail in self.report()}

        self.assertEqual(by_key["current"][0], "fail")
        self.assertEqual(by_key["data_root"][0], "fail")
        self.assertEqual(self.data.stat().st_mode & 0o777, 0o755)

    def test_procfs_failure_is_unknown(self):
        by_key = {key: (state, detail) for key, state, detail in
                  self.report(tcp_paths=(self.root / "missing",))}

        self.assertEqual(by_key["panel_port_8765"][0], "unknown")

    def test_marks_legacy_cli_entry_unsupported(self):
        legacy = self.home / "yuva" / "bin" / "yuva"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("legacy fixture", encoding="utf-8")
        self.user_bin.unlink()
        self.user_bin.symlink_to(legacy)

        by_key = {key: (state, detail) for key, state, detail in self.report()}

        self.assertEqual(by_key["supported_cli_entry"][0], "fail")
        self.assertIn("desteklenmiyor", by_key["supported_cli_entry"][1])

    def test_rejects_copied_cli_as_supported_path_entry(self):
        self.user_bin.unlink()
        self.user_bin.write_text("copied release file", encoding="utf-8")

        by_key = {key: (state, detail) for key, state, detail in self.report()}

        self.assertEqual(by_key["supported_cli_entry"][0], "fail")
        self.assertIn("symlink değil", by_key["supported_cli_entry"][1])

    def test_path_cli_and_panel_source_must_resolve_to_same_release(self):
        other = self.root / "other-release"
        (other / "panel").mkdir(parents=True)
        (other / "panel" / "server.py").write_text("other", encoding="utf-8")

        by_key = {key: (state, detail) for key, state, detail in
                  self.report(code_root=other)}

        self.assertEqual(by_key["cli_panel_release_alignment"][0], "fail")
        self.assertIn("NO-GO", by_key["cli_panel_release_alignment"][1])

    def test_rejects_unit_execstart_copy_and_symlink_data_root(self):
        other = self.root / "legacy" / "panel" / "server.py"
        other.parent.mkdir(parents=True)
        other.write_text("legacy panel", encoding="utf-8")
        self.unit.write_text(
            "[Service]\n"
            f"WorkingDirectory={self.install / 'current'}\n"
            f"Environment=YUVA_DIR={self.data}\n"
            f"ExecStart=/usr/bin/python3 {other} --port 8765\n",
            encoding="utf-8")
        data_alias = self.root / "data-alias"
        data_alias.symlink_to(self.data)

        by_key = {key: (state, detail) for key, state, detail in
                  self.report(data_root=data_alias)}

        self.assertEqual(by_key["installed_unit"][0], "fail")
        self.assertIn("panel_script", by_key["installed_unit"][1])
        self.assertEqual(by_key["data_root"][0], "fail")

    def test_inventories_legacy_writer_copy_without_reading_or_running_it(self):
        legacy = self.home / "yuva" / "bin" / "yuva"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("private legacy source", encoding="utf-8")

        by_key = {key: (state, detail) for key, state, detail in self.report()}

        self.assertEqual(by_key["legacy_writer_inventory"][0], "unknown")
        self.assertIn("etkin writer olup olmadığı", by_key["legacy_writer_inventory"][1])
        self.assertNotIn("private legacy source", repr(by_key["legacy_writer_inventory"]))

    def test_rejects_unsupported_data_schema_without_reporting_payload(self):
        (self.data / "gorevler.json").write_text(
            '{"schema_version":99,"gorevler":[{"detay":"private"}]}',
            encoding="utf-8")

        by_key = {key: (state, detail) for key, state, detail in self.report()}

        self.assertEqual(by_key["writer_schema"][0], "fail")
        self.assertIn("NO-GO", by_key["writer_schema"][1])
        self.assertNotIn("private", repr(by_key["writer_schema"]))

    def test_rollback_data_schema_candidate_is_bounded_and_never_a_go(self):
        self._prepare_rollback_manifests()
        rows = self.report()
        by_key = {key: (state, detail) for key, state, detail in rows}
        self.assertEqual(by_key["rollback_data_schema"][0], "candidate")
        self.assertIn("stored manifest pin'i", by_key["rollback_data_schema"][1])
        self.assertIn("screen satırları", by_key["rollback_data_schema"][1])
        self.assertIn("runtime doğrulanmadı", by_key["rollback_data_schema"][1])
        self.assertEqual(by_key["data_root"][0], "pass")
        self.assertEqual(by_key["writer_schema"][0], "pass")

        # Runtime/presence evidence remains unknown; a schema candidate never
        # upgrades the overall read-only doctor summary to GO.
        self.assertEqual(by_key["presence"][0], "unknown")
        output = io.StringIO()
        with patch.object(self.cli, "doctor_raporu", return_value=rows):
            with contextlib.redirect_stdout(output):
                self.cli.cmd_doctor(type("Args", (), {
                    "install_root": self.install, "port": 8765})())
        rendered = output.getvalue()
        self.assertIn("UNKNOWN · kurulum hazır kabul edilemez", rendered)
        self.assertNotIn("summary=GO", rendered)

    def test_rollback_data_schema_contract_pointer_and_metadata_fail_closed(self):
        current_id, previous_id = self._prepare_rollback_manifests()
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "candidate")

        # A valid but different target contract is a hard incompatibility.
        self._prepare_rollback_manifests(
            current_contract="yuva-data-contract/v1",
            previous_contract="yuva-data-contract/v2")
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "fail")

        # Missing and malformed metadata cannot be promoted to a candidate.
        self._prepare_rollback_manifests()
        (self.install / "manifests" / f"{previous_id}.manifest.json").unlink()
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")
        (self.install / "manifests" / f"{previous_id}.manifest.json").write_text(
            '{"invalid":true}', encoding="utf-8")
        (self.install / "manifests" / f"{previous_id}.manifest.json").chmod(0o600)
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")

        (self.install / "manifests" / f"{previous_id}.manifest.json").unlink()
        (self.install / "previous").unlink()
        (self.install / "previous").symlink_to(f"releases/{current_id}")
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "fail")

        (self.install / "previous").unlink()
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")
        (self.install / "previous").symlink_to("releases/../outside")
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")
        (self.install / "current").unlink()
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")

    def test_rollback_evidence_chain_metadata_and_conflicts_stay_unknown_or_fail(self):
        current_id, previous_id = self._prepare_rollback_manifests()
        releases = self.install / "releases"
        manifests = self.install / "manifests"
        previous_manifest = manifests / f"{previous_id}.manifest.json"

        # Every directory that anchors pointer or manifest evidence must keep
        # its required type/owner/mode; broken metadata cannot become PASS.
        for path in (self.install, releases, manifests):
            before = path.stat().st_mode & 0o777
            path.chmod(0o755)
            with self.subTest(directory=path.name):
                by_key = {key: (state, detail) for key, state, detail in self.report()}
                self.assertEqual(by_key["rollback_data_schema"][0], "unknown")
                self.assertNotIn("PASS", by_key["rollback_data_schema"][1])
            path.chmod(before)

        # Manifest custody failures and malformed/contradictory fields leave
        # the chain UNKNOWN instead of treating a parseable fragment as proof.
        previous_manifest.chmod(0o644)
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")
        previous_manifest.chmod(0o600)

        hardlink = self.root / "manifest-hardlink"
        os.link(str(previous_manifest), str(hardlink))
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")
        hardlink.unlink()

        original = previous_manifest.read_bytes()
        previous_manifest.write_text(
            '{"manifest_schema":1,"manifest_schema":1}', encoding="utf-8")
        previous_manifest.chmod(0o600)
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")

        previous_manifest.write_bytes(original)
        previous_manifest.chmod(0o600)
        contradictory = json.loads(original)
        contradictory["release_id"] = current_id
        previous_manifest.write_text(json.dumps(contradictory), encoding="utf-8")
        previous_manifest.chmod(0o600)
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")

        # A valid but contradictory current/previous contract is a hard NO-GO.
        self._prepare_rollback_manifests(
            current_contract="yuva-data-contract/v1",
            previous_contract="yuva-data-contract/v2")
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "fail")
        self.assertIn("NO-GO", by_key["rollback_data_schema"][1])

    def test_rollback_data_schema_uses_actual_data_root_and_writer_states(self):
        self._prepare_rollback_manifests()
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["rollback_data_schema"][0], "candidate")

        self.data.chmod(0o755)
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["data_root"][0], "fail")
        self.assertEqual(by_key["rollback_data_schema"][0], "fail")
        self.data.chmod(0o700)

        missing_data = self.root / "missing-data"
        by_key = {key: (state, detail) for key, state, detail in
                  self.report(data_root=missing_data)}
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")

        (self.data / "gorevler.json").write_text(
            '{"schema_version":99,"gorevler":[]}', encoding="utf-8")
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["writer_schema"][0], "fail")
        self.assertEqual(by_key["rollback_data_schema"][0], "fail")

        (self.data / "gorevler.json").unlink()
        by_key = {key: (state, detail) for key, state, detail in self.report()}
        self.assertEqual(by_key["writer_schema"][0], "unknown")
        self.assertEqual(by_key["rollback_data_schema"][0], "unknown")


if __name__ == "__main__":
    unittest.main()
