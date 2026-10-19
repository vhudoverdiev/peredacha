import unittest

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, SyncConflict, Task, User, WorkPoint


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "task-delete-sync-conflict-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class TaskDeleteSyncConflictContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.project = Project(name="Delete conflict project")
        db.session.add(self.project)
        db.session.flush()
        self.apartment = Apartment(project=self.project, apartment_number="32")
        self.point = WorkPoint(point_number="11", short_name="Стены")
        self.task = Task(
            source_uid="delete-conflict-task",
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            description="Удаляемое замечание",
            source_cell_value="Удаляемое замечание",
        )
        self.admin = User(username="admin-delete-conflict", role=ROLE_ADMIN, is_active=True, captcha_disabled=True)
        self.admin.set_password("correct-password")
        self.admin.set_project_access([self.project.id], all_projects=False)
        db.session.add_all([self.apartment, self.point, self.task, self.admin])
        db.session.flush()
        self.conflict = SyncConflict(
            task_id=self.task.id,
            apartment_id=self.apartment.id,
            target_type="task",
            source_type="excel",
            old_value="old",
            new_value="new",
            status="pending",
        )
        db.session.add(self.conflict)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def _login(self):
        response = self.client.post(
            "/login",
            data={"username": self.admin.username, "password": "correct-password"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            sess["current_project_id"] = self.project.id

    def test_task_delete_removes_sync_conflicts_that_reference_task(self):
        task_id = self.task.id
        conflict_id = self.conflict.id
        self._login()

        response = self.client.post(f"/tasks/{task_id}/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        self.assertIsNone(db.session.get(Task, task_id))
        self.assertIsNone(db.session.get(SyncConflict, conflict_id))


if __name__ == "__main__":
    unittest.main()
