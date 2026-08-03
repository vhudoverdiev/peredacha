from datetime import datetime, timedelta
from io import BytesIO
import unittest
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from config import Config
from app import create_app, db
from app.auth import _is_safe_next
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER, Task, User
from app.permissions import can_change_task, can_export, can_manage_mapping, can_manage_sync, readonly
from app.security import (
    _BUCKETS,
    allowed_upload_suffix,
    clear_captcha,
    generate_captcha,
    hit_rate_limit,
    is_account_locked,
    mark_login_failure,
    mark_login_success,
    validate_upload,
    verify_captcha,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "security-auth-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    MAX_UPLOAD_FILE_BYTES = 16


class SecurityAuthContractsTests(unittest.TestCase):
    def setUp(self):
        _BUCKETS.clear()
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        _BUCKETS.clear()

    def _upload(self, filename: str, payload: bytes) -> FileStorage:
        return FileStorage(stream=BytesIO(payload), filename=filename)

    def test_safe_next_allows_local_relative_urls_only(self):
        with self.app.test_request_context("/login", base_url="https://crm.example"):
            self.assertTrue(_is_safe_next("/tasks?status=open"))
            self.assertFalse(_is_safe_next("https://crm.example/tasks"))
            self.assertFalse(_is_safe_next("https://evil.example/phish"))
            self.assertFalse(_is_safe_next("//evil.example/phish"))
            self.assertFalse(_is_safe_next(""))
            self.assertFalse(_is_safe_next(None))

    def test_rate_limit_is_scoped_by_endpoint_and_client_ip(self):
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.7"}):
            with patch("app.security.time.time", side_effect=[1000.0, 1001.0, 1002.0, 1003.0]):
                self.assertFalse(hit_rate_limit("login", limit=2, window_seconds=60))
                self.assertFalse(hit_rate_limit("login", limit=2, window_seconds=60))
                self.assertTrue(hit_rate_limit("login", limit=2, window_seconds=60))
                self.assertFalse(hit_rate_limit("upload", limit=2, window_seconds=60))

    def test_rate_limit_expires_old_hits(self):
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.8"}):
            with patch("app.security.time.time", side_effect=[1000.0, 1001.0, 1061.1]):
                self.assertFalse(hit_rate_limit("login", limit=2, window_seconds=60))
                self.assertFalse(hit_rate_limit("login", limit=2, window_seconds=60))
                self.assertFalse(hit_rate_limit("login", limit=2, window_seconds=60))

    def test_captcha_uses_prefix_specific_session_keys_and_expires(self):
        with self.app.test_request_context("/login"):
            with patch("app.security.time.time", return_value=1000):
                with patch("app.security.secrets.randbelow", side_effect=[0, 1, 2]):
                    with patch("app.security.secrets.token_urlsafe", return_value="nonce"):
                        question = generate_captcha(prefix="login")

            self.assertEqual(question, "2 + 3")
            with patch("app.security.time.time", return_value=1001):
                self.assertTrue(verify_captcha(" 5 ", prefix="login"))
                self.assertFalse(verify_captcha("5", prefix="registration"))

            with patch("app.security.time.time", return_value=1002):
                self.assertFalse(verify_captcha("5", max_age_seconds=1, prefix="login"))

            clear_captcha(prefix="login")
            self.assertFalse(verify_captcha("5", prefix="login"))

    def test_upload_validation_accepts_real_magic_bytes_and_rejects_spoofed_files(self):
        with self.app.test_request_context("/upload"):
            validate_upload(self._upload("remarks.xlsx", b"PK\x03\x04 workbook"), {"xlsx"})
            validate_upload(self._upload("act.pdf", b"%PDF-1.7"), {"pdf"})
            validate_upload(self._upload("legacy.doc", bytes.fromhex("D0CF11E0") + b"doc"), {"doc"})

            with self.assertRaises(ValueError):
                validate_upload(self._upload("remarks.exe", b"MZ"), {"xlsx"})
            with self.assertRaises(ValueError):
                validate_upload(self._upload("remarks.xlsx", b"not zip"), {"xlsx"})
            with self.assertRaises(ValueError):
                validate_upload(self._upload("act.pdf", b"not pdf"), {"pdf"})
            with self.assertRaises(ValueError):
                validate_upload(self._upload("large.xlsx", b"PK" + b"x" * 32), {"xlsx"})

    def test_upload_suffix_allowlist_is_case_insensitive_and_extension_based(self):
        self.assertTrue(allowed_upload_suffix("Report.XLSX", {"xlsx"}))
        self.assertTrue(allowed_upload_suffix("archive.tar.gz", {".gz"}))
        self.assertFalse(allowed_upload_suffix("xlsx", {"xlsx"}))
        self.assertFalse(allowed_upload_suffix("report.xlsx.exe", {"xlsx"}))

    def test_login_failure_lockout_escalates_and_success_resets_account_state(self):
        user = User(username="locked-user", password_hash="unused", role=ROLE_MANAGER)
        db.session.add(user)
        db.session.commit()

        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.10"}):
            for _ in range(4):
                mark_login_failure(user)
                self.assertFalse(is_account_locked(user))

            before_lock = datetime.utcnow()
            mark_login_failure(user)
            self.assertTrue(is_account_locked(user))
            self.assertGreaterEqual(user.locked_until, before_lock + timedelta(minutes=14))

            mark_login_success(user)
            self.assertEqual(user.failed_login_count, 0)
            self.assertIsNone(user.locked_until)
            self.assertEqual(user.last_login_ip, "192.0.2.10")

    def test_login_failure_refreshes_detached_user_before_updating_counter(self):
        user = User(username="detached-user", password_hash="unused", role=ROLE_MANAGER)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        db.session.expunge(user)

        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.10"}):
            mark_login_failure(user)

        stored_user = db.session.get(User, user_id)
        self.assertEqual(stored_user.failed_login_count, 1)

    def test_permission_helpers_enforce_role_and_assignment_rules(self):
        admin = User(id=1, username="admin", role=ROLE_ADMIN)
        manager = User(id=2, username="manager", role=ROLE_MANAGER)
        viewer = User(id=3, username="viewer", role=ROLE_VIEWER)
        worker = User(id=4, username="worker", role="glazier")
        assigned_task = Task(responsible_id=worker.id)
        other_task = Task(responsible_id=999)

        self.assertTrue(can_manage_sync(admin))
        self.assertTrue(can_manage_mapping(manager))
        self.assertTrue(can_export(manager))
        self.assertFalse(can_export(viewer))
        self.assertTrue(readonly(viewer))
        self.assertTrue(can_change_task(admin, other_task))
        self.assertTrue(can_change_task(manager, other_task))
        self.assertTrue(can_change_task(worker, assigned_task))
        self.assertFalse(can_change_task(worker, other_task))
        self.assertFalse(can_change_task(viewer, assigned_task))


if __name__ == "__main__":
    unittest.main()
