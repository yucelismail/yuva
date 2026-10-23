import importlib.util
import json
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prototypes.panel_snapshot_budget import snapshot_budget


ROOT = Path(__file__).resolve().parents[1]


def load_panel():
    name = "yuva_snapshot_screen_cursor_panel"
    path = ROOT / "panel" / "server.py"
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decoded(response):
    return json.loads(response.body.decode("utf-8"))


class SnapshotScreenCursorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-snapshot-cursor-")
        self.root = Path(self.temp.name) / "yuva-data"
        self.env = patch.dict(os.environ, {"YUVA_DIR": str(self.root)})
        self.env.start()
        self.panel = load_panel()
        self.screen_root = self.root / "ekran"
        self.screen_root.mkdir(parents=True)
        self.records = {}
        for name in ("agent-a", "agent-b", "agent-c", "agent-d"):
            row = {
                "ts": "2026-10-23T12:00:00+03:00",
                "kimlik": name,
                "ad": name,
                "tur": "ekran",
                # Large rows make the global response limit cross the item
                # boundary while the panel's own source budgets stay generous.
                "satir": ("screen fixture " + name + " ") + ("x" * 2200),
            }
            self.records[name] = row
            (self.screen_root / f"{name}.jsonl").write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def _panel_limits(self, *, raw_budget=1_000_000, cursor=None):
        return patch.multiple(
            self.panel,
            EKRAN=self.screen_root,
            EKRAN_DOSYA_AZAMI=2,
            EKRAN_TARAMA_TOPLAM_BAYT=raw_budget,
            EKRAN_PARSE_TOPLAM_BAYT=100_000,
            EKRAN_CIKTI_TOPLAM_BAYT=100_000,
            EKRAN_SN=10,
            _EKRAN_SECIM_KURSORU=cursor,
        )

    @staticmethod
    def _snapshot(screens, screen_meta):
        return {
            "ok": True,
            "simdi": "fixture-now",
            "online_sn": 30,
            "rev": 1,
            "kullanicilar": {},
            "gorevler": [],
            "mesajlar": [],
            "ekranlar": screens,
            "ekranlar_meta": screen_meta,
        }

    def _response(self, screens, screen_meta, budget):
        return snapshot_budget.build_response(
            self._snapshot(screens, screen_meta), response_byte_budget=budget,
            group_budgets={name: 100_000 for name in snapshot_budget.GROUP_FIELDS},
            metadata_reserve=512, screen_order=list(screens))

    def test_global_budget_below_and_above_screen_items(self):
        source_before = {path.name: path.read_bytes()
                         for path in self.screen_root.glob("*.jsonl")}
        with self._panel_limits():
            screens, screen_meta = self.panel.tum_ekranlar()
            self.assertEqual(list(screens), ["agent-a", "agent-b"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-b.jsonl")

            # The response budget admits the first screen file, but not the
            # second. The global projection must not change the source cursor.
            smaller = decoded(self._response(screens, screen_meta, 5_000))
            self.assertEqual(list(smaller["ekranlar"]), ["agent-a"])
            self.assertEqual(smaller["snapshot_meta"]["omitted"]["ekran_dosyalari"], 1)
            self.assertTrue(smaller["snapshot_meta"]["partial"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-b.jsonl")

            larger = decoded(self._response(screens, screen_meta, 20_000))
            self.assertEqual(list(larger["ekranlar"]), ["agent-a", "agent-b"])
            self.assertEqual(larger["snapshot_meta"]["included"]["ekran_dosyalari"], 2)
            self.assertEqual(larger["snapshot_meta"]["omitted"]["ekran_dosyalari"], 0)
            # The panel source itself had discovered more files than its page
            # limit; that independent partial state remains visible.
            self.assertTrue(larger["snapshot_meta"]["partial"])
            self.assertIn("screen_output_partial",
                          larger["snapshot_meta"]["partial_reasons"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-b.jsonl")
            self.assertEqual(source_before, {path.name: path.read_bytes()
                                             for path in self.screen_root.glob("*.jsonl")})

    def test_cursor_wrap_visits_first_page_without_changing_sources(self):
        source_before = {path.name: path.read_bytes()
                         for path in self.screen_root.glob("*.jsonl")}
        with self._panel_limits(cursor="agent-d.jsonl"):
            screens, _ = self.panel.tum_ekranlar()
            self.assertEqual(list(screens), ["agent-a", "agent-b"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-b.jsonl")
            self.assertEqual(source_before, {path.name: path.read_bytes()
                                             for path in self.screen_root.glob("*.jsonl")})

    def test_reader_partial_then_global_projection_keeps_unread_file_eligible(self):
        first_file_size = (self.screen_root / "agent-a.jsonl").stat().st_size
        source_before = {path.name: path.read_bytes()
                         for path in self.screen_root.glob("*.jsonl")}
        with self._panel_limits(raw_budget=first_file_size):
            first_screens, first_meta = self.panel.tum_ekranlar()
            self.assertEqual(list(first_screens), ["agent-a"])
            self.assertTrue(first_meta["partial"])
            self.assertIn("raw_byte_limit", first_meta["partial_reasons"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-a.jsonl")

            first = decoded(self._response(first_screens, first_meta, 20_000))
            self.assertEqual(list(first["ekranlar"]), ["agent-a"])
            self.assertTrue(first["snapshot_meta"]["partial"])
            self.assertIn("screen_output_partial", first["snapshot_meta"]["partial_reasons"])

        with self._panel_limits(cursor="agent-a.jsonl"):
            next_screens, _ = self.panel.tum_ekranlar()
            self.assertEqual(list(next_screens), ["agent-b", "agent-c"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-c.jsonl")
            self.assertEqual(source_before, {path.name: path.read_bytes()
                                             for path in self.screen_root.glob("*.jsonl")})
        with patch.object(self.panel, "EKRAN", self.screen_root), \
                patch.object(self.panel, "EKRAN_DOSYA_AZAMI", 2), \
                patch.object(self.panel, "EKRAN_TARAMA_TOPLAM_BAYT", 1_000_000), \
                patch.object(self.panel, "EKRAN_PARSE_TOPLAM_BAYT", 100_000), \
                patch.object(self.panel, "EKRAN_CIKTI_TOPLAM_BAYT", 100_000), \
                patch.object(self.panel, "EKRAN_SN", 10), \
                patch.object(self.panel, "_EKRAN_SECIM_KURSORU", None):
            screens, screen_meta = self.panel.tum_ekranlar()
            self.assertEqual(list(screens), ["agent-a", "agent-b"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-b.jsonl")

            snapshot = {
                "ok": True,
                "simdi": "fixture-now",
                "online_sn": 30,
                "rev": 1,
                "kullanicilar": {},
                "gorevler": [],
                "mesajlar": [],
                "ekranlar": screens,
                "ekranlar_meta": screen_meta,
            }
            encoded_first = len(json.dumps(
                "agent-a", ensure_ascii=False, separators=(",", ":"),
                allow_nan=False).encode("utf-8")) + 1 + len(json.dumps(
                    screens["agent-a"], ensure_ascii=False,
                    separators=(",", ":"), allow_nan=False).encode("utf-8"))
            group_caps = {name: 2 for name in snapshot_budget.GROUP_FIELDS}
            group_caps["ekranlar"] = 2 + encoded_first
            response = snapshot_budget.build_response(
                snapshot, response_byte_budget=4096,
                group_budgets=group_caps, metadata_reserve=512,
                screen_order=list(screens))

            body = decoded(response)
            self.assertEqual(response.status, 200)
            self.assertEqual(list(body["ekranlar"]), ["agent-a"])
            self.assertEqual(body["snapshot_meta"]["omitted"]["ekran_dosyalari"], 1)
            self.assertTrue(body["snapshot_meta"]["partial"])
            self.assertIn("screen_output_partial",
                          body["snapshot_meta"]["partial_reasons"])
            # The global projection is a pure response selector. It neither
            # rolls back nor advances the cursor owned by tum_ekranlar().
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-b.jsonl")

            next_screens, _ = self.panel.tum_ekranlar()
            self.assertEqual(list(next_screens), ["agent-c", "agent-d"])
            self.assertEqual(self.panel._EKRAN_SECIM_KURSORU, "agent-d.jsonl")


if __name__ == "__main__":
    unittest.main()
