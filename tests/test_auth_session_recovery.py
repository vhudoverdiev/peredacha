"""A stale session/remember cookie must not lock a browser in a 401 loop."""
import unittest

from flask import abort
from flask_login import current_user, login_required

from app import create_app, db, login_manager
from app.models import ROLE_ADMIN, User
from app.security import _BUCKETS
from config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = 'session-recovery-test-only'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class AuthSessionRecoveryTests(unittest.TestCase):
    def setUp(self):
        _BUCKETS.clear()
        self.app = create_app(TestConfig)
        self.protection = login_manager.session_protection
        login_manager.session_protection = 'strong'

        @self.app.get('/auth-test/protected')
        @login_required
        def protected():
            return {'user': current_user.username}

        @self.app.get('/auth-test/unauthorized')
        def unauthorized():
            abort(401)

        self.context = self.app.app_context()
        self.context.push()
        self.user = User(username='session-user', role=ROLE_ADMIN, captcha_disabled=True, is_active=True)
        self.user.set_password('Strong-test-password-2026!')
        db.session.add(self.user)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.protection
        _BUCKETS.clear()

    def login(self, remember=True):
        response = self.client.post('/login', data={
            'username': self.user.username,
            'password': 'Strong-test-password-2026!',
            'remember': 'y' if remember else '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get('/auth-test/protected').status_code, 200)

    def assert_recoverable(self):
        for _ in range(3):
            response = self.client.get('/login', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.request.path, '/login')
        self.assertIsNone(self.client.get_cookie('remember_token'))
        self.login(remember=False)

    def test_expired_session_with_remember_cookie_can_log_in_without_clearing_cookies(self):
        self.login()
        self.assertIsNotNone(self.client.get_cookie('remember_token'))
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        self.assert_recoverable()

    def test_revoked_session_recovers_and_clears_remember_cookie(self):
        self.login()
        self.user.session_version += 1
        db.session.commit()
        response = self.client.get('/auth-test/protected')
        self.assertEqual(response.status_code, 303)
        self.assertIn('/login', response.location)
        self.assert_recoverable()

    def test_logout_deletes_remember_cookie(self):
        self.login()
        self.assertEqual(self.client.post('/logout').status_code, 302)
        self.assertIsNone(self.client.get_cookie('remember_token'))
        self.assert_recoverable()

    def test_invalid_session_version_is_rejected_without_server_error(self):
        self.login()
        with self.client.session_transaction() as session:
            session['session_version'] = 'invalid'
        self.assertEqual(self.client.get('/auth-test/protected').status_code, 303)
        self.assert_recoverable()

    def test_ajax_revocation_returns_recoverable_json_and_expires_cookie(self):
        self.login()
        self.user.session_version += 1
        db.session.commit()
        response = self.client.get('/auth-test/protected', headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json['error'], 'authentication_required')
        self.assertTrue(response.json['login_url'].startswith('/login'))
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assert_recoverable()

    def test_anonymous_json_request_does_not_receive_login_html(self):
        response = self.client.get('/auth-test/protected', headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json['error'], 'authentication_required')

    def test_html_401_redirects_to_login_without_loop(self):
        response = self.client.get('/auth-test/unauthorized', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, '/login')

    def test_valid_session_keeps_working_and_remember_cookie(self):
        self.login()
        cookie = self.client.get_cookie('remember_token').value
        for _ in range(3):
            self.assertEqual(self.client.get('/auth-test/protected').status_code, 200)
        self.assertEqual(self.client.get_cookie('remember_token').value, cookie)

    def test_new_login_without_remember_does_not_keep_previous_account_token(self):
        self.login()
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        # Direct POST from a restored stale browser must recover rather than loop.
        self.client.get('/login', follow_redirects=True)
        self.login(remember=False)
        self.assertIsNone(self.client.get_cookie('remember_token'))
