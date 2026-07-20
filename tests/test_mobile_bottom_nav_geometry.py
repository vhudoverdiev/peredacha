import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = ROOT / "app" / "templates" / "base.html"
MOBILE_CSS = ROOT / "app" / "static" / "mobile-only.css"
STYLE_CSS = ROOT / "app" / "static" / "style.css"
SERVICE_WORKER = ROOT / "app" / "static" / "service-worker.js"
GLASS_TEMPLATE = ROOT / "app" / "templates" / "glass_measurements.html"
TASK_FORM_TEMPLATE = ROOT / "app" / "templates" / "task_form.html"
ASSIGNMENT_FORM_TEMPLATE = ROOT / "app" / "templates" / "assignment_task_form.html"
ASSIGNMENTS_TEMPLATE = ROOT / "app" / "templates" / "assignments.html"


class MobileBottomNavGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.style_css = STYLE_CSS.read_text(encoding="utf-8")
        cls.service_worker = SERVICE_WORKER.read_text(encoding="utf-8")
        cls.glass_template = GLASS_TEMPLATE.read_text(encoding="utf-8")
        cls.task_form_template = TASK_FORM_TEMPLATE.read_text(encoding="utf-8")
        cls.assignment_form_template = ASSIGNMENT_FORM_TEMPLATE.read_text(encoding="utf-8")
        cls.assignments_template = ASSIGNMENTS_TEMPLATE.read_text(encoding="utf-8")

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

    def test_add_remark_does_not_get_a_page_specific_dock_anchor(self):
        task_dock_selector = re.compile(
            r":has\(\.task-single-form\)[^\{]*mobile-bottom-nav-root"
        )
        self.assertIsNone(task_dock_selector.search(self.base))
        self.assertIsNone(task_dock_selector.search(self.mobile_css))

    def test_add_assignment_form_keeps_iphone_safe_area(self):
        self.assertIn(
            "assignment-manual-task-form mobile-fill-card",
            self.assignment_form_template,
        )
        self.assertIn(
            ":not(.account-page):not(.assignment-manual-task-form)",
            self.mobile_css,
        )
        selector = (
            "body.app-body:has(.assignment-manual-task-form)\n"
            "    .crm-mobile-page-shell > .assignment-manual-task-form"
        )
        selector_start = self.mobile_css.index(selector)
        rule_end = self.mobile_css.index("}", selector_start)
        rule = self.mobile_css[selector_start:rule_end]
        self.assertIn(
            "padding-bottom: var(--ios-safe-bottom, env(safe-area-inset-bottom, 0px)) !important;",
            rule,
        )

    def test_add_assignment_does_not_get_a_page_specific_dock_anchor(self):
        assignment_dock_selector = re.compile(
            r":has\(\.assignment-manual-task-form\)[^\{]*mobile-bottom-nav-root"
        )
        self.assertIsNone(assignment_dock_selector.search(self.base))
        self.assertIsNone(assignment_dock_selector.search(self.mobile_css))

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

    def test_empty_issued_assignments_do_not_get_a_page_specific_dock_anchor(self):
        assignment_empty_dock_selector = re.compile(
            r":has\(\.assignment-issued-empty-page\)[^\{]*mobile-bottom-nav-root"
        )
        self.assertIsNone(assignment_empty_dock_selector.search(self.base))
        self.assertIsNone(assignment_empty_dock_selector.search(self.mobile_css))

    def test_pwa_cache_uses_the_same_mobile_stylesheet_version(self):
        version_pattern = r"mobile-only\.css[^\n]*\?v=(v[\w-]+)"
        template_version = re.search(version_pattern, self.base)
        worker_version = re.search(version_pattern, self.service_worker)
        self.assertIsNotNone(template_version)
        self.assertIsNotNone(worker_version)
        self.assertEqual(template_version.group(1), worker_version.group(1))


if __name__ == "__main__":
    unittest.main()
