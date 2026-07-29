import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


CONTRACTS = [
    # Route contracts: public URL surfaces that should not silently disappear.
    ("service_worker_route", "app/routes.py", ["/service-worker.js", "def service_worker("]),
    ("objects_route", "app/routes.py", ["/objects", "def objects("]),
    ("object_new_route", "app/routes.py", ["/objects/new", "def object_new("]),
    ("object_edit_route", "app/routes.py", ["/objects/<int:project_id>/edit", "def object_edit("]),
    ("object_delete_route", "app/routes.py", ["/objects/<int:project_id>/delete", "def object_delete("]),
    ("object_delete_confirm_route", "app/routes.py", ["/objects/<int:project_id>/delete/confirm", "def object_delete_confirm("]),
    ("object_open_route", "app/routes.py", ["/objects/<int:project_id>/open", "def object_open("]),
    ("dashboard_home_route", "app/routes.py", ['@bp.route("/")', "def dashboard("]),
    ("google_sync_route", "app/routes.py", ["/sync/google", "def sync_google("]),
    ("user_error_report_route", "app/routes.py", ["/report-error", "def report_error("]),
    ("tab_analytics_route", "app/routes.py", ["/analytics/tab-open", "def analytics_tab_open("]),
    ("site_errors_route", "app/routes.py", ["/site-errors", "def site_errors("]),
    ("developer_statistics_route", "app/routes.py", ["/developer/statistics", "def developer_statistics("]),
    ("developer_delete_logs_route", "app/routes.py", ["/developer/delete-logs", "def developer_delete_logs("]),
    ("tasks_route", "app/routes.py", ["/tasks", "def task_list("]),
    ("contractors_route", "app/routes.py", ["/contractors", "def contractors_list("]),
    ("contractor_directory_route", "app/routes.py", ["/contractors/directory", "def contractor_directory("]),
    ("glass_measurements_route", "app/routes.py", ["/glass", "def glass_measurements("]),
    ("glass_order_route", "app/routes.py", ["/glass/order", "def glass_order("]),
    ("glass_delete_route", "app/routes.py", ["/glass/delete", "def glass_measurements_delete("]),
    ("materials_route", "app/routes.py", ["/materials", "def materials("]),
    ("material_request_new_route", "app/routes.py", ["/materials/request/new", "def material_request_new("]),
    ("material_writeoff_route", "app/routes.py", ["/materials/write-off", "def material_writeoff_new("]),
    ("apartments_route", "app/routes.py", ["/apartments", "def apartments("]),
    ("avr_route", "app/routes.py", ["/avr", "def avr("]),
    ("documents_route", "app/routes.py", ["/documents", "def documents("]),
    ("documents_addendum_route", "app/routes.py", ["/documents/addendum", "def documents_addendum("]),
    ("work_report_route", "app/routes.py", ["/report", "def work_report("]),
    ("notifications_route", "app/routes.py", ["/notifications", "def notifications("]),
    ("mapping_settings_route", "app/routes.py", ["/mappings", "def mapping_settings("]),
    ("site_settings_route", "app/routes.py", ["/settings", "def site_settings("]),
    ("account_route", "app/routes.py", ["/account", "def account("]),
    ("users_route", "app/routes.py", ["/users", "def users("]),
    ("sync_logs_route", "app/routes.py", ["/sync-logs", "def sync_logs("]),
    ("sync_conflicts_route", "app/routes.py", ["/conflicts", "def sync_conflicts("]),
    ("auth_login_route", "app/auth.py", ["/login", "def login("]),
    ("auth_captcha_route", "app/auth.py", ["/login/captcha", "def login_captcha("]),
    ("auth_2fa_route", "app/auth.py", ["/login/2fa", "def login_2fa("]),
    ("auth_registration_request_route", "app/auth.py", ["/registration-request", "def registration_request("]),
    ("auth_logout_route", "app/auth.py", ["/logout", "def logout("]),
    # Base layout and navigation contracts.
    ("base_mobile_page_chrome_macro", "app/templates/base.html", ["macro mobile_page_chrome", "mobile-shell-topbar"]),
    ("base_mobile_bottom_nav_macro", "app/templates/base.html", ["macro mobile_bottom_nav", "data-mobile-dock=\"unified\""]),
    ("base_worker_dock_two_items", "app/templates/base.html", ["mobile-worker-bottom-nav", "--mobile-nav-count: 2"]),
    ("base_manager_dock_four_items", "app/templates/base.html", ["4 if current_user.role in ['admin', 'manager'] else 3"]),
    ("base_mobile_home_tab", "app/templates/base.html", ["mobile-nav-item-home", "url_for('main.dashboard')"]),
    ("base_mobile_remarks_tab", "app/templates/base.html", ["active == 'remarks'", "url_for('main.task_list')"]),
    ("base_mobile_assignments_tab", "app/templates/base.html", ["mobile-nav-item-assignments", "url_for('main.assignments')"]),
    ("base_mobile_apartments_tab", "app/templates/base.html", ["mobile-nav-item-apartments", "url_for('main.apartments')"]),
    ("base_mobile_objects_tab", "app/templates/base.html", ["active == 'objects'", "url_for('main.objects')"]),
    ("base_mobile_account_tab", "app/templates/base.html", ["active == 'account'", "url_for('main.account')"]),
    ("base_dashboard_active_map", "app/templates/base.html", ["request.endpoint == 'main.dashboard'", "mobile_active = 'dashboard'"]),
    ("base_task_active_map", "app/templates/base.html", ["'main.task_detail'", "mobile_active = 'remarks'"]),
    ("base_apartment_active_map", "app/templates/base.html", ["'main.apartment_detail'", "mobile_active = 'apartments'"]),
    ("base_materials_active_map", "app/templates/base.html", ["'main.material_request_detail'", "mobile_active = 'materials'"]),
    ("base_glass_active_map", "app/templates/base.html", ["'main.glass_measurements'", "mobile_active = 'glass'"]),
    ("base_assignments_active_map", "app/templates/base.html", ["'main.assignment_manual_task_new'", "mobile_active = 'assignments'"]),
    ("base_report_active_map", "app/templates/base.html", ["'main.work_report'", "mobile_active = 'report'"]),
    ("base_objects_layout_branch", "app/templates/base.html", ["layout_mode.strip() == 'objects'", "objects-layout"]),
    ("base_documents_layout_branch", "app/templates/base.html", ["layout_mode.strip() in ['documents', 'settings']", "documents-standalone-layout"]),
    ("base_app_layout_branch", "app/templates/base.html", ["app-layout", "app-topbar"]),
    ("base_desktop_home_sidebar_link", "app/templates/base.html", ["request.endpoint == 'main.dashboard'", "sidebar-link"]),
    ("base_desktop_report_sidebar_link", "app/templates/base.html", ["url_for('main.work_report')", "sidebar-link"]),
    ("base_desktop_materials_sidebar_link", "app/templates/base.html", ["url_for('main.materials')", "sidebar-link"]),
    ("base_desktop_glass_sidebar_link", "app/templates/base.html", ["url_for('main.glass_measurements')", "sidebar-link"]),
    ("base_desktop_account_menu", "app/templates/base.html", ["dropdown-menu", "url_for('main.account')"]),
    # CSS contracts that keep top and bottom panels fixed.
    ("mobile_dock_fixed", "app/static/mobile-only.css", ["nav.mobile-bottom-nav.mobile-bottom-nav-root", "position: fixed !important"]),
    ("mobile_dock_bottom_anchor", "app/static/mobile-only.css", ["inset: auto 0 0 0 !important", "bottom: 0 !important"]),
    ("mobile_dock_height", "app/static/mobile-only.css", ["height: 72px !important", "max-height: 72px !important"]),
    ("mobile_dock_grid_count", "app/static/mobile-only.css", ["grid-template-columns: repeat(var(--mobile-nav-count, 4), minmax(0, 1fr)) !important"]),
    ("mobile_dock_full_width", "app/static/mobile-only.css", ["width: 100vw !important", "max-width: 100vw !important"]),
    ("mobile_topbar_fixed", "app/static/mobile-only.css", ["mobile-app-topbar.mobile-shell-topbar", "position: fixed !important"]),
    ("mobile_project_topbar_fixed", "app/static/mobile-only.css", ["mobile-project-topbar.mobile-shell-topbar", "position: fixed !important"]),
    ("mobile_topbar_shell_layering", "app/static/mobile-only.css", ["body.app-body :is(.mobile-app-topbar, .mobile-project-topbar, .mobile-bottom-nav)"]),
    ("mobile_content_bottom_reserve", "app/static/mobile-only.css", ["padding-bottom: calc(72px + .75rem) !important"]),
    ("mobile_short_page_marker", "app/static/mobile-only.css", ["body.app-body:has(.mobile-short-page-marker)"]),
    ("mobile_assignment_empty_physical_anchor", "app/static/mobile-only.css", ["assignment-issued-layout-empty", "top: calc(var(--mobile-physical-app-height, 100dvh) - 72px) !important"]),
    ("mobile_task_form_physical_anchor", "app/static/mobile-only.css", ["task-single-form", "top: calc(var(--mobile-physical-app-height, 100dvh) - 72px) !important"]),
    ("mobile_worker_short_physical_anchor", "app/static/mobile-only.css", ["mobile-worker-bottom-nav", "worker-page-empty"]),
    ("desktop_hides_mobile_dock", "app/static/desktop-only.css", ["nav.mobile-bottom-nav.mobile-bottom-nav-root[data-mobile-dock=\"unified\"]", "display: none !important"]),
    ("desktop_sidebar_fixed", "app/static/desktop-only.css", [".app-layout > .app-sidebar", "position: fixed !important"]),
    ("desktop_sidebar_width", "app/static/desktop-only.css", ["width: var(--desktop-sidebar-width, 230px) !important"]),
    ("desktop_main_offsets_sidebar", "app/static/desktop-only.css", ["margin-left: var(--desktop-sidebar-width, 230px) !important"]),
    ("desktop_main_reserves_topbar", "app/static/desktop-only.css", ["padding-top: 4.9rem !important"]),
    ("desktop_topbar_fixed", "app/static/desktop-only.css", [".app-layout > .app-main > .app-topbar", "position: fixed !important"]),
    ("desktop_topbar_left_anchor", "app/static/desktop-only.css", ["inset: 0 auto auto var(--desktop-sidebar-width, 230px) !important"]),
    ("desktop_topbar_height", "app/static/desktop-only.css", ["height: 4.9rem !important"]),
    ("desktop_standalone_topbar_fixed", "app/static/desktop-only.css", ["> .objects-topbar", "position: fixed !important"]),
    ("desktop_standalone_topbar_height", "app/static/desktop-only.css", ["height: 5.75rem !important"]),
    ("desktop_standalone_layout_top_padding", "app/static/desktop-only.css", ["padding-top: 5.75rem !important"]),
    ("dashboard_mobile_topbar_offset", "app/static/style.css", ["body.app-body:has(.dashboard-page.dashboard-redesign) .app-main", "padding-top: var(--ref-mobile-topbar-height"]),
    # Page template markers used by navigation, CSS and route layout contracts.
    ("dashboard_page_marker", "app/templates/dashboard.html", ["dashboard-page", "dashboard-redesign"]),
    ("objects_page_marker", "app/templates/objects.html", ["objects-page"]),
    ("remarks_page_marker", "app/templates/task_list.html", ["remarks-page-head"]),
    ("apartments_page_marker", "app/templates/apartments.html", ["apartments-page"]),
    ("apartment_detail_page_marker", "app/templates/apartment_detail.html", ["apartment-detail-page"]),
    ("materials_page_marker", "app/templates/materials.html", ["materials-page"]),
    ("glass_page_marker", "app/templates/glass_measurements.html", ["glass-page"]),
    ("assignments_page_marker", "app/templates/assignments.html", ["assignments-page-head"]),
    ("documents_page_marker", "app/templates/documents.html", ["document-type-grid"]),
    ("account_page_marker", "app/templates/account.html", ["account-page"]),
]


class SiteContracts100Tests(unittest.TestCase):
    pass


def _make_contract_test(name: str, relative_path: str, needles: list[str]):
    def test(self):
        source = read(relative_path)
        for needle in needles:
            with self.subTest(needle=needle):
                self.assertIn(needle, source)

    test.__name__ = f"test_{name}"
    test.__doc__ = f"{relative_path} contains {', '.join(needles)}"
    return test


for index, (name, relative_path, needles) in enumerate(CONTRACTS, start=1):
    safe_name = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    setattr(
        SiteContracts100Tests,
        f"test_{index:03d}_{safe_name}",
        _make_contract_test(name, relative_path, needles),
    )


assert len(CONTRACTS) == 100


if __name__ == "__main__":
    unittest.main()
