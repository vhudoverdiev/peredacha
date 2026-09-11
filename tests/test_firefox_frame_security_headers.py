import unittest

from config import Config
from app import create_app, db, login_manager
from app.models import ROLE_ADMIN, User


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "firefox-frame-security-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class FirefoxFrameSecurityHeaderTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.user = User(
            username="firefox-frame-admin",
            password_hash="unused",
            role=ROLE_ADMIN,
        )
        db.session.add(self.user)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_public_pages_cannot_be_framed(self):
        response = self.client.get("/login")

        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_authenticated_pages_allow_same_origin_frames_only(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
            session["session_version"] = int(self.user.session_version or 0)

        response = self.client.get("/objects")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("frame-ancestors 'self'", response.headers["Content-Security-Policy"])
        self.assertNotIn("frame-ancestors *", response.headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
