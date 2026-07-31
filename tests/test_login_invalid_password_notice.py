import unittest
from pathlib import Path
import re


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

    def test_mobile_auth_toast_overrides_global_mobile_toast_suppression(self):
        suppressor = self.style.index("/* v329 mobile shell cleanup")
        hidden_rule = self.style.index("html.mobile-viewport body .crm-toast-stack", suppressor)
        auth_override = self.style.index(
            "body.auth-body .auth-shell .crm-toast-stack.auth-flashes,\n"
            "html.desktop-like-pointer body.auth-body .auth-shell .crm-toast-stack.auth-flashes",
            hidden_rule,
        )

        self.assertLess(hidden_rule, auth_override)
        override_end = self.style.index("}", auth_override)
        override_rule = self.style[auth_override:override_end]
        self.assertIn("display: grid !important", override_rule)
        self.assertIn("visibility: visible !important", override_rule)
        self.assertIn("opacity: 1 !important", override_rule)

    def test_mobile_auth_toast_stays_above_bottom_footer(self):
        mobile_rule = re.search(
            r"@media \(max-width: 767\.98px\) \{\s*"
            r"html\.mobile-viewport body\.auth-body \.auth-shell \.crm-toast-stack\.auth-flashes,"
            r"(?P<body>.*?)\n\s*\}",
            self.style,
            re.DOTALL,
        )

        self.assertIsNotNone(mobile_rule)
        self.assertIn("bottom: calc(max(.85rem, env(safe-area-inset-bottom)) + 3.9rem) !important", mobile_rule.group("body"))


if __name__ == "__main__":
    unittest.main()
