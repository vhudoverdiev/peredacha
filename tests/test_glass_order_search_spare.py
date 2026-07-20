import unittest
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
MOBILE_CSS = PROJECT_ROOT / "app" / "static" / "mobile-only.css"
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class GlassOrderSearchSpareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.service_worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_hidden_ajax_spares_stay_hidden_on_desktop_glass_page(self):
        selector = (
            "html.desktop-like-pointer body.app-body\n"
            "    .glass-page [data-ajax-pagination-spare][hidden]"
        )
        selector_start = self.desktop_css.index(selector)
        rule_end = self.desktop_css.index("}", selector_start)
        rule = self.desktop_css[selector_start:rule_end]

        self.assertIn("display: none !important", rule)

    def test_mobile_styles_are_untouched(self):
        self.assertNotIn("data-ajax-pagination-spare", self.mobile_css)

    def test_pwa_cache_uses_the_same_desktop_stylesheet_version(self):
        version_pattern = r"desktop-only\.css[^\n]*\?v=(v[\w-]+)"
        template_version = re.search(version_pattern, self.base)
        worker_version = re.search(version_pattern, self.service_worker)

        self.assertIsNotNone(template_version)
        self.assertIsNotNone(worker_version)
        self.assertEqual(template_version.group(1), worker_version.group(1))


if __name__ == "__main__":
    unittest.main()
