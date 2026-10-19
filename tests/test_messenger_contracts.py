import unittest

from flask import g

from config import Config
from app import create_app, db, login_manager
from app.models import Project, ROLE_ADMIN, ROLE_EXECUTOR, ROLE_MANAGER, ROLE_OFFICE, ROLE_SUPERVISOR, SiteErrorReport, User


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "messenger-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class MessengerContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Messenger project")
        self.admin = User(
            username="developer",
            full_name="Владимир Худовердиев",
            password_hash="unused",
            role=ROLE_ADMIN,
        )
        self.manager = User(username="manager-chat", full_name="Инженер", password_hash="unused", role=ROLE_MANAGER)
        self.supervisor = User(username="supervisor-chat", full_name="Начальник", password_hash="unused", role=ROLE_SUPERVISOR)
        self.office = User(username="office-chat", full_name="Офис", password_hash="unused", role=ROLE_OFFICE)
        self.worker = User(username="worker-chat", full_name="Рабочий", password_hash="unused", role=ROLE_EXECUTOR)
        db.session.add_all([self.project, self.admin, self.manager, self.supervisor, self.office, self.worker])
        db.session.commit()

        self.client = self.app.test_client()
        self.admin_client = self.app.test_client()
        self.office_client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def _login(self, user, client=None):
        client = client or self.client
        if hasattr(g, "_login_user"):
            delattr(g, "_login_user")
        with client.session_transaction() as session:
            session.clear()
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
            session["session_version"] = int(user.session_version or 0)
            session["current_project_id"] = self.project.id

    def test_messenger_endpoints_are_removed_for_authenticated_roles(self):
        for user in (self.admin, self.manager, self.supervisor, self.office, self.worker):
            with self.subTest(role=user.role):
                client = self.app.test_client()
                self._login(user, client)
                response = client.get("/messenger/thread")
                self.assertEqual(response.status_code, 403)

    def test_developer_reply_to_error_report_is_removed(self):
        report = SiteErrorReport(
            project=self.project,
            user=self.office,
            kind="user",
            message="Не открывается страница",
            page_url="/apartments",
            status="new",
        )
        db.session.add(report)
        db.session.commit()

        self._login(self.admin, self.admin_client)
        response = self.admin_client.post(
            f"/site-errors/{report.id}/reply",
            data={"reply": "Проверил, теперь работает."},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 404)
        db.session.refresh(report)
        self.assertEqual(report.status, "new")
        self.assertIsNone(report.developer_reply)
        self.assertIsNone(report.user_reply_read_at)
