import unittest

from flask import request, session
from flask_login import login_user
from werkzeug.exceptions import Forbidden
from werkzeug.routing import Rule

from config import Config
from app import create_app, db, login_manager
from app.models import (
    AppSetting,
    Project,
    ROLE_ADMIN,
    ROLE_EXECUTOR,
    ROLE_GLAZIER,
    ROLE_HANDYMAN,
    ROLE_MANAGER,
    ROLE_PAINTER,
    ROLE_VERIFIER,
    ROLE_VIEWER,
    Task,
    User,
    WORKER_ROLES,
)
from app.permissions import can_change_task, can_export, can_manage_mapping, can_manage_sync, readonly, role_required
from app.routes import (
    VERIFIER_ALLOWED_ENDPOINTS,
    VIEWER_ALLOWED_GET_ENDPOINTS,
    WORKER_ALLOWED_ENDPOINTS,
    _abort_if_project_forbidden,
    _abort_if_user_outside_current_project,
    _mobile_phone_allowed_endpoints,
    _mobile_phone_home_endpoint,
    _role_home_endpoint,
    enforce_role_access,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "access-rights-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit Mobile/15E148"


class AccessRightsContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.project = Project(name="Access project")
        self.other_project = Project(name="Other access project")
        db.session.add_all([self.project, self.other_project])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def _user(self, role=ROLE_MANAGER, *, project=None, active=True, all_projects=False, username=None):
        user = User(
            username=username or f"{role}-{User.query.count()}",
            role=role,
            is_active=active,
            all_projects_access=all_projects,
            project_id=project.id if project else None,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        return user

    def _guard(self, user, endpoint, *, method="GET", mobile=False, path="/guard"):
        headers = {"User-Agent": MOBILE_UA} if mobile else {}
        with self.app.test_request_context(path, method=method, headers=headers):
            request.url_rule = Rule(path, endpoint=endpoint)
            if user:
                login_user(user)
            return enforce_role_access()

    def assertRedirectsTo(self, response, suffix):
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith(suffix), response.headers["Location"])

    def test_role_home_endpoint_contract_for_all_roles(self):
        cases = {
            ROLE_ADMIN: "main.dashboard",
            ROLE_MANAGER: "main.dashboard",
            ROLE_VIEWER: "main.dashboard",
            ROLE_VERIFIER: "main.work_report",
            ROLE_EXECUTOR: "main.my_tasks",
            ROLE_PAINTER: "main.my_tasks",
            ROLE_HANDYMAN: "main.my_tasks",
            ROLE_GLAZIER: "main.my_tasks",
        }
        for role, endpoint in cases.items():
            with self.subTest(role=role):
                with self.app.test_request_context("/"):
                    login_user(self._user(role=role, username=f"home-{role}"))
                    self.assertEqual(_role_home_endpoint(), endpoint)

    def test_worker_allowed_endpoint_set_is_small_and_field_work_only(self):
        self.assertEqual(WORKER_ALLOWED_ENDPOINTS, {
            "main.dashboard_legacy",
            "main.my_tasks",
            "main.my_task_done",
            "main.my_task_return",
            "main.account",
            "main.report_error",
        })
        self.assertTrue(WORKER_ROLES.issuperset({ROLE_EXECUTOR, ROLE_PAINTER, ROLE_HANDYMAN, ROLE_GLAZIER}))

    def test_verifier_allowed_endpoint_set_is_report_and_document_focused(self):
        self.assertEqual(VERIFIER_ALLOWED_ENDPOINTS, {
            "main.dashboard_legacy",
            "main.objects",
            "main.object_open",
            "main.work_report",
            "main.work_report_export",
            "main.documents",
            "main.documents_addendum",
            "main.documents_download",
            "main.account",
            "main.report_error",
        })

    def test_viewer_readonly_get_allowlist_excludes_mutating_endpoints(self):
        self.assertIn("main.task_list", VIEWER_ALLOWED_GET_ENDPOINTS)
        self.assertIn("main.material_request_detail", VIEWER_ALLOWED_GET_ENDPOINTS)
        self.assertIn("main.work_report", VIEWER_ALLOWED_GET_ENDPOINTS)
        for mutating_endpoint in (
            "main.task_new",
            "main.update_task",
            "main.material_request_new",
            "main.assignment_manual_task_new",
            "main.upload_excel",
            "main.mapping_settings",
            "main.users",
        ):
            with self.subTest(endpoint=mutating_endpoint):
                self.assertNotIn(mutating_endpoint, VIEWER_ALLOWED_GET_ENDPOINTS)

    def test_permission_helpers_allow_only_admin_manager_for_sync_mapping_and_export(self):
        users = {
            role: self._user(role=role, username=f"perm-{role}")
            for role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER, ROLE_VERIFIER, ROLE_GLAZIER)
        }

        for role, user in users.items():
            with self.subTest(role=role):
                expected = role in {ROLE_ADMIN, ROLE_MANAGER}
                self.assertEqual(can_manage_sync(user), expected)
                self.assertEqual(can_manage_mapping(user), expected)
                self.assertEqual(can_export(user), expected)
                self.assertEqual(readonly(user), role == ROLE_VIEWER)

    def test_can_change_task_allows_managers_and_assigned_workers_only(self):
        admin = self._user(role=ROLE_ADMIN, username="change-admin")
        manager = self._user(role=ROLE_MANAGER, username="change-manager")
        worker = self._user(role=ROLE_GLAZIER, username="change-worker")
        other_worker = self._user(role=ROLE_HANDYMAN, username="change-other")
        viewer = self._user(role=ROLE_VIEWER, username="change-viewer")
        task = Task(source_uid="access-change-task", project_id=self.project.id, apartment_id=1, work_point_id=1, responsible_id=worker.id)

        self.assertTrue(can_change_task(admin, task))
        self.assertTrue(can_change_task(manager, task))
        self.assertTrue(can_change_task(worker, task))
        self.assertFalse(can_change_task(other_worker, task))
        self.assertFalse(can_change_task(viewer, task))

    def test_role_required_redirects_anonymous_allows_admin_and_rejects_wrong_role(self):
        protected = role_required(ROLE_MANAGER)(lambda: "ok")

        with self.app.test_request_context("/protected"):
            request.url_rule = Rule("/protected", endpoint="main.protected")
            response = protected()
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

        with self.app.test_request_context("/protected"):
            request.url_rule = Rule("/protected", endpoint="main.protected")
            login_user(self._user(role=ROLE_ADMIN, username="role-required-admin"))
            self.assertEqual(protected(), "ok")

        with self.app.test_request_context("/protected"):
            request.url_rule = Rule("/protected", endpoint="main.protected")
            login_user(self._user(role=ROLE_VIEWER, username="role-required-viewer"))
            with self.assertRaises(Forbidden):
                protected()

    def test_unauthenticated_main_endpoint_redirects_to_login_with_next(self):
        response = self._guard(None, "main.task_list", path="/tasks?status=open")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        self.assertIn("next=/tasks", response.headers["Location"])

    def test_public_error_and_service_worker_endpoints_bypass_auth(self):
        for endpoint in ("main.report_error", "main.service_worker", "main.service_worker_reset"):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._guard(None, endpoint))

    def test_admin_and_manager_bypass_role_restrictions_for_main_endpoints(self):
        for role in (ROLE_ADMIN, ROLE_MANAGER):
            with self.subTest(role=role):
                user = self._user(role=role, username=f"bypass-{role}")
                self.assertIsNone(self._guard(user, "main.users"))
                self.assertIsNone(self._guard(user, "main.mapping_settings", method="POST"))
                self.assertIsNone(self._guard(user, "main.assignment_manual_task_new"))

    def test_worker_can_open_allowed_pages_but_get_is_redirected_from_backoffice(self):
        worker = self._user(role=ROLE_GLAZIER, username="worker-access")

        self.assertIsNone(self._guard(worker, "main.my_tasks"))
        self.assertIsNone(self._guard(worker, "main.account"))
        self.assertRedirectsTo(self._guard(worker, "main.task_list"), "/my-tasks")
        self.assertRedirectsTo(self._guard(worker, "main.users"), "/my-tasks")

    def test_worker_post_to_forbidden_endpoint_is_403(self):
        worker = self._user(role=ROLE_GLAZIER, username="worker-post")

        with self.assertRaises(Forbidden):
            self._guard(worker, "main.update_task", method="POST")

    def test_verifier_can_open_reports_objects_documents_and_account_only(self):
        verifier = self._user(role=ROLE_VERIFIER, username="verifier-access")

        for endpoint in ("main.work_report", "main.objects", "main.object_open", "main.documents", "main.documents_addendum", "main.account"):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._guard(verifier, endpoint))
        self.assertRedirectsTo(self._guard(verifier, "main.task_list"), "/report")

    def test_verifier_post_to_forbidden_endpoint_is_403(self):
        verifier = self._user(role=ROLE_VERIFIER, username="verifier-post")

        with self.assertRaises(Forbidden):
            self._guard(verifier, "main.update_task", method="POST")

    def test_viewer_can_read_allowed_pages_but_cannot_open_write_pages(self):
        viewer = self._user(role=ROLE_VIEWER, username="viewer-read")

        for endpoint in ("main.dashboard", "main.task_list", "main.task_detail", "main.apartments", "main.materials", "main.account"):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._guard(viewer, endpoint))
        self.assertRedirectsTo(self._guard(viewer, "main.task_new"), "/")
        self.assertRedirectsTo(self._guard(viewer, "main.users"), "/")

    def test_viewer_post_to_any_non_public_endpoint_is_403(self):
        viewer = self._user(role=ROLE_VIEWER, username="viewer-post")

        with self.assertRaises(Forbidden):
            self._guard(viewer, "main.update_task", method="POST")

    def test_unknown_authenticated_role_is_forbidden(self):
        unknown = self._user(role="guest", username="unknown-role")

        with self.assertRaises(Forbidden):
            self._guard(unknown, "main.dashboard")

    def test_maintenance_mode_blocks_non_manager_roles_after_authentication(self):
        viewer = self._user(role=ROLE_VIEWER, username="maintenance-viewer")
        manager = self._user(role=ROLE_MANAGER, username="maintenance-manager")
        db.session.add(AppSetting(key="site_maintenance_mode", value="1"))
        db.session.commit()

        viewer_response = self._guard(viewer, "main.dashboard")
        self.assertIsInstance(viewer_response, tuple)
        self.assertEqual(viewer_response[1], 503)
        self.assertIsNone(self._guard(manager, "main.dashboard"))

    def test_mobile_home_endpoint_respects_role_and_project_selection(self):
        worker = self._user(role=ROLE_PAINTER, username="mobile-worker", project=self.project)
        verifier = self._user(role=ROLE_VERIFIER, username="mobile-verifier", project=self.project)
        manager = self._user(role=ROLE_MANAGER, username="mobile-manager", all_projects=True)

        with self.app.test_request_context("/", headers={"User-Agent": MOBILE_UA}):
            login_user(worker)
            self.assertEqual(_mobile_phone_home_endpoint(), "main.my_tasks")

        with self.app.test_request_context("/", headers={"User-Agent": MOBILE_UA}):
            login_user(verifier)
            self.assertEqual(_mobile_phone_home_endpoint(), "main.work_report")

        with self.app.test_request_context("/", headers={"User-Agent": MOBILE_UA}):
            login_user(manager)
            self.assertEqual(_mobile_phone_home_endpoint(), "main.objects")
            session["current_project_id"] = self.project.id
            self.assertEqual(_mobile_phone_home_endpoint(), "main.dashboard")

    def test_mobile_allowed_endpoints_are_role_specific(self):
        cases = (
            (ROLE_GLAZIER, "main.my_tasks", "main.assignments"),
            (ROLE_VERIFIER, "main.work_report", "main.task_list"),
            (ROLE_MANAGER, "main.assignments", "main.users"),
            (ROLE_VIEWER, "main.task_list", "main.assignments"),
        )
        for role, allowed_endpoint, forbidden_endpoint in cases:
            with self.subTest(role=role):
                with self.app.test_request_context("/", headers={"User-Agent": MOBILE_UA}):
                    login_user(self._user(role=role, username=f"mobile-allowed-{role}"))
                    allowed = _mobile_phone_allowed_endpoints()
                    self.assertIn(allowed_endpoint, allowed)
                    self.assertNotIn(forbidden_endpoint, allowed)

    def test_mobile_guard_redirects_disallowed_get_and_blocks_disallowed_post(self):
        manager = self._user(role=ROLE_MANAGER, username="mobile-guard-manager", project=self.project)

        self.assertRedirectsTo(self._guard(manager, "main.users", mobile=True), "/")
        with self.assertRaises(Forbidden):
            self._guard(manager, "main.users", method="POST", mobile=True)

    def test_project_access_guard_returns_allowed_project_and_hides_forbidden_project(self):
        scoped = self._user(role=ROLE_MANAGER, username="project-scoped", project=self.project)
        admin = self._user(role=ROLE_ADMIN, username="project-admin")

        with self.app.test_request_context("/"):
            login_user(scoped)
            self.assertEqual(_abort_if_project_forbidden(self.project).id, self.project.id)
            with self.assertRaises(Exception) as error:
                _abort_if_project_forbidden(self.other_project)
            self.assertEqual(getattr(error.exception, "code", None), 404)

        with self.app.test_request_context("/"):
            login_user(admin)
            self.assertEqual(_abort_if_project_forbidden(self.other_project).id, self.other_project.id)

    def test_user_scope_guard_allows_admin_and_hides_users_outside_current_project(self):
        manager = self._user(role=ROLE_MANAGER, username="scope-manager", project=self.project)
        inside = self._user(role=ROLE_GLAZIER, username="scope-inside", project=self.project)
        outside = self._user(role=ROLE_GLAZIER, username="scope-outside", project=self.other_project)
        admin = self._user(role=ROLE_ADMIN, username="scope-admin")

        with self.app.test_request_context("/"):
            login_user(manager)
            session["current_project_id"] = self.project.id
            self.assertEqual(_abort_if_user_outside_current_project(inside).id, inside.id)
            with self.assertRaises(Exception) as error:
                _abort_if_user_outside_current_project(outside)
            self.assertEqual(getattr(error.exception, "code", None), 404)

        with self.app.test_request_context("/"):
            login_user(admin)
            self.assertEqual(_abort_if_user_outside_current_project(outside, self.project).id, outside.id)

    def test_inactive_worker_cannot_be_assigned_to_project_work(self):
        active_worker = self._user(role=ROLE_GLAZIER, username="active-worker", project=self.project, active=True)
        inactive_worker = self._user(role=ROLE_GLAZIER, username="inactive-worker", project=self.project, active=False)
        manager = self._user(role=ROLE_MANAGER, username="not-worker", project=self.project)
        from app.routes import _user_can_work_in_project

        self.assertTrue(_user_can_work_in_project(active_worker, self.project))
        self.assertFalse(_user_can_work_in_project(inactive_worker, self.project))
        self.assertFalse(_user_can_work_in_project(manager, self.project))
        self.assertFalse(_user_can_work_in_project(active_worker, self.other_project))


if __name__ == "__main__":
    unittest.main()
