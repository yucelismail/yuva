import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = load_module("yuva_schema_compat_cli", ROOT / "bin" / "yuva")
panel = load_module("yuva_schema_compat_panel", ROOT / "panel" / "server.py")
backup = load_module("yuva_schema_compat_backup", ROOT / "backup_verify.py")


class DataSchemaCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-schema-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        cli.KOK = self.root
        cli.STATE = self.root / "durum.json"
        cli.GOREV = self.root / "gorevler.json"
        cli.BUS = self.root / "mesaj.jsonl"
        panel.KOK = self.root
        panel.DURUM = self.root / "durum.json"
        panel.GOREV = self.root / "gorevler.json"
        panel.BUS = self.root / "mesaj.jsonl"

    def test_unversioned_roots_remain_readable_and_writes_stamp_v1(self):
        cli.STATE.write_text('{"kullanicilar":{},"rev":0}', encoding="utf-8")
        cli.GOREV.write_text('{"siradaki":1,"gorevler":[]}', encoding="utf-8")
        self.assertEqual(cli.durum_oku()["rev"], 0)
        self.assertEqual(panel.durum_oku()["rev"], 0)
        self.assertEqual(cli.gorev_yukle()["gorevler"], [])
        self.assertEqual(panel.gorev_oku()["gorevler"], [])

        cli.kaydet(cli.GOREV, {"siradaki": 1, "gorevler": []})
        panel.durum_yaz({"kullanicilar": {}, "rev": 0})
        self.assertEqual(json.loads(cli.GOREV.read_text())["schema_version"], 1)
        self.assertEqual(json.loads(panel.DURUM.read_text())["schema_version"], 1)

    def test_future_root_versions_fail_closed_without_rewriting_fixture(self):
        for path, readers in (
                (cli.STATE, (cli.durum_oku, panel.durum_oku)),
                (cli.GOREV, (cli.gorev_yukle, panel.gorev_oku))):
            with self.subTest(path=path.name):
                path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
                original = path.read_bytes()
                for reader in readers:
                    with self.assertRaises((cli.VeriHatasi, panel.DurumHatasi)):
                        reader()
                    self.assertEqual(path.read_bytes(), original)

    def test_message_readers_skip_unknown_explicit_versions_but_keep_legacy(self):
        rows = [
            {"schema_version": 99, "id": "future", "kimden": "future", "metin": "x"},
            {"id": "legacy", "kimden": "old", "metin": "readable"},
        ]
        payload = "".join(json.dumps(row) + "\n" for row in rows)
        cli.BUS.write_text(payload, encoding="utf-8")
        cli_rows = cli.mesajlar()
        self.assertEqual([row["id"] for row in cli_rows], ["legacy"])
        self.assertEqual(cli_rows[0]["trust"], "unverified")
        panel_rows = panel.mesajlar()
        self.assertEqual([row["id"] for row in panel_rows], ["legacy"])
        # The CLI reader exposes archive normalization metadata directly;
        # panel's public allowlist projection carries trust only in provenance.
        self.assertNotIn("trust", panel_rows[0])
        self.assertEqual(panel_rows[0]["provenance"]["trust"], "unverified")
        self.assertEqual(panel_rows[0]["provenance"]["source"], "unknown")

    def test_source_class_claim_is_retained_but_never_trusted(self):
        cli.mesaj_ekle("same-name", "agent claim", source_class="agent")
        panel.mesaj_ekle("same-name", "operator claim", source_class="operator")
        with cli.BUS.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"id": "legacy-class", "kimden": "operator",
                                     "metin": "old row"}) + "\n")

        for reader in (cli.mesajlar, panel.mesajlar):
            rows = {row["metin"]: row for row in reader()}
            self.assertEqual(rows["agent claim"]["source_class"], "agent")
            self.assertEqual(rows["operator claim"]["source_class"], "operator")
            self.assertEqual(rows["old row"]["source_class"], "unknown")
            self.assertTrue(all(row["source_class_trust"] == "unverified"
                                for row in rows.values()))

    def test_claimed_verified_source_class_is_downgraded(self):
        row = {
            "schema_version": 2, "id": "forged-class", "ts": "now",
            "kimden": "operator", "kime": "@all", "tur": "not", "metin": "x",
            "ad": "operator", "kanal": "sohbet", "source": "cli_local",
            "trust": "unverified", "actor_id": None, "auth_method": "none",
            "provenance": {"source": "cli_local", "trust": "unverified",
                            "actor_id": None, "auth_method": "none",
                            "identity_claim": {"value": "operator", "source": "unknown",
                                               "trust": "unverified", "actor_id": None}},
            "source_class": "operator", "source_class_trust": "verified",
        }
        cli.BUS.write_text(json.dumps(row) + "\n", encoding="utf-8")
        for reader in (cli.mesajlar, panel.mesajlar):
            message = reader()[0]
            self.assertEqual(message["source_class"], "operator")
            self.assertEqual(message["source_class_trust"], "unverified")

    def test_backup_verifier_rejects_future_root_and_message_schemas(self):
        state = self.root / "durum.json"
        tasks = self.root / "gorevler.json"
        messages = self.root / "future-messages.jsonl"
        state.write_text('{"schema_version":2}', encoding="utf-8")
        tasks.write_text('{"schema_version":2}', encoding="utf-8")
        messages.write_text('{"schema_version":3}\n', encoding="utf-8")
        for validate, path in ((backup._validate_state, state),
                               (backup._validate_tasks, tasks),
                               (lambda p: backup._validate_jsonl(
                                   p, versioned_messages=True), messages)):
            with self.subTest(path=path.name):
                with self.assertRaises(backup.BackupError):
                    validate(path)


if __name__ == "__main__":
    unittest.main()
