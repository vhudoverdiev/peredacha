import re
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

    def test_login_template_renders_inline_alert_when_password_is_invalid(self):
        self.assertIn("{% if login_error_message %}", self.template)
        self.assertIn('class="login-auth-alert alert alert-danger"', self.template)
        self.assertIn('role="alert"', self.template)
        self.assertIn('aria-live="assertive"', self.template)
        self.assertIn("{{ login_error_message }}", self.template)

    def test_inline_alert_is_scoped_to_login_card_and_keeps_stable_geometry(self):
        alert_rule = re.search(r"\.login-auth-alert\s*\{(?P<body>.*?)\}", self.style, re.DOTALL)
        self.assertIsNotNone(alert_rule)
        rule_body = alert_rule.group("body")

        self.assertIn("display: grid !important", rule_body)
        self.assertIn("grid-template-columns: 1.25rem minmax(0, 1fr)", rule_body)
        self.assertIn("margin: 0 0 1rem !important", rule_body)
        self.assertIn("background: #fef2f2 !important", rule_body)
        self.assertIn("overflow-wrap: anywhere", self.style)


if __name__ == "__main__":
    unittest.main()
