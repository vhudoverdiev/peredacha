"""A stale session/remember cookie must not lock a browser in a 401 loop."""
import unittest

from flask import abort
from flask_login import current_user, login_required
from flask_login.utils import encode_cookie
from flask.testing import FlaskClient

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


class RequestScopedClient(FlaskClient):
    def open(self, *args, **kwargs):
        # Match a real server: CSRF and current_user are cached per request,
        # never in the outer application context used by the database fixture.
        with self.application.app_context():
            return super().open(*args, **kwargs)


class AuthSessionRecoveryTests(unittest.TestCase):
    def setUp(self):
        _BUCKETS.clear()
        self.app = create_app(TestConfig)
        self.app.test_client_class = RequestScopedClient
        self.protection = login_manager.session_protection
        login_manager.session_protection = 'strong'

        @self.app.route('/auth-test/protected', methods=['GET', 'POST'])
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
        token = self.client.get('/csrf-token').json['csrf_token']
        response = self.client.post('/login', data={
            'username': self.user.username,
            'password': 'Strong-test-password-2026!',
            'remember': 'y' if remember else '',
            'csrf_token': token,
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

    def test_expired_session_with_valid_remember_cookie_restores_login(self):
        self.login()
        self.assertIsNotNone(self.client.get_cookie('remember_token'))
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        for _ in range(3):
            response = self.client.get('/auth-test/protected')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['user'], self.user.username)
        with self.client.session_transaction() as state:
            self.assertEqual(state['session_version'], self.user.session_version)
            self.assertFalse(state['_fresh'])
            self.assertTrue(state.permanent)

    def test_legacy_remember_cookie_requires_login_without_clearing_browser_cookies(self):
        self.client.set_cookie('remember_token', encode_cookie(str(self.user.id)))
        self.assert_recoverable()

    def test_revoked_remember_cookie_cannot_restore_expired_session(self):
        self.login()
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        self.user.set_password('Changed-test-password-2026!')
        db.session.commit()
        response = self.client.get('/auth-test/protected', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, '/login')
        self.assertIsNone(self.client.get_cookie('remember_token'))

    def test_invalid_remember_cookie_cannot_authenticate(self):
        self.client.set_cookie('remember_token', 'invalid-cookie')
        response = self.client.get('/auth-test/protected', follow_redirects=True)
        self.assertEqual(response.request.path, '/login')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.get_cookie('remember_token'))

    def test_inactive_account_cannot_restore_a_remembered_login(self):
        self.login()
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        self.user.is_active = False
        db.session.commit()
        response = self.client.get('/objects', follow_redirects=True)
        self.assertEqual(response.request.path, '/login')
        self.assertIsNone(self.client.get_cookie('remember_token'))

    def test_legacy_active_session_remains_valid(self):
        self.login(remember=False)
        with self.client.session_transaction() as state:
            state['_user_id'] = str(self.user.id)
        self.assertEqual(self.client.get('/auth-test/protected').status_code, 200)

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
        self.assertEqual(self.client.post('/logout', data={'csrf_token': self.client.get('/csrf-token').json['csrf_token']}).status_code, 302)
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

    def test_main_pages_use_auth_recovery_for_expired_ajax_requests(self):
        for path in ('/', '/objects', '/appeals', '/records'):
            with self.subTest(path=path):
                response = self.client.get(path, headers={'Accept': 'application/json'})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers['X-CRM-Auth-Required'], '1')
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

    def test_background_reads_do_not_reissue_an_old_session_cookie(self):
        self.login()
        for path in ('/auth-test/protected', '/static/favicon.ico'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(any(value.startswith('session=') for value in response.headers.getlist('Set-Cookie')))
                response.close()

    def test_new_login_without_remember_does_not_keep_previous_account_token(self):
        self.login()
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        self.client.set_cookie('remember_token', encode_cookie(str(self.user.id)))
        # An old account token must not survive a fresh login without remember.
        self.client.get('/login', follow_redirects=True)
        self.login(remember=False)
        self.assertIsNone(self.client.get_cookie('remember_token'))


class AuthCsrfRecoveryTests(AuthSessionRecoveryTests):
    def setUp(self):
        super().setUp()
        self.app.config['WTF_CSRF_ENABLED'] = True

    def test_stale_form_after_session_expiry_redirects_to_login(self):
        self.login(remember=False)
        token = self.client.get('/csrf-token').json['csrf_token']
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        response = self.client.post('/records/slots/close-interval', data={'csrf_token': token})
        self.assertEqual(response.status_code, 303)
        self.assertIn('/login', response.location)
        self.assert_recoverable()

    def test_stale_ajax_form_after_session_expiry_uses_auth_recovery(self):
        self.login(remember=False)
        token = self.client.get('/csrf-token').json['csrf_token']
        self.client.delete_cookie(self.app.config['SESSION_COOKIE_NAME'])
        response = self.client.post('/records/slots/close-interval', data={'csrf_token': token},
                                    headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers['X-CRM-Auth-Required'], '1')
        self.assertEqual(response.json['error'], 'authentication_required')

    def test_public_error_report_keeps_csrf_protection_without_requiring_login(self):
        response = self.client.post('/report-error', data={'csrf_token': 'invalid'})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('X-CRM-Auth-Required', response.headers)

    def test_authenticated_request_with_invalid_csrf_still_fails(self):
        self.login()
        response = self.client.post('/auth-test/protected', data={'csrf_token': 'invalid'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/auth-test/protected').status_code, 200)
