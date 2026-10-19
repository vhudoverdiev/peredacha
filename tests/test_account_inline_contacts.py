import unittest
from pathlib import Path

from config import Config
from app import create_app, db
from app.models import ROLE_ADMIN, ROLE_MANAGER, User
from app.routes import short_user_display_name


ROOT = Path(__file__).resolve().parents[1]


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "account-inline-contacts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class AccountInlineContactsTests(unittest.TestCase):
    def test_contact_inputs_are_embedded_in_profile_rows(self):
        template = (ROOT / "app" / "templates" / "account.html").read_text(encoding="utf-8")

        self.assertIn("account-profile-edit-list", template)
        profile_form = template.split('<form class="account-contact-form', 1)[1].split("</form>", 1)[0]
        self.assertIn('data-account-autosave="1"', template)
        self.assertIn('<dl class="account-profile-list account-profile-edit-list">', profile_form)
        self.assertIn('id="accountFullName"', profile_form)
        self.assertIn('id="accountEmail"', profile_form)
        self.assertIn('id="accountPhone"', profile_form)
        self.assertNotIn("Сохранить контакты", profile_form)
        self.assertIn("X-Requested-With", template)
        self.assertNotIn('class="mb-3"', profile_form)
        self.assertIn("let saving = false", template)
        self.assertIn("saveAgain = true", template)
        self.assertIn("const saveUrl = form.getAttribute('action') || window.location.href", template)
        self.assertIn("fetch(saveUrl", template)
        self.assertNotIn("fetch(form.action", template)
        self.assertIn("if (!response.ok || data.ok === false)", template)
        self.assertIn("navigator.sendBeacon", template)
        self.assertNotIn("AbortController", template)
        self.assertIn("current_user.role == ROLE_ADMIN", template)
        self.assertIn("url_for('main.account_password')", template)
        self.assertIn("account-password-panel", template)
        password_panel = template.split('<div class="account-password-panel', 1)[1].split("</div>", 1)[0]
        self.assertIn("Сменить пароль", password_panel)
        self.assertNotIn("<h2>Пароль</h2>", password_panel)
        self.assertNotIn("bi bi-key\"></i></span>", password_panel)
        self.assertNotIn('name="current_password"', template)
        self.assertNotIn('name="new_password"', template)
        self.assertNotIn('name="confirm_password"', template)

    def test_password_change_fields_live_on_separate_page(self):
        account_template = (ROOT / "app" / "templates" / "account.html").read_text(encoding="utf-8")
        password_template = (ROOT / "app" / "templates" / "account_password.html").read_text(encoding="utf-8")

        self.assertIn("url_for('main.account_password')", account_template)
        self.assertIn('name="current_password"', password_template)
        self.assertIn('name="new_password"', password_template)
        self.assertIn('name="confirm_password"', password_template)
        self.assertIn("Сменить пароль", password_template)
        self.assertIn("account-back-button", password_template)
        self.assertNotIn("<h2>Пароль</h2>", password_template)
        self.assertNotIn("account-card-title account-password-title", password_template)

    def test_mobile_account_hides_password_change_entrypoint(self):
        mobile_css = (ROOT / "app" / "static" / "mobile-only.css").read_text(encoding="utf-8")

        self.assertIn("body.app-body:has(.account-page) .account-password-panel", mobile_css)
        selector_start = mobile_css.index("body.app-body:has(.account-page) .account-password-panel")
        rule_end = mobile_css.index("}", selector_start)
        rule = mobile_css[selector_start:rule_end]
        self.assertIn("display: none !important;", rule)

    def test_password_account_back_link_uses_plain_black_text_style(self):
        password_template = (ROOT / "app" / "templates" / "account_password.html").read_text(encoding="utf-8")
        style = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")

        self.assertIn('class="account-back-button"', password_template)
        self.assertIn("bi bi-arrow-left", password_template)
        self.assertIn(".account-back-button,", style)
        self.assertIn("background: transparent !important;", style)
        self.assertIn("border: 0 !important;", style)
        self.assertIn("box-shadow: none !important;", style)
        self.assertIn("color: #111827 !important;", style)

    def test_topbar_user_name_uses_surname_with_initials(self):
        self.assertEqual(
            short_user_display_name(User(full_name="Федотов Дмитрий Сергеевич", username="fedotovds")),
            "Федотов Д.С.",
        )
        self.assertEqual(
            short_user_display_name(User(full_name="Федотов Дмитрий", username="fedotovds")),
            "Федотов Д.",
        )
        self.assertEqual(short_user_display_name(User(full_name="", username="fedotovds")), "fedotovds")

    def test_account_dropdown_item_uses_default_menu_style(self):
        template = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        style = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")

        self.assertNotIn("account-dropdown-item", template)
        self.assertNotIn(".dropdown-item.account-dropdown-item", style)

    def test_two_factor_start_uses_ajax_without_page_reload(self):
        template = (ROOT / "app" / "templates" / "account.html").read_text(encoding="utf-8")
        routes = (ROOT / "app" / "routes.py").read_text(encoding="utf-8")

        self.assertIn('data-account-2fa-start="1"', template)
        self.assertIn("event.preventDefault()", template)
        self.assertIn("const startUrl = form.getAttribute('action') || window.location.href", template)
        self.assertIn("fetch(startUrl", template)
        self.assertIn("pending_secret=pending_secret", routes)
        self.assertIn("qr_data_uri=qr_svg_data_uri(provisioning)", routes)


class AccountAutosaveContactsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username="autosave-user", role=ROLE_MANAGER, captcha_disabled=True)
        self.user.set_password("Strong-test-password-2026!")
        db.session.add(self.user)
        db.session.commit()
        self.client = self.app.test_client()
        self.client.post("/login", data={"username": self.user.username, "password": "Strong-test-password-2026!"})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_account_contacts_autosave_returns_json_without_redirect(self):
        response = self.client.post(
            "/account",
            data={
                "action": "update_contacts",
                "full_name": "Иванов Иван Иванович",
                "email": "ivanov@example.test",
                "phone": "8 900 000-00-00",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "message": "Контакты сохранены."})
        updated = db.session.get(User, self.user.id)
        self.assertEqual(updated.full_name, "Иванов Иван Иванович")
        self.assertEqual(updated.email, "ivanov@example.test")
        self.assertEqual(updated.phone, "8 900 000-00-00")

    def test_account_hides_role_for_non_developer(self):
        response = self.client.get("/account")

        html = response.get_data(as_text=True)
        self.assertNotIn("<dt>Роль</dt>", html)
        self.assertNotIn("Инженер", html)

    def test_account_shows_role_for_developer(self):
        self.user.role = ROLE_ADMIN
        db.session.commit()

        response = self.client.get("/account")

        html = response.get_data(as_text=True)
        self.assertIn("<dt>Роль</dt>", html)
        self.assertIn("Разработчик", html)

    def test_account_password_change_updates_current_user_password(self):
        response = self.client.post(
            "/account/password",
            data={
                "current_password": "Strong-test-password-2026!",
                "new_password": "Another-strong-password-2026!",
                "confirm_password": "Another-strong-password-2026!",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        updated = db.session.get(User, self.user.id)
        self.assertFalse(updated.check_password("Strong-test-password-2026!"))
        self.assertTrue(updated.check_password("Another-strong-password-2026!"))


if __name__ == "__main__":
    unittest.main()
