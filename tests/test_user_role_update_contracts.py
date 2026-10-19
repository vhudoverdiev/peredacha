import unittest
from pathlib import Path

from config import Config
from app import create_app, db, login_manager
from app.models import (
    ROLE_ADMIN,
    ROLE_GLAZIER,
    ROLE_MANAGER,
    ROLE_OFFICE,
    ROLE_PAINTER,
    ROLE_SUPERVISOR,
    ChatMessage,
    Project,
    SecurityEvent,
    SiteErrorReport,
    User,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "user-role-update-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class UserRoleUpdateContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.project = Project(name="Role update project")
        self.other_project = Project(name="Second role update project")
        db.session.add_all([self.project, self.other_project])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def _user(self, username, role=ROLE_MANAGER):
        user = User(
            username=username,
            role=role,
            is_active=True,
            captcha_disabled=True,
            project_id=self.project.id,
        )
        user.set_password("correct-password")
        db.session.add(user)
        db.session.commit()
        return user

    def _login(self, user):
        response = self.client.post(
            "/login",
            data={"username": user.username, "password": "correct-password"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def test_admin_can_update_another_users_role(self):
        admin = self._user("admin", ROLE_ADMIN)
        user = self._user("worker", ROLE_MANAGER)
        self._login(admin)

        response = self.client.post(
            f"/users/{user.id}/role",
            data={"role": ROLE_PAINTER},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["role"], ROLE_PAINTER)
        self.assertEqual(db.session.get(User, user.id).role, ROLE_PAINTER)

    def test_users_page_role_select_has_resilient_autosave_handlers(self):
        script = Path("app/static/script.js").read_text(encoding="utf-8")

        self.assertIn("const saveRole = async () =>", script)
        self.assertIn("select.addEventListener('change', saveRole)", script)
        self.assertIn("select.addEventListener('input', saveRole)", script)
        self.assertIn("form.addEventListener('submit'", script)
        self.assertNotIn("select.disabled = true", script)
        self.assertIn("select.setAttribute('aria-busy', 'true')", script)
        self.assertIn("if (select.value !== savedValue) saveRole();", script)

    def test_users_table_does_not_render_password_column(self):
        template = Path("app/templates/users.html").read_text(encoding="utf-8")

        self.assertNotIn('class="users-col-password"', template)
        self.assertNotIn("<th>Пароль</th>", template)
        self.assertNotIn('class="users-password-cell"', template)
        self.assertNotIn("password-preview", template)

    def test_user_password_forms_have_generate_button(self):
        users_template = Path("app/templates/users.html").read_text(encoding="utf-8")
        reset_template = Path("app/templates/user_password.html").read_text(encoding="utf-8")
        script = Path("app/static/script.js").read_text(encoding="utf-8")
        style = Path("app/static/style.css").read_text(encoding="utf-8")
        desktop_style = Path("app/static/desktop-only.css").read_text(encoding="utf-8")

        self.assertIn('data_generated_password_target="create-user"', users_template)
        self.assertIn('data-generate-password="create-user"', users_template)
        self.assertIn('data_generated_password_target="reset-user"', reset_template)
        self.assertIn('data-generate-password="reset-user"', reset_template)
        self.assertIn("const generatePassword = (length = 14)", script)
        self.assertIn("window.crypto?.getRandomValues", script)
        self.assertIn("field.type = 'text'", script)
        start = style.index(".password-generate-btn,")
        end = style.index("@media (max-width: 575.98px)", start)
        rule = style[start:end]
        self.assertIn("var(--peredacha-action-green)", rule)
        self.assertIn("var(--peredacha-action-green-hover)", rule)
        self.assertIn("color: #ffffff !important", rule)
        self.assertNotIn("rgba(121,191,37,.08)", rule)
        self.assertIn(".btn.btn-outline-primary.password-generate-btn:active", style)
        self.assertIn("--bs-btn-active-color: #ffffff", style)
        self.assertIn(".btn.btn-outline-primary.password-generate-btn:active *::before", style)
        self.assertIn("html.desktop-like-pointer body.app-body .btn.btn-outline-primary.password-generate-btn:active", desktop_style)
        self.assertIn("--bs-btn-active-color: #ffffff !important", desktop_style)

    def test_admin_can_update_user_to_office_role(self):
        admin = self._user("admin-office", ROLE_ADMIN)
        user = self._user("worker-office", ROLE_MANAGER)
        self._login(admin)

        response = self.client.post(
            f"/users/{user.id}/role",
            data={"role": ROLE_OFFICE},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["role"], ROLE_OFFICE)
        self.assertEqual(db.session.get(User, user.id).role, ROLE_OFFICE)

    def test_admin_can_update_user_to_supervisor_role(self):
        admin = self._user("admin-supervisor", ROLE_ADMIN)
        user = self._user("worker-supervisor", ROLE_MANAGER)
        self._login(admin)

        response = self.client.post(
            f"/users/{user.id}/role",
            data={"role": ROLE_SUPERVISOR},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["role"], ROLE_SUPERVISOR)
        self.assertEqual(db.session.get(User, user.id).role, ROLE_SUPERVISOR)

    def test_admin_can_grant_all_projects_access_from_users_table(self):
        admin = self._user("admin-all-projects", ROLE_ADMIN)
        user = self._user("manager-all-projects", ROLE_MANAGER)
        self._login(admin)

        response = self.client.post(
            f"/users/{user.id}/projects",
            data={"all_projects_access": "1"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["all_projects_access"])
        self.assertEqual(data["label"], "Все объекты")
        updated = db.session.get(User, user.id)
        self.assertTrue(updated.can_access_all_projects)
        self.assertTrue(updated.can_access_project(self.project))
        self.assertTrue(updated.can_access_project(self.other_project))

    def test_admin_can_create_office_user_with_all_projects_access(self):
        admin = self._user("admin-create-all-projects", ROLE_ADMIN)
        self._login(admin)

        response = self.client.post(
            "/users",
            data={
                "username": "office-all-projects",
                "full_name": "Офис Все Объекты",
                "password": "correct-password",
                "role": ROLE_OFFICE,
                "all_projects_access": "1",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        created = User.query.filter_by(username="office-all-projects").one()
        self.assertEqual(created.role, ROLE_OFFICE)
        self.assertTrue(created.can_access_all_projects)
        self.assertTrue(created.can_access_project(self.project))
        self.assertTrue(created.can_access_project(self.other_project))

    def test_role_update_rejects_invalid_role(self):
        admin = self._user("admin-invalid", ROLE_ADMIN)
        user = self._user("worker-invalid", ROLE_MANAGER)
        self._login(admin)

        response = self.client.post(
            f"/users/{user.id}/role",
            data={"role": "owner"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])
        self.assertEqual(db.session.get(User, user.id).role, ROLE_MANAGER)

    def test_admin_cannot_update_own_role_from_users_table(self):
        admin = self._user("admin-self", ROLE_ADMIN)
        self._login(admin)

        response = self.client.post(
            f"/users/{admin.id}/role",
            data={"role": ROLE_GLAZIER},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])
        self.assertEqual(db.session.get(User, admin.id).role, ROLE_ADMIN)

    def test_admin_cannot_update_another_admin_role_from_users_table(self):
        admin = self._user("admin-actor", ROLE_ADMIN)
        other_admin = self._user("admin-target", ROLE_ADMIN)
        self._login(admin)

        response = self.client.post(
            f"/users/{other_admin.id}/role",
            data={"role": ROLE_GLAZIER},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])
        self.assertEqual(db.session.get(User, other_admin.id).role, ROLE_ADMIN)

    def test_admin_can_delete_user_with_security_events(self):
        admin = self._user("admin-delete", ROLE_ADMIN)
        user = self._user("worker-delete", ROLE_MANAGER)
        event = SecurityEvent(user_id=user.id, kind="login_failed", severity="warning", ip_address="203.0.113.44")
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        self._login(admin)

        response = self.client.post(f"/users/{user.id}/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(User, user.id))
        detached_event = db.session.get(SecurityEvent, event_id)
        self.assertIsNotNone(detached_event)
        self.assertIsNone(detached_event.user_id)

    def test_admin_can_delete_user_with_chat_messages_and_error_replies(self):
        admin = self._user("admin-delete-chat", ROLE_ADMIN)
        user = self._user("worker-delete-chat", ROLE_MANAGER)
        message_from_user = ChatMessage(
            project_id=self.project.id,
            sender_id=user.id,
            recipient_id=admin.id,
            body="Нужно проверить",
        )
        message_to_user = ChatMessage(
            project_id=self.project.id,
            sender_id=admin.id,
            recipient_id=user.id,
            body="Проверяю",
        )
        report = SiteErrorReport(
            kind="user",
            message="Проверка удаления",
            status="new",
            user_id=user.id,
            developer_reply="Ответ",
            developer_reply_user_id=user.id,
        )
        db.session.add_all([message_from_user, message_to_user, report])
        db.session.commit()
        report_id = report.id
        self._login(admin)

        response = self.client.post(f"/users/{user.id}/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(db.session.get(User, user.id))
        self.assertEqual(ChatMessage.query.count(), 0)
        detached_report = db.session.get(SiteErrorReport, report_id)
        self.assertIsNotNone(detached_report)
        self.assertIsNone(detached_report.user_id)
        self.assertIsNone(detached_report.developer_reply_user_id)


if __name__ == "__main__":
    unittest.main()
