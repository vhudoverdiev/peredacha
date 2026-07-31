import unittest
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
TEMPLATES = PROJECT_ROOT / "app" / "templates"
STYLE_CSS = PROJECT_ROOT / "app" / "static" / "style.css"
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class DesktopAjaxTableSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.style_css = STYLE_CSS.read_text(encoding="utf-8")
        cls.base_template = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.service_worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_unmarked_table_filters_use_ajax_only_on_desktop(self):
        helper_start = self.script.index("const isPaginationFilterForm = form =>")
        helper_end = self.script.index("const paginationFilterForms", helper_start)
        helper = self.script[helper_start:helper_end]

        explicit_marker = helper.index("data-ajax-pagination-form")
        desktop_gate = helper.index("isDesktopAjaxTableSearch()")
        self.assertLess(explicit_marker, desktop_gate)
        self.assertIn("targetUrl.origin === window.location.origin", helper)
        self.assertIn("targetUrl.pathname === window.location.pathname", helper)
        self.assertIn("const form = event.target.closest('form');", self.script)
        self.assertNotIn(
            "event.target.closest('form[data-ajax-pagination-form]')",
            self.script,
        )

    def test_desktop_search_and_reset_never_fall_back_to_document_reload(self):
        self.assertIn(
            "const link = event.target.closest('.crm-reset-btn[href], "
            "[data-ajax-pagination-reset][href]');",
            self.script,
        )
        self.assertIn("fallbackToNavigation: !isDesktopAjaxTableSearch()", self.script)
        self.assertIn("fallbackToNavigation: false", self.script)
        self.assertIn("if (itemsSelector && !isDesktopAjaxTableSearch())", self.script)

    def test_hidden_ajax_spares_cannot_override_hidden_attribute(self):
        selector = "[data-ajax-pagination-spare][hidden]"
        selector_start = self.style_css.index(selector)
        rule_end = self.style_css.index("}", selector_start)
        rule = self.style_css[selector_start:rule_end]

        self.assertIn("display: none !important", rule)

    def test_delete_logs_page_does_not_render_site_error_kind_tabs(self):
        delete_logs_template = (TEMPLATES / "developer_delete_logs.html").read_text(encoding="utf-8")
        site_errors_template = (TEMPLATES / "site_errors.html").read_text(encoding="utf-8")

        self.assertIn("site-errors-kind-tabs", site_errors_template)
        self.assertNotIn("site-errors-kind-tabs", delete_logs_template)
        self.assertNotIn("Обращения", delete_logs_template)
        self.assertNotIn("Регистрации", delete_logs_template)
        self.assertNotIn("Системные", delete_logs_template)

    def test_site_error_filters_have_visible_native_select_fallback(self):
        site_errors_template = (TEMPLATES / "site_errors.html").read_text(encoding="utf-8")
        script_start = site_errors_template.index("document.querySelectorAll('.js-developer-custom-select')")
        script_end = site_errors_template.index("document.addEventListener('click'", script_start)
        select_script = site_errors_template[script_start:script_end]

        self.assertIn("selectShell.classList.add('is-enhanced')", select_script)

        fallback_selector = (
            "body:has(.developer-section-tabs) .site-errors-filter-form "
            ".developer-custom-select:not(.is-enhanced) > .developer-native-select"
        )
        enhanced_selector = (
            "body:has(.developer-section-tabs) .site-errors-filter-form "
            ".developer-custom-select.is-enhanced > .developer-native-select"
        )
        fallback_start = self.style_css.index(fallback_selector)
        fallback_rule = self.style_css[fallback_start:self.style_css.index("}", fallback_start)]
        enhanced_start = self.style_css.index(enhanced_selector)
        enhanced_rule = self.style_css[enhanced_start:self.style_css.index("}", enhanced_start)]

        self.assertIn("display: block !important", fallback_rule)
        self.assertIn("opacity: 1 !important", fallback_rule)
        self.assertIn("pointer-events: auto !important", fallback_rule)
        self.assertIn("opacity: 0 !important", enhanced_rule)
        self.assertIn("pointer-events: none !important", enhanced_rule)

    def test_style_cache_version_matches_service_worker(self):
        version_pattern = r"style\.css[^\n]*\?v=(v[\w-]+)"
        template_version = re.search(version_pattern, self.base_template)
        worker_version = re.search(version_pattern, self.service_worker)

        self.assertIsNotNone(template_version)
        self.assertIsNotNone(worker_version)
        self.assertEqual(template_version.group(1), worker_version.group(1))

    def test_every_search_table_has_a_partial_update_contract(self):
        expected_contracts = {
            "apartments.html": ("apartments", "apartments-grid"),
            "assignments.html": ("assignments", "assignment-shell"),
            "assignment_report.html": ("assignment-report", "assignment-report-grid"),
            "developer_statistics_base.html": (
                "developer-statistics",
                "developer-statistics-lower-content",
            ),
            "glass_measurements.html": ("glass-measurements", "glass-tab-content"),
            "materials.html": ("materials", "materials-tab-content"),
            "material_writeoff_form.html": ("materials", "material-tasks-box"),
            "site_errors.html": ("site-errors", "site-errors-tab-content"),
            "task_list.html": ("remarks", "remarks-export-scope"),
        }

        for template_name, (page_key, content_class) in expected_contracts.items():
            with self.subTest(template=template_name):
                template = (TEMPLATES / template_name).read_text(encoding="utf-8")
                self.assertIn(
                    f'data-ajax-pagination-page="{page_key}"',
                    template,
                )
                content_class_position = template.index(content_class)
                self.assertGreaterEqual(
                    template.find(
                        "data-ajax-pagination-content",
                        content_class_position,
                    ),
                    content_class_position,
                )

    def test_assignment_report_filter_updates_totals_and_rows_together(self):
        template = (TEMPLATES / "assignment_report.html").read_text(encoding="utf-8")
        summary_start = template.index('class="assignment-report-summary mb-3"')
        self.assertGreaterEqual(
            template.find("data-ajax-pagination-summary", summary_start),
            summary_start,
        )
        self.assertIn("data-ajax-pagination-reset", template)
        self.assertIn(
            'data-ajax-items-selector=".assignment-report-card"',
            template,
        )
        self.assertGreaterEqual(template.count("{% if not is_mobile_phone_request %}"), 4)


if __name__ == "__main__":
    unittest.main()
