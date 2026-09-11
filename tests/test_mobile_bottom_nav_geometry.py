import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "app" / "templates" / "base.html"
MOBILE_CSS = ROOT / "app" / "static" / "mobile-only.css"
STYLE_CSS = ROOT / "app" / "static" / "style.css"
SCRIPT_JS = ROOT / "app" / "static" / "script.js"
SERVICE_WORKER = ROOT / "app" / "static" / "service-worker.js"
GLASS_TEMPLATE = ROOT / "app" / "templates" / "glass_measurements.html"
TASK_FORM_TEMPLATE = ROOT / "app" / "templates" / "task_form.html"
ASSIGNMENT_FORM_TEMPLATE = ROOT / "app" / "templates" / "assignment_task_form.html"
ASSIGNMENTS_TEMPLATE = ROOT / "app" / "templates" / "assignments.html"
MY_TASKS_TEMPLATE = ROOT / "app" / "templates" / "my_tasks.html"


class MobileBottomNavGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.style_css = STYLE_CSS.read_text(encoding="utf-8")
        cls.script_js = SCRIPT_JS.read_text(encoding="utf-8")
        cls.service_worker = SERVICE_WORKER.read_text(encoding="utf-8")
        cls.glass_template = GLASS_TEMPLATE.read_text(encoding="utf-8")
        cls.task_form_template = TASK_FORM_TEMPLATE.read_text(encoding="utf-8")
        cls.assignment_form_template = ASSIGNMENT_FORM_TEMPLATE.read_text(encoding="utf-8")
        cls.assignments_template = ASSIGNMENTS_TEMPLATE.read_text(encoding="utf-8")
        cls.my_tasks_template = MY_TASKS_TEMPLATE.read_text(encoding="utf-8")

    def test_nav_markup_does_not_override_shared_anchor(self):
        nav_tags = re.findall(
            r'<nav class="mobile-bottom-nav[^>]+data-mobile-dock="unified"[^>]+>',
            self.base,
        )
        self.assertEqual(len(nav_tags), 2)
        for nav_tag in nav_tags:
            self.assertNotIn("inset:", nav_tag)
            self.assertNotIn("position:", nav_tag)
            self.assertIn("width: 100vw !important", nav_tag)
            self.assertIn("height: 72px !important", nav_tag)

    def test_mobile_safari_web_topbar_matches_the_solid_bottom_nav(self):
        topbar_selector = (
            "html:not(.standalone-app):is(.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device)\n"
            "    body.app-body\n"
            "    :is(.mobile-app-topbar.mobile-shell-topbar, .mobile-project-topbar.mobile-shell-topbar) {"
        )
        topbar_start = self.mobile_css.index(topbar_selector)
        topbar_end = self.mobile_css.index("}", topbar_start)
        topbar_rule = self.mobile_css[topbar_start:topbar_end]
        self.assertIn("background: #111820 !important;", topbar_rule)
        self.assertIn("background-image: none !important;", topbar_rule)
        self.assertIn("box-shadow: none !important;", topbar_rule)
        self.assertIn("backdrop-filter: none !important;", topbar_rule)

        dock_selector = (
            "html body.app-body.app-body.app-body nav.mobile-bottom-nav.mobile-bottom-nav-root"
        )
        dock_start = self.mobile_css.index(dock_selector)
        dock_end = self.mobile_css.index("}", dock_start)
        dock_rule = self.mobile_css[dock_start:dock_end]
        self.assertIn("background: #111820 !important;", dock_rule)

        self.assertNotIn(
            "html.standalone-app:is(.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device)\n"
            "    body.app-body\n"
            "    :is(.mobile-app-topbar.mobile-shell-topbar, .mobile-project-topbar.mobile-shell-topbar) {",
            self.mobile_css,
        )

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

    def test_only_empty_ordered_measurements_use_shared_short_page_geometry(self):
        self.assertIn(
            "{% if tab == 'ordered' and not ordered_rows %} glass-ordered-empty-page mobile-short-page-marker{% endif %}",
            self.glass_template,
        )
        reset_selector_start = self.mobile_css.index(
            ".crm-mobile-page-shell\n"
            "    > :last-child:not(.crm-toast-stack)"
        )
        reset_selector_end = self.mobile_css.index("{", reset_selector_start)
        reset_selector = self.mobile_css[reset_selector_start:reset_selector_end]
        self.assertNotIn(
            ":not(.glass-ordered-empty-page)",
            reset_selector,
        )
        self.assertNotIn(
            "body.app-body:has(.glass-ordered-empty-page)\n"
            "    .crm-mobile-page-shell > .glass-ordered-empty-page",
            self.mobile_css,
        )
        self.assertIn(
            "body.app-body:has(.mobile-short-page-marker)",
            self.mobile_css,
        )

    def test_measurements_do_not_get_a_page_specific_dock_anchor(self):
        glass_dock_selector = re.compile(
            r":has\(\.glass(?:-ordered-empty)?-page\)[^\{]*mobile-bottom-nav"
        )
        self.assertIsNone(glass_dock_selector.search(self.base))
        self.assertIsNone(glass_dock_selector.search(self.mobile_css))

    def test_direct_add_remark_form_uses_shared_short_page_geometry(self):
        self.assertIn(
            "task-single-form mobile-fill-card",
            self.task_form_template,
        )
        self.assertIn(
            "task-add-page mobile-short-page-marker",
            self.task_form_template,
        )
        reset_selector_start = self.mobile_css.index(
            ".crm-mobile-page-shell\n"
            "    > :last-child:not(.crm-toast-stack)"
        )
        reset_selector_end = self.mobile_css.index("{", reset_selector_start)
        reset_selector = self.mobile_css[reset_selector_start:reset_selector_end]
        self.assertNotIn(
            ":not(.task-single-form)",
            reset_selector,
        )
        self.assertNotIn(
            "body.app-body:has(.task-single-form)\n"
            "    .crm-mobile-page-shell > .task-single-form",
            self.mobile_css,
        )
        self.assertIn(
            "body.app-body:has(.mobile-short-page-marker)",
            self.mobile_css,
        )

    def test_add_remark_uses_the_physical_ios_dock_anchor(self):
        body_selector = (
            "body.app-body.app-body.app-body:has(.task-single-form) {"
        )
        dock_selector = re.compile(
            r"body\.app-body\.app-body\.app-body:has\(\.task-single-form\)"
            r"\s*>\s*nav\.mobile-bottom-nav\.mobile-bottom-nav-root"
        )
        for stylesheet in (self.base, self.mobile_css):
            body_start = stylesheet.index(body_selector)
            body_end = stylesheet.index("}", body_start)
            body_rule = stylesheet[body_start:body_end]
            self.assertIn(
                "height: var(--mobile-physical-app-height, 100dvh) !important;",
                body_rule,
            )
            dock_match = dock_selector.search(stylesheet)
            self.assertIsNotNone(dock_match)
            dock_end = stylesheet.index("}", dock_match.start())
            dock_rule = stylesheet[dock_match.start():dock_end]
            self.assertIn("position: absolute !important;", dock_rule)
            self.assertIn(
                "top: calc(var(--mobile-physical-app-height, 100dvh) - 72px) !important;",
                dock_rule,
            )
            self.assertIn("bottom: auto !important;", dock_rule)

    def test_add_assignment_form_uses_shared_short_page_geometry(self):
        self.assertIn(
            "assignment-manual-task-form mobile-fill-card",
            self.assignment_form_template,
        )
        reset_selector_start = self.mobile_css.index(
            ".crm-mobile-page-shell\n"
            "    > :last-child:not(.crm-toast-stack)"
        )
        reset_selector_end = self.mobile_css.index("{", reset_selector_start)
        reset_selector = self.mobile_css[reset_selector_start:reset_selector_end]
        self.assertNotIn(
            ":not(.assignment-manual-task-form)",
            reset_selector,
        )
        self.assertNotIn(
            "body.app-body:has(.assignment-manual-task-form)\n"
            "    .crm-mobile-page-shell > .assignment-manual-task-form",
            self.mobile_css,
        )
        self.assertIn(
            "body.app-body:has(.mobile-form-fill-page) .app-content",
            self.mobile_css,
        )

    def test_add_assignment_uses_the_physical_ios_dock_anchor(self):
        body_selector = (
            "body.app-body.app-body.app-body:has(.assignment-manual-task-form) {"
        )
        dock_selector = re.compile(
            r"body\.app-body\.app-body\.app-body:has\(\.assignment-manual-task-form\)"
            r"\s*>\s*nav\.mobile-bottom-nav\.mobile-bottom-nav-root"
        )
        for stylesheet in (self.base, self.mobile_css):
            body_start = stylesheet.index(body_selector)
            body_end = stylesheet.index("}", body_start)
            body_rule = stylesheet[body_start:body_end]
            self.assertIn(
                "height: var(--mobile-physical-app-height, 100dvh) !important;",
                body_rule,
            )
            dock_match = dock_selector.search(stylesheet)
            self.assertIsNotNone(dock_match)
            dock_end = stylesheet.index("}", dock_match.start())
            dock_rule = stylesheet[dock_match.start():dock_end]
            self.assertIn("position: absolute !important;", dock_rule)
            self.assertIn(
                "top: calc(var(--mobile-physical-app-height, 100dvh) - 72px) !important;",
                dock_rule,
            )
            self.assertIn("bottom: auto !important;", dock_rule)

    def test_add_assignment_dropdowns_are_regular_weight_in_mobile_pwa(self):
        selector = (
            "html.standalone-app:is(.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device)\n"
            "    body.app-body:has(.assignment-manual-task-form)\n"
            "    :is("
        )
        selector_start = self.mobile_css.rindex(selector)
        rule_end = self.mobile_css.index("}", selector_start)
        rule = self.mobile_css[selector_start:rule_end]
        for control in (
            ".assignment-manual-task-form select option",
            ".assignment-manual-task-form .developer-select-button *",
            ".assignment-manual-task-form .developer-select-value",
            ".assignment-manual-task-form .global-date-button *",
            ".assignment-manual-task-form .global-date-value",
            ".developer-select-menu-portal .developer-select-option",
        ):
            self.assertIn(control, rule)
        self.assertIn("font-weight: 400 !important;", rule)

    def test_only_empty_issued_assignments_use_shared_short_page_geometry(self):
        self.assertIn(
            "{% if issued_page_empty %} class=\"assignment-issued-empty-page\"{% endif %}",
            self.assignments_template,
        )
        self.assertIn(
            "view_mode == 'issued' and",
            self.assignments_template,
        )
        self.assertIn(
            "assignment-issued-layout-empty mobile-empty-results-page mobile-short-page-marker",
            self.assignments_template,
        )
        reset_selector_start = self.mobile_css.index(
            ".crm-mobile-page-shell\n"
            "    > :last-child:not(.crm-toast-stack)"
        )
        reset_selector_end = self.mobile_css.index("{", reset_selector_start)
        reset_selector = self.mobile_css[reset_selector_start:reset_selector_end]
        self.assertNotIn(
            ":not(.assignment-issued-empty-page)",
            reset_selector,
        )
        self.assertNotIn(
            "body.app-body.app-body:has(.assignment-issued-empty-page)\n"
            "    .crm-mobile-page-shell > .assignment-issued-empty-page",
            self.mobile_css,
        )
        self.assertIn(
            "body.app-body:has(.mobile-short-page-marker)",
            self.mobile_css,
        )

    def test_empty_issued_assignments_anchor_the_dock_to_the_full_canvas(self):
        body_selector = (
            "body.app-body.app-body.app-body:has(.assignment-issued-layout-empty) {"
        )
        selector = re.compile(
            r"body\.app-body\.app-body\.app-body:has\(\.assignment-issued-layout-empty\)"
            r"\s*>\s*nav\.mobile-bottom-nav\.mobile-bottom-nav-root"
        )
        for stylesheet in (self.base, self.mobile_css):
            body_rules = []
            for match in re.finditer(re.escape(body_selector), stylesheet):
                body_end = stylesheet.index("}", match.end())
                body_rules.append(stylesheet[match.end():body_end])
            body_rule = next(
                rule
                for rule in body_rules
                if "var(--mobile-physical-app-height" in rule
            )
            self.assertIn(
                "min-height: var(--mobile-physical-app-height, 100dvh) !important;",
                body_rule,
            )
            self.assertIn(
                "height: var(--mobile-physical-app-height, 100dvh) !important;",
                body_rule,
            )
            self.assertIn(
                "max-height: var(--mobile-physical-app-height, 100dvh) !important;",
                body_rule,
            )
            selector_match = selector.search(stylesheet)
            self.assertIsNotNone(selector_match)
            selector_start = selector_match.start()
            rule_end = stylesheet.index("}", selector_start)
            rule = stylesheet[selector_start:rule_end]
            self.assertIn("position: absolute !important;", rule)
            self.assertIn(
                "top: calc(var(--mobile-physical-app-height, 100dvh) - 72px) !important;",
                rule,
            )
            self.assertIn("bottom: auto !important;", rule)
            self.assertIn(
                "inset: calc(var(--mobile-physical-app-height, 100dvh) - 72px) 0 auto 0 !important;",
                rule,
            )

    def test_empty_issued_assignments_measure_the_physical_ios_canvas(self):
        physical_height_expression = (
            "Math.max(layoutViewportHeight, visualViewportHeight, "
            "deviceScreenHeight, deviceAvailableHeight)"
        )
        self.assertIn(physical_height_expression, self.base)
        self.assertIn(
            "document.documentElement.style.setProperty('--mobile-physical-app-height'",
            self.base,
        )
        self.assertIn(physical_height_expression, self.script_js)
        self.assertIn(
            "document.documentElement.style.setProperty('--mobile-physical-app-height'",
            self.script_js,
        )

    def test_empty_issued_assignments_override_the_dark_root_canvas(self):
        selector = (
            "html body.app-body.app-body.app-body:has(.assignment-issued-layout-empty)"
        )
        selector_start = self.mobile_css.index(selector)
        rule_end = self.mobile_css.index("}", selector_start)
        rule = self.mobile_css[selector_start:rule_end]
        self.assertIn("background: #f6f8fb !important;", rule)
        self.assertIn("background-color: #f6f8fb !important;", rule)

    def test_all_worker_roles_share_the_unified_two_item_dock(self):
        self.assertIn("{% if worker_role %}", self.base)
        worker_nav = re.search(
            r'<nav class="mobile-bottom-nav mobile-bottom-nav-root mobile-worker-bottom-nav"[^>]+>',
            self.base,
        )
        self.assertIsNotNone(worker_nav)
        worker_nav_markup = worker_nav.group(0)
        self.assertIn("--mobile-nav-count: 2", worker_nav_markup)
        self.assertIn("width: 100vw !important", worker_nav_markup)
        self.assertIn("height: 72px !important", worker_nav_markup)

    def test_all_worker_pages_override_the_dark_root_canvas(self):
        selector = (
            "html body.app-body.app-body.app-body:has(.mobile-worker-bottom-nav)"
        )
        selector_start = self.mobile_css.index(selector)
        rule_end = self.mobile_css.index("}", selector_start)
        rule = self.mobile_css[selector_start:rule_end]
        self.assertIn("background: #f6f8fb !important;", rule)
        self.assertIn("background-color: #f6f8fb !important;", rule)
        for role in ("handyman", "painter", "glazier"):
            self.assertIn(f"'{role}'", self.base)

    def test_empty_worker_tasks_paint_the_light_canvas_to_shared_dock(self):
        self.assertIn(
            "worker-page-empty mobile-short-page-marker",
            self.my_tasks_template,
        )
        self.assertIn(
            "body.app-body:has(.mobile-short-page-marker)",
            self.mobile_css,
        )
        self.assertIn(
            "body.app-body:has(.worker-page-empty) .worker-empty-card",
            self.mobile_css,
        )
        self.assertIn(
            ":has(.mobile-worker-bottom-nav):has(:is(.account-page, .worker-page-empty))",
            self.mobile_css,
        )

    def test_worker_account_and_empty_tasks_use_the_physical_ios_dock_anchor(self):
        body_selector = (
            "body.app-body.app-body.app-body:has(.mobile-worker-bottom-nav)"
            ":has(:is(.account-page, .worker-page-empty)) {"
        )
        dock_selector = re.compile(
            r"body\.app-body\.app-body\.app-body:has\(\.mobile-worker-bottom-nav\)"
            r":has\(:is\(\.account-page, \.worker-page-empty\)\)"
            r"\s*>\s*nav\.mobile-bottom-nav\.mobile-bottom-nav-root"
        )
        for stylesheet in (self.base, self.mobile_css):
            body_start = stylesheet.index(body_selector)
            body_end = stylesheet.index("}", body_start)
            body_rule = stylesheet[body_start:body_end]
            self.assertIn(
                "height: var(--mobile-physical-app-height, 100dvh) !important;",
                body_rule,
            )
            dock_match = dock_selector.search(stylesheet)
            self.assertIsNotNone(dock_match)
            dock_end = stylesheet.index("}", dock_match.start())
            dock_rule = stylesheet[dock_match.start():dock_end]
            self.assertIn("position: absolute !important;", dock_rule)
            self.assertIn(
                "top: calc(var(--mobile-physical-app-height, 100dvh) - 72px) !important;",
                dock_rule,
            )
            self.assertIn("bottom: auto !important;", dock_rule)

    def test_pwa_cache_uses_the_same_mobile_stylesheet_version(self):
        version_pattern = r"mobile-only\.css[^\n]*\?v=(v[\w-]+)"
        template_version = re.search(version_pattern, self.base)
        worker_version = re.search(version_pattern, self.service_worker)
        self.assertIsNotNone(template_version)
        self.assertIsNotNone(worker_version)
        self.assertEqual(template_version.group(1), worker_version.group(1))
        service_worker_version = re.search(r"service-worker\.js\?v=(v[\w-]+)", self.base)
        static_cache_version = re.search(r"peredacha-static-(v[\w-]+)", self.service_worker)
        self.assertIsNotNone(service_worker_version)
        self.assertIsNotNone(static_cache_version)
        self.assertEqual(service_worker_version.group(1), static_cache_version.group(1))


if __name__ == "__main__":
    unittest.main()
