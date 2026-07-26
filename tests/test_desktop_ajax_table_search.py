import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
TEMPLATES = PROJECT_ROOT / "app" / "templates"


class DesktopAjaxTableSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")

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
