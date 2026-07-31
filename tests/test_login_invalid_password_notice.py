import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGIN_TEMPLATE = ROOT / "app" / "templates" / "login.html"
STYLE_CSS = ROOT / "app" / "static" / "style.css"


class LoginInvalidPasswordNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = LOGIN_TEMPLATE.read_text(encoding="utf-8")
        cls.style = STYLE_CSS.read_text(encoding="utf-8")

    def test_login_template_does_not_render_duplicate_inline_password_alert(self):
        self.assertNotIn("login_error_message", self.template)
        self.assertNotIn("login-auth-alert", self.template)
        self.assertNotIn('aria-live="assertive"', self.template)

    def test_auth_flash_toasts_are_anchored_to_bottom_on_web_and_desktop(self):
        self.assertNotIn(".login-auth-alert", self.style)
        self.assertIn("body.auth-body .auth-shell .crm-toast-stack.auth-flashes", self.style)
        self.assertIn("bottom: max(1.05rem, env(safe-area-inset-bottom)) !important", self.style)
        self.assertIn("html.desktop-like-pointer body.auth-body .auth-shell .crm-toast-stack.auth-flashes", self.style)


if __name__ == "__main__":
    unittest.main()
