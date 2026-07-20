import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class DesktopNativeTableRowLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_every_clickable_table_row_gets_real_links_on_desktop(self):
        start = self.script.index("const initDesktopNativeTableRowLinks")
        end = self.script.index("const rememberInstantMobileEntryForNextNavigation", start)
        section = self.script[start:end]

        self.assertIn("if (isTouchAppDevice()) return", section)
        self.assertIn("tr[data-href]", section)
        self.assertIn("document.createElement('a')", section)
        self.assertIn("link.href = href", section)
        self.assertIn("desktop-native-row-links", section)

    def test_plain_clicks_are_forwarded_but_new_tab_gestures_stay_native(self):
        start = self.script.index("const forwardOriginalPointerEvent")
        end = self.script.index("cell.appendChild(link)", start)
        section = self.script[start:end]

        self.assertIn("event.button !== 0", section)
        self.assertIn("event.metaKey", section)
        self.assertIn("event.ctrlKey", section)
        self.assertIn("event.shiftKey", section)
        self.assertIn("document.elementFromPoint", section)
        self.assertIn("new MouseEvent(event.type", section)
        self.assertIn("link.addEventListener('click'", section)
        self.assertIn("link.addEventListener('dblclick'", section)

    def test_ajax_replaced_and_new_manual_rows_are_initialized(self):
        self.assertIn("document.addEventListener('crm:ajax-pagination-updated'", self.script)
        self.assertIn("initDesktopNativeTableRowLinks(event.detail?.content || document)", self.script)
        self.assertIn("initDesktopNativeTableRowLinks(row);", self.script)

    def test_hit_area_styles_are_isolated_to_desktop_marker(self):
        self.assertIn(
            "html.desktop-native-row-links body.app-body .desktop-native-row-link-cell",
            self.desktop_css,
        )
        self.assertIn("> .desktop-native-row-link", self.desktop_css)
        self.assertIn("position: absolute;", self.desktop_css)
        self.assertIn("inset: 0;", self.desktop_css)
        self.assertNotIn("desktop-native-row-link", (PROJECT_ROOT / "app" / "static" / "mobile-only.css").read_text(encoding="utf-8"))

    def test_changed_assets_have_synchronized_cache_busters(self):
        script_template = re.search(r"script\.js'\) }}\?v=([^\"]+)", self.base).group(1)
        script_worker = re.search(r"/static/script\.js\?v=([^']+)", self.worker).group(1)
        css_template = re.search(r"desktop-only\.css'\) }}\?v=([^\"]+)", self.base).group(1)
        css_worker = re.search(r"/static/desktop-only\.css\?v=([^']+)", self.worker).group(1)

        self.assertEqual(script_template, script_worker)
        self.assertEqual(css_template, css_worker)


if __name__ == "__main__":
    unittest.main()
