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
    ROLE_LABELS,
    ROLE_MANAGER,
    ROLE_OFFICE,
    ROLE_OFFICE_MANAGER,
    ROLE_PAINTER,
    ROLE_SUPERVISOR,
    ROLE_VIEWER,
    ROLES,
    Task,
    User,
    USER_ROLE_CHOICES,
    WORKER_ROLES,
)
from app.permissions import can_change_task, can_export, can_manage_mapping, can_manage_sync, readonly, role_required
from app.routes import (
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
            ROLE_SUPERVISOR: "main.dashboard",
            ROLE_OFFICE: "main.dashboard",
            ROLE_VIEWER: "main.dashboard",
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
            "main.my_inspections",
            "main.my_task_done",
            "main.my_task_return",
            "main.my_task_status",
            "main.my_task_comment",
            "main.my_task_comment_delete",
            "main.account",
            "main.account_password",
            "main.report_error",
            "main.messenger_thread",
            "main.messenger_send",
            "main.messenger_read",
            "main.messenger_error_replies_read",
        })
        self.assertTrue(WORKER_ROLES.issuperset({ROLE_EXECUTOR, ROLE_PAINTER, ROLE_HANDYMAN, ROLE_GLAZIER}))

    def test_verifier_role_is_removed_from_project_roles(self):
        self.assertNotIn("verifier", ROLES)
        self.assertNotIn("verifier", ROLE_LABELS)
        self.assertNotIn("verifier", dict(USER_ROLE_CHOICES))

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

    def test_permission_helpers_reserve_sync_and_mapping_for_admin(self):
        users = {
            role: self._user(role=role, username=f"perm-{role}")
            for role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_OFFICE, ROLE_VIEWER, ROLE_GLAZIER)
        }

        for role, user in users.items():
            with self.subTest(role=role):
                self.assertEqual(can_manage_sync(user), role == ROLE_ADMIN)
                self.assertEqual(can_manage_mapping(user), role == ROLE_ADMIN)
                self.assertEqual(can_export(user), role in {ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_OFFICE})
                self.assertEqual(readonly(user), role == ROLE_VIEWER)

    def test_can_change_task_allows_managers_and_assigned_workers_only(self):
        admin = self._user(role=ROLE_ADMIN, username="change-admin")
        manager = self._user(role=ROLE_MANAGER, username="change-manager")
        supervisor = self._user(role=ROLE_SUPERVISOR, username="change-supervisor")
        worker = self._user(role=ROLE_GLAZIER, username="change-worker")
        other_worker = self._user(role=ROLE_HANDYMAN, username="change-other")
        viewer = self._user(role=ROLE_VIEWER, username="change-viewer")
        task = Task(source_uid="access-change-task", project_id=self.project.id, apartment_id=1, work_point_id=1, responsible_id=worker.id)

        self.assertTrue(can_change_task(admin, task))
        self.assertTrue(can_change_task(manager, task))
        self.assertTrue(can_change_task(supervisor, task))
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

        self.assertEqual(response.status_code, 303)
        self.assertIn("/login", response.headers["Location"])
        self.assertIn("next=/tasks", response.headers["Location"])

    def test_public_error_and_service_worker_endpoints_bypass_auth(self):
        for endpoint in ("main.report_error", "main.service_worker", "main.service_worker_reset"):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._guard(None, endpoint))

    def test_admin_and_manager_bypass_general_role_restrictions(self):
        for role in (ROLE_ADMIN, ROLE_MANAGER):
            with self.subTest(role=role):
                user = self._user(role=role, username=f"bypass-{role}")
                self.assertIsNone(self._guard(user, "main.users"))
                self.assertIsNone(self._guard(user, "main.assignment_manual_task_new"))

        admin = self._user(role=ROLE_ADMIN, username="admin-service-access")
        self.assertIsNone(self._guard(admin, "main.mapping_settings", method="POST"))

    def test_office_manager_keeps_apartments_but_cannot_open_operational_sections(self):
        user = self._user(role=ROLE_OFFICE_MANAGER, username="office-manager-sections")
        self.assertIsNone(self._guard(user, "main.apartments"))
        self.assertIsNone(self._guard(user, "main.apartment_detail"))
        self.assertIsNone(self._guard(user, "main.records"))
        for endpoint in (
            "main.task_list",
            "main.task_detail",
            "main.contractors_list",
            "main.assignments",
            "main.materials",
            "main.glass_measurements",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertRedirectsTo(self._guard(user, endpoint), "/")

    def test_office_manager_cannot_change_inspection_or_task_status(self):
        user = self._user(role=ROLE_OFFICE_MANAGER, username="office-manager-mutations")
        for endpoint in (
            "main.update_apartment_inspection_status",
            "main.update_apartment_inspection_date",
            "main.delete_apartment_inspection_date",
            "main.update_apartment_inspection_note",
            "main.quick_status",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(Forbidden):
                self._guard(user, endpoint, method="POST")

    def test_office_manager_comment_and_non_inspection_apartment_edits_remain_available(self):
        user = self._user(role=ROLE_OFFICE_MANAGER, username="office-manager-apartment")
        for endpoint in (
            "main.update_apartment_office_manager_comment",
            "main.update_apartment_details",
            "main.update_apartment_app_status",
            "main.update_apartment_avr_status",
            "main.update_apartment_addendum_status",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._guard(user, endpoint, method="POST"))

    def test_closed_section_screen_returns_back_without_logging_user_out(self):
        client = self.app.test_client()
        user = self._user(role=ROLE_MANAGER, username="closed-section-back")
        db.session.add(AppSetting(key="blocked_site_sections", value="remarks"))
        db.session.commit()
        with client.session_transaction() as session_data:
            session_data["_user_id"] = str(user.id)
            session_data["_fresh"] = True
            session_data["session_version"] = int(user.session_version or 0)
        page = client.get("/tasks").get_data(as_text=True)
        self.assertIn(">Назад\n", page)
        self.assertNotIn(">Выйти", page)
        self.assertNotIn('action="/logout"', page)

    def test_office_role_matches_manager_except_restricted_sections(self):
        office = self._user(role=ROLE_OFFICE, username="office-access", project=self.project)

        self.assertTrue(office.can(ROLE_MANAGER))
        self.assertFalse(office.can(ROLE_ADMIN))

        for endpoint in (
            "main.dashboard",
            "main.task_list",
            "main.task_new",
            "main.contractors_list",
            "main.apartments",
            "main.work_report",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._guard(office, endpoint))

        for endpoint in (
            "main.assignments",
            "main.assignment_manual_task_new",
            "main.glass_measurements",
            "main.glass_order",
            "main.materials",
            "main.material_request_detail",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertRedirectsTo(self._guard(office, endpoint), "/")

        with self.assertRaises(Forbidden):
            self._guard(office, "main.material_request_new", method="POST")
        for endpoint in (
            "main.add_task_comment",
            "main.update_apartment_comment",
            "main.update_apartment_inspection_note",
            "main.update_apartment_po_status",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(Forbidden):
                    self._guard(office, endpoint, method="POST")

    def test_supervisor_role_matches_manager_except_admin_and_service_sections(self):
        supervisor = self._user(role=ROLE_SUPERVISOR, username="supervisor-access", project=self.project)

        self.assertTrue(supervisor.can(ROLE_MANAGER))
        self.assertFalse(supervisor.can(ROLE_ADMIN))

        for endpoint in (
            "main.dashboard",
            "main.task_list",
            "main.task_new",
            "main.contractors_list",
            "main.apartments",
            "main.assignments",
            "main.glass_measurements",
            "main.materials",
            "main.work_report",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._guard(supervisor, endpoint))

        for endpoint in (
            "main.users",
            "main.site_settings",
            "main.site_errors",
            "main.developer_statistics",
            "main.upload_excel",
            "main.sync_logs",
            "main.mapping_settings",
            "main.export_source_with_strikes",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertRedirectsTo(self._guard(supervisor, endpoint), "/")

    def test_manager_cannot_open_service_tools(self):
        manager = self._user(role=ROLE_MANAGER, username="manager-service-access")

        for endpoint in (
            "main.upload_excel",
            "main.sync_logs",
            "main.sync_log_details",
            "main.delete_sync_log",
            "main.rollback_sync_log",
            "main.sync_conflicts",
            "main.resolve_conflict",
            "main.resolve_conflicts_bulk",
            "main.mapping_settings",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(Forbidden):
                    self._guard(manager, endpoint)

    def test_worker_can_open_allowed_pages_but_get_is_redirected_from_backoffice(self):
        worker = self._user(role=ROLE_GLAZIER, username="worker-access")

        self.assertIsNone(self._guard(worker, "main.my_tasks"))
        self.assertIsNone(self._guard(worker, "main.account"))
        self.assertIsNone(self._guard(worker, "main.account_password"))
        self.assertRedirectsTo(self._guard(worker, "main.task_list"), "/my-tasks")
        self.assertRedirectsTo(self._guard(worker, "main.users"), "/my-tasks")

    def test_worker_post_to_forbidden_endpoint_is_403(self):
        worker = self._user(role=ROLE_GLAZIER, username="worker-post")

        with self.assertRaises(Forbidden):
            self._guard(worker, "main.update_task", method="POST")

    def test_viewer_can_read_allowed_pages_but_cannot_open_write_pages(self):
        viewer = self._user(role=ROLE_VIEWER, username="viewer-read")

        for endpoint in ("main.dashboard", "main.task_list", "main.task_detail", "main.apartments", "main.materials", "main.account", "main.account_password"):
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
        self.assertEqual(self._guard(manager, "main.dashboard")[1], 503)

    def test_mobile_home_endpoint_respects_role_and_project_selection(self):
        worker = self._user(role=ROLE_PAINTER, username="mobile-worker", project=self.project)
        manager = self._user(role=ROLE_MANAGER, username="mobile-manager", all_projects=True)

        with self.app.test_request_context("/", headers={"User-Agent": MOBILE_UA}):
            login_user(worker)
            self.assertEqual(_mobile_phone_home_endpoint(), "main.my_tasks")

        with self.app.test_request_context("/", headers={"User-Agent": MOBILE_UA}):
            login_user(manager)
            self.assertEqual(_mobile_phone_home_endpoint(), "main.objects")
            session["current_project_id"] = self.project.id
            self.assertEqual(_mobile_phone_home_endpoint(), "main.dashboard")

    def test_mobile_allowed_endpoints_are_role_specific(self):
        cases = (
            (ROLE_GLAZIER, "main.my_tasks", "main.assignments"),
            (ROLE_MANAGER, "main.assignments", "main.users"),
            (ROLE_SUPERVISOR, "main.assignments", "main.users"),
            (ROLE_OFFICE, "main.task_list", "main.assignments"),
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

    def test_mobile_under_development_setting_blocks_phone_access(self):
        manager = self._user(role=ROLE_MANAGER, username="mobile-dev-manager", project=self.project)
        admin = self._user(role=ROLE_ADMIN, username="mobile-dev-admin")
        db.session.add(AppSetting(key="mobile_version_under_development", value="1"))
        db.session.commit()

        response = self._guard(manager, "main.dashboard", mobile=True)
        self.assertIsInstance(response, tuple)
        self.assertEqual(response[1], 503)
        with self.assertRaises(Forbidden):
            self._guard(manager, "main.update_task", method="POST", mobile=True)
        self.assertEqual(self._guard(manager, "main.account", mobile=True)[1], 503)
        self.assertIsNone(self._guard(admin, "main.site_settings", mobile=True))
        self.assertIsNone(self._guard(admin, "main.dashboard", mobile=True))
        self.assertIsNone(self._guard(admin, "main.dashboard", mobile=False))

    def test_site_settings_post_persists_all_toggles_and_section_locks(self):
        admin = self._user(role=ROLE_ADMIN, username="settings-save-admin")
        client = self.app.test_client()
        with client.session_transaction() as session_data:
            session_data["_user_id"] = str(admin.id)
            session_data["_fresh"] = True
            session_data["session_version"] = int(admin.session_version or 0)

        response = client.post(
            "/settings",
            data={
                "mobile_version_under_development": "1",
                "site_maintenance_mode": "1",
                "two_factor_every_login": "1",
                "blocked_site_sections": ["dashboard", "materials", "unknown"],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        settings = {row.key: row.value for row in AppSetting.query.all()}
        self.assertNotIn("hide_documents_section", settings)
        self.assertEqual(settings["mobile_version_under_development"], "1")
        self.assertEqual(settings["site_maintenance_mode"], "1")
        self.assertEqual(settings["two_factor_every_login"], "1")
        self.assertNotIn("enable_messenger", settings)
        self.assertEqual(settings["blocked_site_sections"], "dashboard,materials")

    def test_main_section_locks_cover_nested_actions_and_legacy_keys(self):
        admin = self._user(role=ROLE_MANAGER, username="group-lock-manager")
        setting = AppSetting(key="blocked_site_sections", value="assignments,remarks,administration")
        db.session.add(setting)
        db.session.commit()
        for endpoint in ("main.my_task_status", "main.my_task_comment",
                         "main.export_category_tasks_pdf"):
            with self.subTest(endpoint=endpoint):
                response = self._guard(admin, endpoint, method="POST")
                self.assertEqual(response[1], 503)
        self.assertIsNone(self._guard(admin, "main.assignments_report"))
        setting.value = "report"
        db.session.commit()
        self.assertEqual(self._guard(admin, "main.assignments_report")[1], 503)
        self.assertIsNone(self._guard(admin, "main.assignments"))
        developer = self._user(role=ROLE_ADMIN, username="group-lock-developer")
        self.assertIsNone(self._guard(developer, "main.assignments"))
        self.assertIsNone(self._guard(developer, "main.site_settings"))
        setting.value = "avr"
        db.session.commit()
        self.assertIsNone(self._guard(admin, "main.apartments"))
        self.assertEqual(self._guard(admin, "main.avr")[1], 503)
        setting.value = "apartments"
        db.session.commit()
        self.assertEqual(self._guard(admin, "main.apartments")[1], 503)
        self.assertIsNone(self._guard(admin, "main.avr"))
        setting.value = "objects,administration,users,service"
        db.session.commit()
        self.assertEqual(self._guard(admin, "main.dashboard")[1], 503)
        self.assertIsNone(self._guard(admin, "main.objects"))
        self.assertIsNone(self._guard(admin, "main.users"))
        with self.assertRaises(Forbidden):
            self._guard(admin, "main.mapping_settings")

    def test_documents_removed_and_settings_show_only_main_sections(self):
        admin = self._user(role=ROLE_ADMIN, username="removed-documents-admin")
        client = self.app.test_client()
        with client.session_transaction() as state:
            state["_user_id"] = str(admin.id)
            state["_fresh"] = True
            state["session_version"] = int(admin.session_version or 0)
        for path in ("/documents", "/documents/addendum", "/documents/download/test.docx"):
            self.assertEqual(client.get(path).status_code, 404)
        self.assertEqual(client.post("/documents/addendum").status_code, 404)
        page = client.get("/settings").get_data(as_text=True)
        self.assertNotIn('href="/documents"', page)
        self.assertNotIn('hide-documents-setting', page)
        self.assertEqual(page.count('name="blocked_site_sections"'), 12)
        self.assertNotIn('section-lock-worker_tasks', page)
        self.assertNotIn('section-lock-administration', page)
        self.assertNotIn('section-lock-objects', page)
        self.assertIn('section-lock-dashboard', page)
        self.assertIn('section-lock-apartments', page)
        self.assertIn('section-lock-avr', page)
        from app.routes import _section_lock_controls
        self.assertEqual([item['label'] for item in _section_lock_controls()],
                         ['Главная','Замечания','Подрядчики','Помещения','АВР',
                          'Расход материалов','Замеры','Выдача задач','Обращения','Записи','Отчет','Для разработчика'])

    def test_brand_opens_object_selection_except_three_worker_roles(self):
        from html.parser import HTMLParser
        class Links(HTMLParser):
            def __init__(self):
                super().__init__(); self.targets = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                classes = set(attrs.get('class','').split())
                if tag == 'a' and classes & {'sidebar-brand-link','mobile-shell-brand','mobile-top-avatar'}:
                    self.targets.append(attrs.get('href'))
        client = self.app.test_client()
        from flask import g
        for role in ROLES:
            user = self._user(role=role,project=self.project,username='brand-'+role)
            g.pop('_login_user',None)
            with client.session_transaction() as state:
                state['_user_id']=str(user.id); state['_fresh']=True
                state['session_version']=int(user.session_version or 0)
                state['current_project_id']=self.project.id
            for mobile in (False,True):
                with self.subTest(role=role,mobile=mobile):
                    page=client.get('/account',headers={'User-Agent':MOBILE_UA} if mobile else {})
                    self.assertEqual(page.status_code,200)
                    parser=Links(); parser.feed(page.get_data(as_text=True))
                    target='/my-tasks' if role in {ROLE_PAINTER,ROLE_HANDYMAN,ROLE_GLAZIER} else '/objects'
                    self.assertTrue(parser.targets)
                    self.assertTrue(all(href==target for href in parser.targets),parser.targets)
                    self.assertEqual(client.get(target,headers={'User-Agent':MOBILE_UA} if mobile else {}).status_code,200)

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
