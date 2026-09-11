from pathlib import Path
import unittest
from unittest.mock import patch

from flask import jsonify, request

from app import create_app, db, login_manager
from app.models import (
    Apartment,
    MaterialRequest,
    Project,
    ROLE_MANAGER,
    SyncLog,
    SecurityEvent,
    Task,
    User,
    WorkPoint,
)
from app.time_utils import utc_now
from config import Config


ROOT = Path(__file__).resolve().parents[1]


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "server-security-boundaries-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ServerSecurityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.own_project = Project(name="Own project")
        self.foreign_project = Project(name="Foreign project")
        self.user = User(
            username="scoped-manager",
            role=ROLE_MANAGER,
            project=self.own_project,
            all_projects_access=False,
        )
        self.user.set_password("Strong-test-password-2026!")
        own_point = WorkPoint(point_number="1", short_name="Own point", source_sheet_name="qa")
        foreign_point = WorkPoint(point_number="2", short_name="Foreign point", source_sheet_name="qa")
        self.own_apartment = Apartment(
            project=self.own_project,
            apartment_number="125",
            owner_name="Own owner",
        )
        self.foreign_apartment = Apartment(
            project=self.foreign_project,
            apartment_number="126",
            owner_name="Foreign owner",
        )
        self.foreign_task = Task(
            source_uid="foreign-security-task",
            project=self.foreign_project,
            apartment=self.foreign_apartment,
            work_point=foreign_point,
            description="Foreign secret task",
        )
        self.foreign_request = MaterialRequest(
            project=self.foreign_project,
            author=self.user,
            title="Foreign secret request",
        )
        self.foreign_log = SyncLog(
            project_id=None,
            source_type="excel",
            source_name="foreign.xlsx",
            started_at=utc_now(),
            status="success",
        )
        db.session.add_all(
            [
                self.own_project,
                self.foreign_project,
                self.user,
                own_point,
                foreign_point,
                self.own_apartment,
                self.foreign_apartment,
                self.foreign_task,
                self.foreign_request,
                self.foreign_log,
            ]
        )
        db.session.flush()
        self.foreign_log.project_id = self.foreign_project.id
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
            session["session_version"] = int(self.user.session_version or 0)
            session["current_project_id"] = self.own_project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_idor_cannot_read_foreign_project_records_by_changing_numeric_id(self):
        foreign_urls = (
            f"/apartments/{self.foreign_apartment.id}",
            f"/apartments/{self.foreign_apartment.id}/remarks/export",
            f"/tasks/{self.foreign_task.id}",
            f"/materials/request/{self.foreign_request.id}",
            f"/materials/request/{self.foreign_request.id}/export",
            f"/sync-logs/{self.foreign_log.id}/details",
        )
        for url in foreign_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(b"Foreign secret", response.data)

    def test_idor_cannot_modify_or_delete_foreign_project_records(self):
        foreign_posts = (
            (f"/apartments/{self.foreign_apartment.id}/comment", {"comment": "hacked"}),
            (f"/tasks/{self.foreign_task.id}/delete", {}),
            (f"/tasks/{self.foreign_task.id}/comment", {"comment": "hacked"}),
            (f"/materials/request/{self.foreign_request.id}/rename", {"title": "hacked"}),
            (f"/materials/request/{self.foreign_request.id}/delete", {}),
            (f"/sync-logs/{self.foreign_log.id}/delete", {}),
        )
        for url, data in foreign_posts:
            with self.subTest(url=url):
                response = self.client.post(url, data=data)
                self.assertEqual(response.status_code, 404)

        db.session.expire_all()
        self.assertIsNotNone(db.session.get(Task, self.foreign_task.id))
        self.assertEqual(db.session.get(MaterialRequest, self.foreign_request.id).title, "Foreign secret request")
        self.assertEqual(db.session.get(Apartment, self.foreign_apartment.id).comment, None)
        self.assertIsNotNone(db.session.get(SyncLog, self.foreign_log.id))

    def test_user_controlled_html_is_escaped_in_server_rendered_pages(self):
        payload = '<script>window.__xss = "owned"</script>'
        self.own_apartment.owner_name = payload
        db.session.commit()

        response = self.client.get(f"/apartments/{self.own_apartment.id}")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn(payload, html)
        self.assertIn("&lt;script&gt;", html)

    def test_sql_injection_payload_is_treated_as_search_text(self):
        payload = "' OR 1=1; DROP TABLE apartments; --"
        response = self.client.get("/apartments", query_string={"q": payload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Apartment.query.count(), 2)
        self.assertIsNotNone(db.session.get(Apartment, self.foreign_apartment.id))

    def test_authenticated_html_has_security_headers_and_is_not_cached(self):
        response = self.client.get(f"/apartments/{self.own_apartment.id}")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_failed_login_is_audited_without_storing_the_password(self):
        password = "Never-log-this-password-987!"
        anonymous_client = self.app.test_client()
        response = anonymous_client.post(
            "/login",
            data={"username": self.user.username, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        event = SecurityEvent.query.filter_by(kind="login_failed").order_by(SecurityEvent.id.desc()).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.user_id, self.user.id)
        self.assertNotIn(password, event.message or "")


class ProductionConfigurationSecurityTests(unittest.TestCase):
    def test_production_refuses_missing_or_known_placeholder_secret_key(self):
        for value in (None, "", "change-me", "development"):
            with self.subTest(value=value):
                class InsecureConfig(Config):
                    TESTING = False
                    SECRET_KEY = value
                    SQLALCHEMY_DATABASE_URI = "sqlite://"

                with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                    create_app(InsecureConfig)

    def test_flask_push_can_register_without_production_secret_key(self):
        class PushOnlyConfig(Config):
            TESTING = False
            SECRET_KEY = None
            SQLALCHEMY_DATABASE_URI = "sqlite://"

        with patch("sys.argv", ["flask", "push"]):
            app = create_app(PushOnlyConfig)

        self.assertIn("push", app.cli.commands)

    def test_repository_does_not_contain_common_secret_or_debug_defaults(self):
        config_source = (ROOT / "config.py").read_text(encoding="utf-8")
        app_entry = (ROOT / "app.py").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertNotIn('SECRET_KEY = os.getenv("SECRET_KEY", "change-me")', config_source)
        self.assertIn('os.getenv("FLASK_DEBUG", "0")', app_entry)
        self.assertNotIn("app.run(debug=True)", app_entry)
        self.assertRegex(gitignore, r"(?m)^\.env$")

    def test_gunicorn_runs_as_unprivileged_user_over_private_unix_socket(self):
        service = (ROOT / "deploy" / "gunicorn.service").read_text(encoding="utf-8")
        socket = (ROOT / "deploy" / "gunicorn.socket").read_text(encoding="utf-8")
        self.assertIn("User=www-data", service)
        self.assertIn("Group=www-data", service)
        self.assertIn("EnvironmentFile=/opt/peredacha/.env", service)
        self.assertNotIn("User=root", service)
        self.assertNotIn("--reload", service)
        self.assertIn("ListenStream=/run/gunicorn-crm_flask.sock", socket)
        self.assertIn("SocketMode=0660", socket)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("PrivateTmp=true", service)
        self.assertIn("ProtectSystem=full", service)
        self.assertIn("UMask=0077", service)
        self.assertIn("MemoryMax=", service)
        self.assertIn("CPUQuota=", service)

    def test_nginx_deploy_config_has_tls_headers_upload_limits_and_rate_limits(self):
        nginx_config = (ROOT / "deploy" / "nginx-akvilon-peredacha.conf").read_text(encoding="utf-8")
        rate_limit_config = (ROOT / "deploy" / "nginx-rate-limit.conf").read_text(encoding="utf-8")
        self.assertIn("listen 443 ssl http2", nginx_config)
        self.assertIn("return 301 https://$host$request_uri", nginx_config)
        self.assertIn("server_tokens off", nginx_config)
        self.assertIn("Strict-Transport-Security", nginx_config)
        self.assertIn("client_max_body_size 50M", nginx_config)
        self.assertIn("proxy_request_buffering on", nginx_config)
        self.assertIn("location = /login", nginx_config)
        self.assertIn("limit_req zone=peredacha_login", nginx_config)
        self.assertIn("zone=peredacha_general:10m rate=10r/s", rate_limit_config)
        self.assertIn("zone=peredacha_login:10m rate=5r/m", rate_limit_config)

    def test_cookie_and_request_size_defaults_are_hardened(self):
        self.assertTrue(Config.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(Config.REMEMBER_COOKIE_HTTPONLY)
        self.assertEqual(Config.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(Config.REMEMBER_COOKIE_SAMESITE, "Lax")
        self.assertGreater(Config.MAX_CONTENT_LENGTH, 0)
        self.assertGreater(Config.MAX_UPLOAD_FILE_BYTES, 0)
        self.assertLessEqual(Config.MAX_UPLOAD_FILE_BYTES, Config.MAX_CONTENT_LENGTH)

    def test_env_example_documents_production_security_defaults(self):
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("FLASK_DEBUG=0", env_example)
        self.assertIn("SECRET_KEY=replace-with-a-strong-random-secret", env_example)
        self.assertIn("DATABASE_URL=postgresql://", env_example)
        self.assertIn("SESSION_COOKIE_SECURE=true", env_example)
        self.assertIn("FORCE_HSTS=true", env_example)
        self.assertIn("TRUSTED_PROXY_COUNT=1", env_example)

    def test_trusted_proxy_headers_are_applied_for_nginx_https_requests(self):
        class ProxiedConfig(Config):
            TESTING = True
            SECRET_KEY = "proxied-request-security-test"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            WTF_CSRF_ENABLED = False
            TRUSTED_PROXY_COUNT = 1

        app = create_app(ProxiedConfig)

        @app.get("/proxy-test")
        def proxy_test():
            return jsonify({"remote_addr": request.remote_addr, "is_secure": request.is_secure})

        response = app.test_client().get(
            "/proxy-test",
            headers={
                "X-Forwarded-For": "203.0.113.77",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "lk.akvilon-peredacha.ru",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["remote_addr"], "203.0.113.77")
        self.assertTrue(response.json["is_secure"])
        self.assertIn("Strict-Transport-Security", response.headers)

    def test_csrf_rejects_state_changing_request_without_token(self):
        class CsrfConfig(Config):
            TESTING = True
            SECRET_KEY = "csrf-security-boundary-test"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            WTF_CSRF_ENABLED = True
            SESSION_COOKIE_SECURE = False

        app = create_app(CsrfConfig)
        response = app.test_client().post("/tasks/123/delete")
        self.assertEqual(response.status_code, 400)

    def test_global_request_size_limit_rejects_oversized_body(self):
        class SmallRequestConfig(Config):
            TESTING = True
            SECRET_KEY = "request-limit-security-boundary-test"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            WTF_CSRF_ENABLED = False
            SESSION_COOKIE_SECURE = False
            MAX_CONTENT_LENGTH = 32

        app = create_app(SmallRequestConfig)
        response = app.test_client().post(
            "/report-error",
            data=b"x" * 64,
            content_type="application/octet-stream",
        )
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
