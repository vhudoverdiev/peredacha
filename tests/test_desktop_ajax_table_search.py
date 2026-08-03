import unittest
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
TEMPLATES = PROJECT_ROOT / "app" / "templates"
STYLE_CSS = PROJECT_ROOT / "app" / "static" / "style.css"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class DesktopAjaxTableSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.style_css = STYLE_CSS.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
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

    def test_site_error_filters_hide_native_select_when_custom_button_exists(self):
        site_errors_template = (TEMPLATES / "site_errors.html").read_text(encoding="utf-8")
        script_start = site_errors_template.index("document.querySelectorAll('.js-developer-custom-select')")
        script_end = site_errors_template.index("document.addEventListener('click'", script_start)
        select_script = site_errors_template[script_start:script_end]

        self.assertIn("selectShell.classList.add('is-enhanced')", select_script)

        removed_fallback_selector = (
            "body:has(.developer-section-tabs) .site-errors-filter-form "
            ".developer-custom-select:not(.is-enhanced) > .developer-native-select"
        )
        enhanced_selector = (
            "body:has(.developer-section-tabs) .site-errors-filter-form "
            ".developer-custom-select.is-enhanced > .developer-native-select"
        )
        custom_button_selector = (
            "body:has(.developer-section-tabs) .site-errors-filter-form "
            ".developer-custom-select:has(> .developer-select-button) > select"
        )
        enhanced_start = self.style_css.index(enhanced_selector)
        enhanced_rule = self.style_css[enhanced_start:self.style_css.index("}", enhanced_start)]
        custom_button_start = self.style_css.index(custom_button_selector)
        custom_button_rule = self.style_css[custom_button_start:self.style_css.index("}", custom_button_start)]

        self.assertNotIn(removed_fallback_selector, self.style_css)
        self.assertNotIn(".developer-custom-select:not(.is-enhanced) > .developer-native-select", self.style_css)
        self.assertIn("position: absolute !important", enhanced_rule)
        self.assertIn("inset: 0 !important", enhanced_rule)
        self.assertIn("display: none !important", enhanced_rule)
        self.assertIn("visibility: hidden !important", enhanced_rule)
        self.assertIn("opacity: 0 !important", enhanced_rule)
        self.assertIn("pointer-events: none !important", enhanced_rule)
        self.assertIn("position: absolute !important", custom_button_rule)
        self.assertIn("display: none !important", custom_button_rule)
        self.assertIn("visibility: hidden !important", custom_button_rule)
        self.assertIn("opacity: 0 !important", custom_button_rule)
        self.assertIn("pointer-events: none !important", custom_button_rule)

    def test_site_error_filter_form_exposes_only_status_filter(self):
        site_errors_template = (TEMPLATES / "site_errors.html").read_text(encoding="utf-8")
        filter_start = site_errors_template.index("site-errors-filter-form")
        filter_end = site_errors_template.index("</form>", filter_start)
        filter_markup = site_errors_template[filter_start:filter_end]

        self.assertIn('data-site-errors-kind-filter-disabled="1"', filter_markup)
        self.assertIn('name="kind" disabled', filter_markup)
        self.assertIn('name="status"', filter_markup)

    def test_ajax_custom_selects_hide_native_select_after_enhancement(self):
        init_start = self.script.index("const initDeveloperCustomSelects = (scope = document) =>")
        init_end = self.script.index("const refreshCustomSelectViewportMode", init_start)
        init_script = self.script[init_start:init_end]

        helper_start = init_script.index("const hideEnhancedNativeSelect = () =>")
        helper_end = init_script.index("const forceCustomSelectOnMobile", helper_start)
        helper_script = init_script[helper_start:helper_end]
        self.assertIn("select.hidden = true;", helper_script)
        self.assertIn("select.tabIndex = -1;", helper_script)
        self.assertIn("select.setAttribute('aria-hidden', 'true');", helper_script)
        self.assertIn("select.classList.add('developer-native-select');", helper_script)
        self.assertIn("select.classList.remove('mobile-native-select');", helper_script)
        self.assertIn("select.hidden = false;", init_script)

        existing_button_start = init_script.index("if (selectShell.querySelector('.developer-select-button'))")
        existing_button_end = init_script.index("return;", existing_button_start)
        existing_button_branch = init_script[existing_button_start:existing_button_end]

        self.assertIn("hideEnhancedNativeSelect();", existing_button_branch)
        self.assertIn("selectShell.classList.add('is-enhanced');", existing_button_branch)
        self.assertIn(
            "hideEnhancedNativeSelect();\n\n"
            "      const button = document.createElement('button');",
            init_script,
        )
        self.assertIn("selectShell.appendChild(button);", init_script)
        self.assertIn("selectShell.classList.add('is-enhanced');", init_script)
        self.assertIn("selectShell.classList.remove('is-open', 'is-enhanced');", init_script)
        self.assertIn("button.setAttribute('data-ajax-pagination-runtime', 'custom-select');", init_script)
        self.assertIn("menu.setAttribute('data-ajax-pagination-runtime', 'custom-select');", init_script)
        self.assertIn("const customSelectObserver = new MutationObserver", self.script)
        self.assertIn("refreshCustomSelectViewportMode(node.matches?.('select')", self.script)
        self.assertIn("document.addEventListener('crm:ajax-pagination-updated', event =>", self.script)
        self.assertIn("refreshCustomSelectViewportMode(event.detail?.content || document);", self.script)
        self.assertIn("!child.hasAttribute('data-ajax-pagination-runtime')", self.script)
        self.assertIn("currentNode.dispatchEvent(new Event('change', { bubbles: true }));", self.script)

        site_errors_template = (TEMPLATES / "site_errors.html").read_text(encoding="utf-8")
        inline_helper_start = site_errors_template.index("function hideEnhancedNativeSelect()")
        inline_helper_end = site_errors_template.index("if (selectShell.querySelector('.developer-select-button'))", inline_helper_start)
        inline_helper = site_errors_template[inline_helper_start:inline_helper_end]
        self.assertIn("select.hidden = true;", inline_helper)
        self.assertIn("select.tabIndex = -1;", inline_helper)
        self.assertIn("select.setAttribute('aria-hidden', 'true');", inline_helper)
        self.assertIn("select.classList.add('developer-native-select');", inline_helper)
        self.assertIn("select.classList.remove('mobile-native-select');", inline_helper)
        guard_start = site_errors_template.index("if (selectShell.querySelector('.developer-select-button'))")
        guard_end = site_errors_template.index("return;", guard_start)
        guard_script = site_errors_template[guard_start:guard_end]
        self.assertIn("hideEnhancedNativeSelect();", guard_script)
        self.assertIn("selectShell.classList.add('is-enhanced');", guard_script)
        self.assertIn("hideEnhancedNativeSelect();\n\n    const button = document.createElement('button');", site_errors_template)
        self.assertIn("button.setAttribute('data-ajax-pagination-runtime', 'custom-select');", site_errors_template)
        self.assertIn("menu.setAttribute('data-ajax-pagination-runtime', 'custom-select');", site_errors_template)

    def test_static_asset_cache_versions_match_service_worker(self):
        for asset_name in ("style.css", "script.js"):
            with self.subTest(asset=asset_name):
                version_pattern = rf"{re.escape(asset_name)}[^\n]*\?v=(v[\w-]+)"
                template_version = re.search(version_pattern, self.base_template)
                worker_version = re.search(version_pattern, self.service_worker)

                self.assertIsNotNone(template_version)
                self.assertIsNotNone(worker_version)
                self.assertEqual(template_version.group(1), worker_version.group(1))

        registration_version = re.search(r"service-worker\.js\?v=(v[\w-]+)", self.base_template)
        cache_version = re.search(r"const STATIC_CACHE = 'peredacha-static-(v[\w-]+)'", self.service_worker)
        self.assertIsNotNone(registration_version)
        self.assertIsNotNone(cache_version)
        self.assertEqual(registration_version.group(1), cache_version.group(1))

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

    def test_material_tabs_replay_the_writeoff_entrance_animation_after_ajax_swap(self):
        materials_listener_start = self.script.index("event.detail?.pageKey !== 'materials'")
        materials_listener_end = self.script.index("// Contractor names are also written", materials_listener_start)
        materials_listener = self.script[materials_listener_start:materials_listener_end]

        self.assertIn("document.documentElement.classList.contains('desktop-like-pointer')", materials_listener)
        self.assertIn("'.materials-animated-card'", materials_listener)
        self.assertIn("shell.classList.remove('crm-tab-enter')", materials_listener)
        self.assertIn("shell.style.animation = 'none'", materials_listener)
        self.assertIn("void shell.offsetWidth", materials_listener)
        self.assertIn("window.requestAnimationFrame", materials_listener)
        self.assertIn("shell.style.removeProperty('animation')", materials_listener)
        self.assertIn("shell.classList.add('crm-tab-enter')", materials_listener)

        writeoff_selector = ".material-writeoff-form .materials-animated-card"
        list_table_selector = ".materials-list-page-region > .materials-animated-card"
        replay_selector = ".materials-animated-card.crm-tab-enter"
        writeoff_start = self.desktop_css.index(writeoff_selector)
        writeoff_rule = self.desktop_css[writeoff_start:self.desktop_css.index("}", writeoff_start)]
        list_table_start = self.desktop_css.index(list_table_selector)
        list_table_rule = self.desktop_css[list_table_start:self.desktop_css.index("}", list_table_start)]
        replay_start = self.desktop_css.index(replay_selector)
        replay_rule = self.desktop_css[replay_start:self.desktop_css.index("}", replay_start)]

        for expected in (
            "animation: desktopMaterialWriteoffRise .35s ease both !important",
            "animation-delay: 0ms !important",
            "transition-delay: 0ms !important",
            "will-change: transform, opacity !important",
        ):
            self.assertIn(expected, writeoff_rule)
            self.assertIn(expected, list_table_rule)
            self.assertIn(expected, replay_rule)

    def test_material_list_tables_keep_visible_top_card_edges(self):
        card_selector = (
            "body:has(.materials-page-head) .materials-list-page-region > "
            ".materials-animated-card"
        )
        card_start = self.style_css.index(card_selector)
        card_rule = self.style_css[card_start:self.style_css.index("}", card_start)]

        self.assertIn("border: 1px solid #dfe8d4 !important", card_rule)
        self.assertIn("background: #fff !important", card_rule)
        self.assertIn("background-clip: padding-box !important", card_rule)
        self.assertIn("overflow: hidden !important", card_rule)

        header_selector = (
            "body:has(.materials-page-head) .materials-list-page-region > "
            ".materials-animated-card > .material-bulk-header"
        )
        header_start = self.style_css.index(header_selector)
        header_rule = self.style_css[header_start:self.style_css.index("}", header_start)]
        self.assertIn("border-top-left-radius: inherit !important", header_rule)
        self.assertIn("border-top-right-radius: inherit !important", header_rule)

        materials_template = (TEMPLATES / "materials.html").read_text(encoding="utf-8")
        for tab_name in ("balance", "requests"):
            with self.subTest(tab=tab_name):
                self.assertRegex(
                    materials_template,
                    rf"active_tab == '{tab_name}'[\s\S]*?materials-list-page-region"
                    rf"[\s\S]*?table-shell task-table-shell materials-animated-card",
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
