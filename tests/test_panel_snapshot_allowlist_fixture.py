import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "panel" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "yuva_panel_snapshot_allowlist_fixture", SERVER_PATH,
    loader=SourceFileLoader("yuva_panel_snapshot_allowlist_fixture", str(SERVER_PATH)))
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


class PanelSnapshotAllowlistFixtureTests(unittest.TestCase):
    def test_veri_projects_only_documented_top_level_and_roster_fields(self):
        durum = {
            "rev": 7,
            "kullanicilar": {
                "@fixture": {
                    "ad": "Fixture", "arac": "test", "rol": "isci",
                    "bas_denetci": False, "sorumlu_kimlik": None,
                    "son_okuma": "message-1", "katilma": "private-date",
                    "bagli": True, "not_": "private profile note",
                    "son_gorulme": "private-time", "extra_secret": "must not escape",
                },
            },
            "internal_secret": "must not escape",
        }
        gorevler = {"gorevler": [{"id": 9, "baslik": "Fixture task"}],
                    "internal_secret": "must not escape"}
        with patch.object(panel, "dosya_kilidi", return_value=nullcontext()), \
                patch.object(panel, "durum_oku", return_value=durum), \
                patch.object(panel, "gorev_oku", return_value=gorevler), \
                patch.object(panel, "mesajlar", return_value=[]), \
                patch.object(panel, "tum_ekranlar", return_value=({}, {"partial": False})), \
                patch.object(panel, "simdi", return_value="fixture-time"):
            snapshot = panel.veri()

        self.assertEqual(set(snapshot), {
            "ok", "simdi", "online_sn", "rev", "kullanicilar", "gorevler",
            "mesajlar", "ekranlar", "ekranlar_meta",
        })
        roster = snapshot["kullanicilar"]["@fixture"]
        self.assertEqual(set(roster), {
            "kimlik", "ad", "arac", "rol", "bas_denetci", "sorumlu_kimlik",
            "son_okuma", "online", "presence_state", "presence_verified",
        })
        encoded = json.dumps(snapshot, ensure_ascii=False)
        for private_value in ("private profile note", "private-date", "private-time",
                              "must not escape"):
            self.assertNotIn(private_value, encoded)

    def test_jsonl_fixture_enforces_raw_and_record_byte_budgets(self):
        with tempfile.TemporaryDirectory(prefix="yuva-snapshot-jsonl-") as temp:
            path = Path(temp) / "messages.jsonl"
            oversized = json.dumps({"metin": "x" * 300})
            accepted = json.dumps({"id": "small", "metin": "kept"})
            path.write_text(oversized + "\n" + accepted + "\n", encoding="utf-8")
            stats = {}
            rows, scanned = panel.jsonl_tail_satirlari(
                path, en_cok_satir=10, en_cok_bayt=1024,
                en_cok_kayit_bayt=128, taranan_dondur=True, istatistik=stats)

        self.assertLessEqual(scanned, 1024)
        self.assertEqual(rows, [accepted])
        self.assertEqual(stats["oversized_records"], 1)

        with tempfile.TemporaryDirectory(prefix="yuva-snapshot-raw-budget-") as temp:
            path = Path(temp) / "oversized-tail.jsonl"
            path.write_bytes(b"x" * 2048 + b"\n")
            raw_stats = {}
            rows, scanned = panel.jsonl_tail_satirlari(
                path, en_cok_satir=10, en_cok_bayt=1024,
                en_cok_kayit_bayt=128, taranan_dondur=True,
                istatistik=raw_stats)
        self.assertLessEqual(scanned, 1024)
        self.assertEqual(scanned, 1024)
        self.assertTrue(raw_stats["byte_budget_exhausted"])
        self.assertEqual(rows, [])

    def test_screen_fixture_never_exceeds_output_byte_budget(self):
        with tempfile.TemporaryDirectory(prefix="yuva-snapshot-screen-") as temp:
            screen_root = Path(temp)
            row = {"ts": "2026-10-23T12:00:00+03:00",
                   "kimlik": "fixture", "ad": "Fixture",
                   "tur": "ekran", "satir": "x" * 300}
            (screen_root / "fixture.jsonl").write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            with patch.object(panel, "EKRAN", screen_root), \
                    patch.object(panel, "EKRAN_CIKTI_TOPLAM_BAYT", 128), \
                    patch.object(panel, "EKRAN_TARAMA_TOPLAM_BAYT", 4096), \
                    patch.object(panel, "EKRAN_PARSE_TOPLAM_BAYT", 4096), \
                    patch.object(panel, "_EKRAN_SECIM_KURSORU", None):
                screens, meta = panel.tum_ekranlar()

        self.assertLessEqual(meta["output_bytes"], meta["output_byte_budget"])
        self.assertEqual(meta["output_byte_budget"], 128)
        self.assertEqual(screens, {})
        self.assertTrue(meta["partial"])
        self.assertIn("output_byte_limit", meta["partial_reasons"])


if __name__ == "__main__":
    unittest.main()
