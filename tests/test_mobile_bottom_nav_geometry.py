import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "app" / "templates" / "base.html"
MOBILE_CSS = ROOT / "app" / "static" / "mobile-only.css"
STYLE_CSS = ROOT / "app" / "static" / "style.css"
SERVICE_WORKER = ROOT / "app" / "static" / "service-worker.js"


class MobileBottomNavGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.style_css = STYLE_CSS.read_text(encoding="utf-8")
        cls.service_worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_nav_markup_does_not_override_shared_anchor(self):
        nav_tags = re.findall(
            r'<nav class="mobile-bottom-nav[^>]+data-mobile-dock="unified"[^>]+>',
            self.base,
        )
        self.assertEqual(len(nav_tags), 2)
        for nav_tag in nav_tags:
            self.assertNotIn("inset:", nav_tag)
            self.assertIn("width: 100vw !important", nav_tag)
            self.assertIn("height: 72px !important", nav_tag)

    def test_account_dock_uses_the_same_bottom_anchor_as_objects(self):
        account_dock_selector = re.compile(
            r"has-account-page[^\{]*mobile-bottom-nav-root|"
            r":has\(\.account-page\)[^\{]*mobile-bottom-nav-root"
        )
        self.assertIsNone(account_dock_selector.search(self.base))
        self.assertIsNone(account_dock_selector.search(self.mobile_css))

    def test_account_page_keeps_exactly_its_safe_area_clearance(self):
        self.assertIn(
            "padding: .2rem .2rem calc(1.35rem + var(--ios-safe-bottom)) !important;",
            self.style_css,
        )
        self.assertIn(
            ":last-child:not(.crm-toast-stack):not(.account-page)",
            self.mobile_css,
        )
        self.assertIn(
            "padding-bottom: var(--ios-safe-bottom, env(safe-area-inset-bottom, 0px)) !important;",
            self.mobile_css,
        )

    def test_pwa_cache_uses_the_same_mobile_stylesheet_version(self):
        version_pattern = r"mobile-only\.css[^\n]*\?v=(v[\w-]+)"
        template_version = re.search(version_pattern, self.base)
        worker_version = re.search(version_pattern, self.service_worker)
        self.assertIsNotNone(template_version)
        self.assertIsNotNone(worker_version)
        self.assertEqual(template_version.group(1), worker_version.group(1))


if __name__ == "__main__":
    unittest.main()
