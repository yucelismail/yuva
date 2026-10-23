from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


UI = Path(__file__).resolve().parents[1] / "panel" / "ui.html"


class PanelFixture(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buttons = {}
        self.panels = {}
        self.nav = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav" and attrs.get("id") == "sekmeler":
            self.nav = attrs
        if tag == "button" and attrs.get("data-s"):
            self.buttons[attrs["data-s"]] = attrs
        if tag == "div" and attrs.get("id", "").startswith("b-"):
            self.panels[attrs["id"]] = attrs


class PanelUiAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = UI.read_text(encoding="utf-8")
        cls.fixture = PanelFixture()
        cls.fixture.feed(cls.source)

    def test_section_buttons_expose_selection_and_label_their_panels(self):
        fixture = self.fixture
        self.assertEqual(fixture.nav.get("aria-label"), "Panel bölümleri")
        self.assertEqual(set(fixture.buttons), {"ekip", "tahta", "ekran", "harita"})
        self.assertEqual(set(fixture.panels), {"b-ekip", "b-tahta", "b-ekran", "b-harita"})
        for name, button in fixture.buttons.items():
            with self.subTest(section=name):
                self.assertEqual(button.get("aria-controls"), f"b-{name}")
                self.assertEqual(fixture.panels[f"b-{name}"].get("aria-labelledby"), button["id"])
                self.assertEqual(button.get("aria-pressed"), "true" if name == "ekip" else "false")
        self.assertRegex(self.source, re.compile(
            r'x\.setAttribute\("aria-pressed",x===b\?"true":"false"\)'))

    def test_narrow_layout_keeps_chat_and_panel_inside_two_bounded_rows(self):
        mobile = re.search(r"@media \(max-width:900px\)\{(.*?)\n}", self.source, re.S)
        self.assertIsNotNone(mobile)
        rules = mobile.group(1)
        self.assertIn("grid-template-rows:minmax(0,42%) minmax(0,1fr)", rules)
        self.assertIn("#sol,#sag{min-width:0;min-height:0}", rules)
        self.assertIn("#sol{border-right:0;border-bottom:1px solid var(--brd);max-height:none}", rules)
        self.assertIn(".bolum{max-height:none}", rules)


if __name__ == "__main__":
    unittest.main()
