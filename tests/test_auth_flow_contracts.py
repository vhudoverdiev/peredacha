from datetime import datetime
import time
import unittest
from unittest.mock import patch

from config import Config
from app import create_app, db, login_manager
from app.models import ROLE_ADMIN, ROLE_GLAZIER, ROLE_MANAGER, ROLE_VERIFIER, AppSetting, Project, SiteErrorReport, User
from app.security import _BUCKETS


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "auth-flow-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class AuthFlowContractsTests(unittest.TestCase):
    def setUp(self):
        _BUCKETS.clear()
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection
        _BUCKETS.clear()

    def _user(self, username="qa-user", role=ROLE_MANAGER, *, captcha_disabled=True, active=True) -> User:
        user = User(username=username, role=role, captcha_disabled=captcha_disabled, is_active=active)
        user.set_password("correct-password")
        db.session.add(user)
        db.session.commit()
        return user

    def test_password_login_with_captcha_disabled_completes_session_and_ignores_unsafe_next(self):
        user = self._user(role=ROLE_ADMIN)

        response = self.client.post(
            "/login?next=https://evil.example/phish",
            data={"username": user.username, "password": "correct-password"},
            follow_redirects=False,
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")
        with self.client.session_transaction() as session:
            self.assertEqual(session.get("_user_id"), str(user.id))
            self.assertEqual(session.get("session_version"), user.session_version)
            self.assertNotIn("pending_login_user_id", session)

        stored_user = db.session.get(User, user.id)
        self.assertEqual(stored_user.failed_login_count, 0)
        self.assertEqual(stored_user.last_login_ip, "203.0.113.10")

    def test_worker_login_honors_safe_next_url_for_field_workflows(self):
        worker = self._user(username="glazier", role=ROLE_GLAZIER)

        response = self.client.post(
            "/login?next=/my-tasks?status=open",
            data={"username": worker.username, "password": "correct-password"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/my-tasks?status=open")

    def test_verifier_login_respects_current_project_session_when_redirecting(self):
        verifier = self._user(username="verifier", role=ROLE_VERIFIER)
        project = Project(name="Verifier project")
        db.session.add(project)
        db.session.commit()
        with self.client.session_transaction() as session:
            session["current_project_id"] = project.id

        response = self.client.post(
            "/login",
            data={"username": verifier.username, "password": "correct-password"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/report", response.headers["Location"])

    def test_invalid_password_increments_failure_count_without_creating_pending_login(self):
        user = self._user()

        response = self.client.post(
            "/login",
            data={"username": user.username, "password": "wrong-password"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(user)
        self.assertEqual(user.failed_login_count, 1)
        with self.client.session_transaction() as session:
            self.assertNotIn("pending_login_user_id", session)
            self.assertNotIn("_user_id", session)

    def test_captcha_step_blocks_bad_answer_and_keeps_login_pending(self):
        user = self._user(captcha_disabled=False)

        password_response = self.client.post(
            "/login",
            data={"username": user.username, "password": "correct-password"},
            follow_redirects=False,
        )
        self.assertEqual(password_response.status_code, 302)
        self.assertIn("/login/captcha", password_response.headers["Location"])

        with self.client.session_transaction() as session:
            session["login_captcha_answer"] = "7"
            session["login_captcha_issued_at"] = int(time.time())

        captcha_response = self.client.post("/login/captcha", data={"captcha_answer": "8"}, follow_redirects=False)

        self.assertEqual(captcha_response.status_code, 200)
        db.session.refresh(user)
        self.assertEqual(user.failed_login_count, 1)
        with self.client.session_transaction() as session:
            self.assertEqual(session.get("pending_login_user_id"), user.id)
            self.assertNotIn("_user_id", session)

    def test_two_factor_step_requires_valid_code_before_login_completion(self):
        user = self._user(captcha_disabled=True)
        user.two_factor_enabled = True
        user.two_factor_secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        user.last_login_ip = "198.51.100.1"
        db.session.add(AppSetting(key="two_factor_every_login", value="1"))
        db.session.commit()
        user_id = user.id
        username = user.username
        db.session.remove()

        password_response = self.client.post(
            "/login",
            data={"username": username, "password": "correct-password"},
            follow_redirects=False,
            environ_base={"REMOTE_ADDR": "198.51.100.2"},
        )
        self.assertEqual(password_response.status_code, 302)
        self.assertIn("/login/2fa", password_response.headers["Location"])

        with patch("app.auth.verify_totp", return_value=False):
            bad_response = self.client.post("/login/2fa", data={"two_factor_code": "000000"}, follow_redirects=False)

        self.assertEqual(bad_response.status_code, 200)
        self.assertEqual(db.session.get(User, user_id).failed_login_count, 1)
        with self.client.session_transaction() as session:
            self.assertNotIn("_user_id", session)
            self.assertTrue(session.get("pending_login_2fa"))

        with patch("app.auth.verify_totp", return_value=True):
            good_response = self.client.post("/login/2fa", data={"two_factor_code": "123456"}, follow_redirects=False)

        self.assertEqual(good_response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session.get("_user_id"), str(user_id))
            self.assertNotIn("pending_login_2fa", session)

    def test_registration_request_validates_captcha_and_persists_normalized_request(self):
        with self.client.session_transaction() as session:
            session["registration_captcha_answer"] = "9"
            session["registration_captcha_issued_at"] = int(time.time())

        response = self.client.post(
            "/registration-request",
            data={"name": "QA Engineer", "email": "QA@Example.COM", "captcha_answer": "9"},
            headers={"User-Agent": "AuthFlowTest/1.0"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        report = SiteErrorReport.query.filter_by(kind="registration").one()
        self.assertIn("qa@example.com", report.message)
        self.assertEqual(report.user_agent, "AuthFlowTest/1.0")
        with self.client.session_transaction() as session:
            self.assertNotIn("registration_captcha_answer", session)


if __name__ == "__main__":
    unittest.main()
