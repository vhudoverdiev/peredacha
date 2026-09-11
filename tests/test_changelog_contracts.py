import unittest

from flask_login import login_user

from config import Config
from app import create_app, db
from app.models import Apartment, ChangeLog, Project, Task, User, WorkPoint
from app.services.changelog_service import log_change


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "changelog-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ChangeLogContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.project = Project(name="Project")
        self.apartment = Apartment(project=self.project, apartment_number="42")
        self.work_point = WorkPoint(point_number="2", short_name="Doors")
        self.task = Task(
            source_uid="changelog-task",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Fix lock",
        )
        db.session.add_all([self.project, self.apartment, self.work_point, self.task])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_log_change_outside_request_is_safe_and_normalizes_values_to_strings(self):
        entry = log_change(self.task, "update", field_name="status", old_value=None, new_value=123)
        db.session.commit()

        persisted = ChangeLog.query.one()
        self.assertEqual(entry.id, persisted.id)
        self.assertIsNone(persisted.user_id)
        self.assertEqual(persisted.task_id, self.task.id)
        self.assertEqual(persisted.old_value, "")
        self.assertEqual(persisted.new_value, "123")

    def test_log_change_uses_authenticated_user_when_user_id_is_not_explicit(self):
        user = User(username="manager", role="manager")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

        with self.app.test_request_context("/tasks/1"):
            login_user(user)
            log_change(self.task, "comment", new_value="Added details")
            db.session.commit()

        self.assertEqual(ChangeLog.query.one().user_id, user.id)

    def test_explicit_user_id_takes_precedence_over_current_user(self):
        current = User(username="current", role="manager")
        explicit = User(username="explicit", role="admin")
        current.set_password("secret")
        explicit.set_password("secret")
        db.session.add_all([current, explicit])
        db.session.commit()

        with self.app.test_request_context("/tasks/1"):
            login_user(current)
            log_change(self.task, "update", user_id=explicit.id)
            db.session.commit()

        self.assertEqual(ChangeLog.query.one().user_id, explicit.id)


if __name__ == "__main__":
    unittest.main()
