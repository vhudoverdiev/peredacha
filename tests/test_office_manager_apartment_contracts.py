import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DETAIL = (ROOT / "app" / "templates" / "apartment_detail.html").read_text(encoding="utf-8")
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
STYLE = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")


class OfficeManagerApartmentContractsTests(unittest.TestCase):
    def test_office_manager_gets_booking_action_without_inspection_edit_controls(self):
        self.assertIn("current_user.role not in ['viewer', 'office_manager']", DETAIL)
        self.assertIn("Записать на осмотр", DETAIL)
        self.assertIn("url_for('main.record_apartment_new', apartment_id=apartment.id)", DETAIL)

    def test_three_apartment_comments_have_distinct_labels(self):
        self.assertIn("Комментарий (Офис)", DETAIL)
        self.assertIn("Комментарий (Инженеры)", DETAIL)
        self.assertIn("Комментарий (Офис-Менеджер)", DETAIL)
        self.assertIn("update_apartment_office_manager_comment", DETAIL)
        self.assertIn("data-apartment-office-manager-comment-display", DETAIL)

    def test_office_manager_task_status_buttons_and_links_are_hidden(self):
        self.assertGreaterEqual(DETAIL.count("current_user.role not in ['viewer', 'office_manager']"), 3)
        self.assertIn("current_user.role != 'office_manager' %}task-row-link", DETAIL)

    def test_office_manager_forbidden_sidebar_links_are_hidden_on_desktop_and_mobile(self):
        self.assertGreaterEqual(BASE.count("current_user.role != 'office_manager'"), 2)

    def test_owner_field_keeps_original_grid_and_fits_name_without_wrapping(self):
        owner_rule = STYLE[STYLE.index('html body.app-body .apartment-detail-page .apartment-owner-names-control[name="owner_name"]'):]
        owner_rule = owner_rule[:owner_rule.index("}")]
        self.assertIn("white-space: pre", owner_rule)
        self.assertIn("font-size: .78rem", owner_rule)
        self.assertNotIn("grid-template-columns", owner_rule)

    def test_worker_room_badge_is_uppercase_and_in_progress_pill_is_gray(self):
        worker_template = (ROOT / "app" / "templates" / "my_tasks.html").read_text(encoding="utf-8")
        script = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")
        self.assertIn("task.apartment.label()|upper", worker_template)
        self.assertIn("'secondary' if task.status == 'in_progress'", worker_template)
        self.assertIn("result.status === 'in_progress' ? 'secondary'", script)
        self.assertIn("'Не выполнено' if task.status == STATUS_DONE else 'Выполнено'", worker_template)
        self.assertIn("result.is_done ? 'Не выполнено' : 'Выполнено'", script)


if __name__ == "__main__":
    unittest.main()
