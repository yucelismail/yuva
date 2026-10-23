import importlib.util
from importlib.machinery import SourceFileLoader
import json
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = ROOT / "panel" / "server.py"
UI_PATH = ROOT / "panel" / "ui.html"


def load_panel():
    name = "yuva_panel_revision_validation_fixture"
    spec = importlib.util.spec_from_file_location(
        name, PANEL_PATH, loader=SourceFileLoader(name, str(PANEL_PATH)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TagsAndText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attrs = []
        self.data = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)

    def handle_data(self, data):
        self.data.append(data)


class PanelRevisionValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yuva-revision-")
        self.data = Path(self.temp.name)
        self.panel = load_panel()
        self.durum_path = self.data / "durum.json"

    def tearDown(self):
        self.temp.cleanup()

    def _read(self, document):
        self.durum_path.write_text(json.dumps(document), encoding="utf-8")
        with patch.object(self.panel, "DURUM", self.durum_path):
            return self.panel.durum_oku()

    def test_revision_defaults_to_zero_and_accepts_nonnegative_integer_only(self):
        self.durum_path.unlink(missing_ok=True)
        with patch.object(self.panel, "DURUM", self.durum_path):
            self.assertEqual(self.panel.durum_oku()["rev"], 0)
        self.assertEqual(self._read({"kullanicilar": {}, "rev": 0})["rev"], 0)
        self.assertEqual(self._read({"kullanicilar": {}, "rev": 123})["rev"], 123)

    def test_string_object_boolean_float_and_negative_revisions_are_rejected(self):
        sentinel = '"><img src=x onerror=alert(1)>'
        invalid = (sentinel, {"html": sentinel}, True, False, 1.5, -1)
        for revision in invalid:
            with self.subTest(revision=type(revision).__name__):
                with self.assertRaisesRegex(self.panel.DurumHatasi,
                                            "rev.*negatif olmayan tamsayı"):
                    self._read({"kullanicilar": {}, "rev": revision})

    def test_ui_summary_validates_revision_and_escapes_both_render_paths(self):
        source = UI_PATH.read_text(encoding="utf-8")
        helper = source[source.index("function revGorunen(rev){"):
                        source.index("function saat(ts){")]
        render = source[source.index("function ciz(){"):
                        source.index("function presenceOzetMetni(")]
        self.assertIn('Number.isSafeInteger(rev)&&rev>=0?String(rev):"?"', helper)
        self.assertEqual(render.count("esc(revGorunen(veri.rev))"), 2)
        self.assertNotIn("(veri.rev||0)", render)

        # The invalid-snapshot display fallback is fixed text; HTML parsing
        # therefore cannot create a tag or event attribute from the revision.
        parser = TagsAndText()
        parser.feed("<span>rev ?</span>")
        self.assertEqual(parser.tags, ["span"])
        self.assertEqual(parser.attrs, [])
        self.assertEqual("".join(parser.data), "rev ?")


if __name__ == "__main__":
    unittest.main()
