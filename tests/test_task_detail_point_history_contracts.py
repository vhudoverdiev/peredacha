import unittest

from config import Config
from app import create_app, db, login_manager
from app.models import (
    Apartment,
    ChangeLog,
    Project,
    ROLE_ADMIN,
    ROLE_MANAGER,
    STATUS_NOT_STARTED,
    Task,
    User,
    WorkPoint,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "task-detail-point-history-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class TaskDetailPointHistoryContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.project = Project(name="Task detail project")
        db.session.add(self.project)
        db.session.flush()
        self.apartment = Apartment(project=self.project, apartment_number="1")
        self.point_11 = WorkPoint(point_number="11", short_name="Стены. Потолки")
        self.point_16 = WorkPoint(point_number="16", short_name="Разнорабочие")
        self.point_26 = WorkPoint(point_number="26", short_name="Отступное (ТМЦ)", original_column_name="Отступное (ТМЦ)")
        self.task = Task(
            source_uid="task-detail-point-change",
            project=self.project,
            apartment=self.apartment,
            work_point=self.point_11,
            description="Тестовое замечание",
            status=STATUS_NOT_STARTED,
        )
        self.admin = self._user("admin", ROLE_ADMIN)
        self.manager = self._user("manager", ROLE_MANAGER)
        self.other = self._user("other", ROLE_MANAGER)
        db.session.add_all([self.apartment, self.point_11, self.point_16, self.point_26, self.task])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def _user(self, username, role):
        user = User(username=username, role=role, is_active=True, captcha_disabled=True)
        user.set_password("correct-password")
        user.set_project_access([self.project.id], all_projects=False)
        db.session.add(user)
        return user

    def _login(self, user):
        response = self.client.post(
            "/login",
            data={"username": user.username, "password": "correct-password"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            sess["current_project_id"] = self.project.id

    def test_task_point_can_be_changed_from_detail_page(self):
        self._login(self.admin)

        response = self.client.post(
            f"/tasks/{self.task.id}/point",
            data={"point_number": "16"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.task)
        self.assertEqual(self.task.work_point.point_number, "16")
        change = ChangeLog.query.filter_by(task_id=self.task.id, field_name="work_point").one()
        self.assertIn("Стены", change.old_value)
        self.assertIn("Разнорабочие", change.new_value)

    def test_task_point_change_supports_ajax_autosave(self):
        self._login(self.admin)

        response = self.client.post(
            f"/tasks/{self.task.id}/point",
            data={"point_number": "16"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["point_number"], "16")
        db.session.refresh(self.task)
        self.assertEqual(self.task.work_point.point_number, "16")

    def test_task_point_change_rejects_service_points_before_ten(self):
        self._login(self.admin)

        response = self.client.post(
            f"/tasks/{self.task.id}/point",
            data={"point_number": "2"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])
        db.session.refresh(self.task)
        self.assertEqual(self.task.work_point.point_number, "11")

    def test_task_detail_point_select_autosaves_without_check_button_and_starts_from_ten(self):
        self._login(self.admin)

        response = self.client.get(f"/tasks/{self.task.id}")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("data-task-detail-point-autosave", html)
        self.assertIn('<option value="10"', html)
        self.assertIn('<option value="26"', html)
        self.assertIn("26. Отступное (ТМЦ)", html)
        self.assertNotIn('<option value="1"', html)
        self.assertNotIn("task-detail-point-save-btn", html)

    def test_task_point_can_be_changed_to_dop_agreement_point(self):
        self._login(self.admin)

        response = self.client.post(
            f"/tasks/{self.task.id}/point",
            data={"point_number": "26"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        db.session.refresh(self.task)
        self.assertEqual(self.task.work_point.point_number, "26")
        self.assertEqual(self.task.work_point.original_column_name, "Отступное (ТМЦ)")

    def test_non_admin_sees_only_own_history_entries(self):
        db.session.add_all([
            ChangeLog(task_id=self.task.id, user_id=self.manager.id, action="field_update", field_name="description", old_value="", new_value="Своя запись"),
            ChangeLog(task_id=self.task.id, user_id=self.other.id, action="field_update", field_name="description", old_value="", new_value="Чужая запись"),
        ])
        db.session.commit()
        self._login(self.manager)

        response = self.client.get(f"/tasks/{self.task.id}")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Своя запись", html)
        self.assertNotIn("Чужая запись", html)

    def test_admin_sees_full_history_entries(self):
        db.session.add_all([
            ChangeLog(task_id=self.task.id, user_id=self.manager.id, action="field_update", field_name="description", old_value="", new_value="Своя запись"),
            ChangeLog(task_id=self.task.id, user_id=self.other.id, action="field_update", field_name="description", old_value="", new_value="Чужая запись"),
        ])
        db.session.commit()
        self._login(self.admin)

        response = self.client.get(f"/tasks/{self.task.id}")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Своя запись", html)
        self.assertIn("Чужая запись", html)


if __name__ == "__main__":
    unittest.main()
