import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "app" / "templates" / "base.html"
MOBILE_CSS = ROOT / "app" / "static" / "mobile-only.css"
SERVICE_WORKER = ROOT / "app" / "static" / "service-worker.js"


class MobileBottomNavGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.service_worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_nav_markup_does_not_override_page_specific_inset(self):
        nav_tags = re.findall(
            r'<nav class="mobile-bottom-nav[^>]+data-mobile-dock="unified"[^>]+>',
            self.base,
        )
        self.assertEqual(len(nav_tags), 2)
        for nav_tag in nav_tags:
            self.assertNotIn("inset:", nav_tag)
            self.assertIn("width: 100vw !important", nav_tag)
            self.assertIn("height: 72px !important", nav_tag)

    def test_account_dock_is_top_anchored_in_critical_and_final_css(self):
        selector = (
            "html.standalone-app body.app-body:has(.account-page) "
            "nav.mobile-bottom-nav-root"
        )
        expected_top = (
            "top: calc(var(--mobile-layout-height, 100dvh) - "
            "var(--ref-mobile-nav-height, 72px)) !important;"
        )
        for stylesheet in (self.base, self.mobile_css):
            self.assertIn(selector, stylesheet)
            selector_start = stylesheet.index(selector)
            rule_end = stylesheet.index("}", selector_start)
            rule = stylesheet[selector_start:rule_end]
            self.assertIn(expected_top, rule)
            self.assertIn("bottom: auto !important;", rule)

    def test_pwa_cache_uses_the_same_mobile_stylesheet_version(self):
        version_pattern = r"mobile-only\.css[^\n]*\?v=(v[\w-]+)"
        template_version = re.search(version_pattern, self.base)
        worker_version = re.search(version_pattern, self.service_worker)
        self.assertIsNotNone(template_version)
        self.assertIsNotNone(worker_version)
        self.assertEqual(template_version.group(1), worker_version.group(1))


if __name__ == "__main__":
    unittest.main()
