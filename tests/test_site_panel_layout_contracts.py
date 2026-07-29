import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "app" / "templates" / "base.html"
STYLE_CSS = ROOT / "app" / "static" / "style.css"
MOBILE_CSS = ROOT / "app" / "static" / "mobile-only.css"
DESKTOP_CSS = ROOT / "app" / "static" / "desktop-only.css"


PRIMARY_MOBILE_ENDPOINTS = {
    "home": "main.dashboard",
    "remarks": "main.task_list",
    "assignments": "main.assignments",
    "apartments": "main.apartments",
}

DESKTOP_SIDEBAR_ENDPOINTS = {
    "home": "main.dashboard",
    "remarks": "main.task_list",
    "contractors": "main.contractors_list",
    "apartments": "main.apartments",
    "avr": "main.avr",
    "materials": "main.materials",
    "glass": "main.glass_measurements",
    "assignments": "main.assignments",
    "report": "main.work_report",
}

MOBILE_PANEL_PAGE_MARKERS = (
    ".task-detail-page",
    ".apartment-detail-page",
    ".objects-page",
    ".materials-page",
    ".work-report-page",
    ".documents-page",
    ".settings-page-shell",
    ".users-page",
    ".sync-logs-page",
    ".assignment-report-page",
    ".glass-page",
    ".account-page",
)


def _css_rule(source: str, selector: str) -> str:
    start = source.index(selector)
    end = source.index("}", start)
    return source[start:end]


class SitePanelLayoutContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.style_css = STYLE_CSS.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")

    def test_every_authenticated_layout_renders_mobile_topbar_and_bottom_dock(self):
        authenticated_layouts = (
            "{% if current_user.is_authenticated and layout_mode.strip() == 'objects' %}",
            "{% elif current_user.is_authenticated and (layout_mode.strip() in ['documents', 'settings'] or request.endpoint in ['main.account', 'main.site_settings']) %}",
            "{% elif current_user.is_authenticated %}",
        )
        for marker in authenticated_layouts:
            with self.subTest(layout=marker):
                layout_start = self.base.index(marker)
                dock_start = self.base.index("{{ mobile_bottom_nav(mobile_active) }}", layout_start)
                layout_block = self.base[layout_start:dock_start + len("{{ mobile_bottom_nav(mobile_active) }}")]

                self.assertIn("{{ mobile_page_chrome(mobile_title) }}", layout_block)
                self.assertIn("{{ mobile_bottom_nav(mobile_active) }}", layout_block)

    def test_mobile_primary_tabs_include_home_and_keep_stable_order(self):
        primary_nav_start = self.base.index("{% else %}\n    <a class=\"mobile-nav-item mobile-nav-item-home")
        primary_nav_end = self.base.index("{% endif %}\n  </nav>", primary_nav_start)
        primary_nav = self.base[primary_nav_start:primary_nav_end]

        previous_position = -1
        for tab, endpoint in PRIMARY_MOBILE_ENDPOINTS.items():
            with self.subTest(tab=tab):
                position = primary_nav.index(f"url_for('{endpoint}')")
                self.assertGreater(position, previous_position)
                previous_position = position

        self.assertIn("mobile-nav-item-home", primary_nav)
        self.assertIn("active == 'dashboard'", primary_nav)
        self.assertIn("4 if current_user.role in ['admin', 'manager'] else 3", self.base)

    def test_mobile_active_tab_map_covers_all_site_sections_including_home(self):
        endpoint_to_active_tab = {
            "main.dashboard": "dashboard",
            "main.task_list": "remarks",
            "main.task_detail": "remarks",
            "main.task_new": "remarks",
            "main.task_recognition": "remarks",
            "main.apartments": "apartments",
            "main.apartment_detail": "apartments",
            "main.materials": "materials",
            "main.glass_measurements": "glass",
            "main.assignments": "assignments",
            "main.work_report": "report",
            "main.account": "account",
            "main.objects": "objects",
            "main.site_settings": "objects",
        }
        for endpoint, active_tab in endpoint_to_active_tab.items():
            with self.subTest(endpoint=endpoint):
                endpoint_pos = self.base.index(endpoint)
                active_pos = self.base.find(f"mobile_active = '{active_tab}'", endpoint_pos)
                self.assertNotEqual(active_pos, -1)
        self.assertIn("layout_mode.strip() == 'documents'", self.base)
        self.assertIn("mobile_active = 'objects'", self.base)

    def test_mobile_bottom_dock_geometry_is_identical_in_critical_inline_and_external_css(self):
        selectors = (
            "html body.app-body nav.mobile-bottom-nav-root",
            "html body.app-body.app-body.app-body nav.mobile-bottom-nav.mobile-bottom-nav-root",
        )
        for source_name, source, selector in (
            ("base inline css", self.base, selectors[0]),
            ("mobile css", self.mobile_css, selectors[1]),
        ):
            with self.subTest(source=source_name):
                rule = _css_rule(source, selector)
                self.assertIn("position: fixed !important", rule)
                self.assertIn("z-index: 2147481000 !important", rule)
                self.assertIn("grid-template-columns: repeat(var(--mobile-nav-count, 4), minmax(0, 1fr)) !important", rule)
                self.assertIn("inset: auto 0 0 0 !important", rule)
                self.assertIn("width: 100vw !important", rule)
                self.assertIn("height: 72px !important", rule)
                self.assertIn("transform: none !important", rule)

    def test_mobile_content_reserves_space_for_panels_on_all_major_tabs(self):
        clearance_rule = _css_rule(
            self.style_css,
            "html:is(.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device) body.app-body:has(:is(.task-detail-page",
        )
        for marker in MOBILE_PANEL_PAGE_MARKERS:
            with self.subTest(page_marker=marker):
                self.assertIn(marker, clearance_rule)
        self.assertIn("padding-bottom: calc((var(--ref-mobile-nav-height", clearance_rule)

        self.assertIn("body.app-body:has(.dashboard-page.dashboard-redesign) .app-main", self.style_css)
        self.assertIn("padding-top: var(--ref-mobile-topbar-height", self.style_css)
        self.assertIn("body.app-body:has(.dashboard-page.dashboard-redesign) .app-content", self.style_css)

    def test_desktop_sidebar_has_home_and_all_web_tabs_with_fixed_shell_geometry(self):
        sidebar_start = self.base.index("<nav class=\"sidebar-nav\">")
        sidebar_end = self.base.index("</nav>", sidebar_start)
        sidebar = self.base[sidebar_start:sidebar_end]

        for tab, endpoint in DESKTOP_SIDEBAR_ENDPOINTS.items():
            with self.subTest(tab=tab):
                self.assertIn(f"url_for('{endpoint}')", sidebar)

        home_link = re.search(
            r"<a class=\"sidebar-link[^\"]*request\.endpoint == 'main\.dashboard'[^\"]*\" "
            r"href=\"{{ url_for\('main\.dashboard'\) }}\"",
            sidebar,
        )
        self.assertIsNotNone(home_link)

    def test_desktop_web_shell_pins_top_panel_and_reserves_content_offset(self):
        sidebar_rule = _css_rule(
            self.desktop_css,
            "html.desktop-like-pointer body.app-body .app-layout > .app-sidebar",
        )
        self.assertIn("position: fixed !important", sidebar_rule)
        self.assertIn("inset: 0 auto 0 0 !important", sidebar_rule)
        self.assertIn("width: var(--desktop-sidebar-width, 230px) !important", sidebar_rule)

        app_main_rule = _css_rule(
            self.desktop_css,
            "html.desktop-like-pointer body.app-body .app-layout > .app-main",
        )
        self.assertIn("margin-left: var(--desktop-sidebar-width, 230px) !important", app_main_rule)
        self.assertIn("padding-top: 4.9rem !important", app_main_rule)

        app_topbar_rule = _css_rule(
            self.desktop_css,
            "html.desktop-like-pointer body.app-body .app-layout > .app-main > .app-topbar",
        )
        self.assertIn("position: fixed !important", app_topbar_rule)
        self.assertIn("inset: 0 auto auto var(--desktop-sidebar-width, 230px) !important", app_topbar_rule)
        self.assertIn("height: 4.9rem !important", app_topbar_rule)

    def test_desktop_objects_documents_and_settings_keep_their_topbar_anchor(self):
        standalone_layout_rule = _css_rule(
            self.desktop_css,
            "html.desktop-like-pointer body.app-body\n    :is(.objects-layout, .documents-standalone-layout, .settings-standalone-layout)",
        )
        self.assertIn("padding-top: 5.75rem !important", standalone_layout_rule)
        self.assertIn("min-height: calc(100vh / var(--desktop-stage-scale, 1)) !important", standalone_layout_rule)

        standalone_topbar_rule = _css_rule(
            self.desktop_css,
            "html.desktop-like-pointer body.app-body\n    :is(.objects-layout, .documents-standalone-layout, .settings-standalone-layout)\n    > .objects-topbar",
        )
        self.assertIn("position: fixed !important", standalone_topbar_rule)
        self.assertIn("inset: 0 auto auto 0 !important", standalone_topbar_rule)
        self.assertIn("height: 5.75rem !important", standalone_topbar_rule)
        self.assertIn("width: var(--desktop-reference-width, 1920px) !important", standalone_topbar_rule)


if __name__ == "__main__":
    unittest.main()
