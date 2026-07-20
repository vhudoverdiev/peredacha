import unittest
from datetime import date

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, GlassMeasurement, Project, ROLE_ADMIN, Task, User, WorkPoint


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "glass-manual-task-entry-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class GlassManualTaskEntryTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Glass manual task QA")
        self.user = User(
            username="glass-manual-admin",
            password_hash="unused",
            role=ROLE_ADMIN,
            all_projects_access=True,
        )
        self.apartment = Apartment(project=self.project, apartment_number="8")
        self.glass_point = WorkPoint(point_number="16", source_sheet_name="qa")
        ordered_task = Task(
            source_uid="glass-manual-existing-ordered",
            project=self.project,
            apartment=self.apartment,
            work_point=self.glass_point,
            description="Уже заказанный стеклопакет",
        )
        ordered_measurement = GlassMeasurement(
            project=self.project,
            task=ordered_task,
            apartment=self.apartment,
            status="ordered",
            ordered_at=date(2026, 7, 20),
        )
        db.session.add_all([self.project, self.user, self.glass_point, ordered_task, ordered_measurement])
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
            session["session_version"] = int(self.user.session_version or 0)
            session["current_project_id"] = self.project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_desktop_page_restores_add_task_button_and_mobile_does_not_change(self):
        desktop_response = self.client.get(
            "/glass-measurements",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        mobile_response = self.client.get(
            "/glass-measurements",
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 15; Mobile)"},
        )

        self.assertEqual(desktop_response.status_code, 200)
        self.assertIn("js-glass-manual-open", desktop_response.get_data(as_text=True))
        self.assertIn("Добавить задачу", desktop_response.get_data(as_text=True))
        self.assertEqual(mobile_response.status_code, 200)
        self.assertNotIn("js-glass-manual-open", mobile_response.get_data(as_text=True))

    def test_manual_task_is_created_and_remains_visible_after_reload(self):
        response = self.client.post(
            "/glass/task/new",
            data={"apartment_id": self.apartment.id, "description": "Новый ручной замер"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        manual_task = Task.query.filter_by(source_sheet_name="manual_glass").one()
        self.assertEqual(manual_task.work_point.point_number, "22")
        self.assertIsNotNone(manual_task.glass_measurement)
        self.assertEqual(manual_task.glass_measurement.status, "none")

        page_response = self.client.get(
            "/glass-measurements?tab=all",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertIn("Новый ручной замер", page_response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
