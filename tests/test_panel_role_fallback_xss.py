from html import escape
from html.parser import HTMLParser
from pathlib import Path
import unittest


UI_PATH = Path(__file__).resolve().parents[1] / "panel" / "ui.html"


class RenderedFragment(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attributes = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)

    def handle_data(self, data):
        self.text.append(data)


class PanelRoleFallbackXssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = UI_PATH.read_text(encoding="utf-8")

    def test_unknown_role_fallback_is_escaped_in_target_and_person_card(self):
        source = self.source
        role_label = source[source.index("function rolGorunen(rol){"):
                            source.index("function saat(ts){")]
        target_renderer = source[source.index("function hedefCiz(kimlikler,ks){"):
                                 source.index("function sohbetCiz(veri){")]
        card_renderer = source[source.index("function modelKart(k,v,veri){"):
                               source.index("function ekipCiz(veri,ks,kimlikler){")]

        self.assertIn('typeof rol!=="string"', role_label)
        self.assertIn('Object.prototype.hasOwnProperty.call(ROL_AD,rol)?ROL_AD[rol]:rol',
                      role_label)
        self.assertIn('esc(rolGorunen(v.rol))', target_renderer)
        self.assertIn('esc(rolGorunen(v.rol))', card_renderer)

        sentinel = '"><img src=x onerror=alert(1)>'
        for wrapper in ("option", "div"):
            with self.subTest(wrapper=wrapper):
                parser = RenderedFragment()
                parser.feed("<" + wrapper + ">" + escape(sentinel, quote=True)
                            + "</" + wrapper + ">")
                self.assertEqual(parser.tags, [wrapper])
                self.assertEqual(parser.attributes, [])
                self.assertEqual("".join(parser.text), sentinel)

    def test_fallback_is_not_interpolated_as_raw_html(self):
        source = self.source
        target_renderer = source[source.index("function hedefCiz(kimlikler,ks){"):
                                 source.index("function sohbetCiz(veri){")]
        card_renderer = source[source.index("function modelKart(k,v,veri){"):
                               source.index("function ekipCiz(veri,ks,kimlikler){")]
        self.assertNotIn('(ROL_AD[v.rol]||v.rol)', target_renderer)
        self.assertNotIn('(ROL_AD[v.rol]||v.rol)', card_renderer)


if __name__ == "__main__":
    unittest.main()
