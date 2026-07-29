import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLE_PATH = ROOT / "app" / "static" / "style.css"


class FirefoxUsersAuthLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.style = STYLE_PATH.read_text(encoding="utf-8")
        cls.firefox_css = cls.style[cls.style.index("/* v629: Firefox on desktop") :]

    def test_firefox_motion_rule_does_not_reveal_hidden_role_radios(self):
        visibility_rule = re.search(
            r"/\* Only the animated containers need their final visibility\."
            r".*?\*/(?P<selectors>.*?)\{\s*opacity:\s*1\s*!important;",
            self.firefox_css,
            re.DOTALL,
        )
        self.assertIsNotNone(visibility_rule)
        self.assertNotIn(".crm-page-entry-surface *", visibility_rule.group("selectors"))
        self.assertNotIn(".auth-shell *", visibility_rule.group("selectors"))
        self.assertIn(
            ".users-page .users-role-input {\n"
            "  position: absolute;\n"
            "  opacity: 0;",
            self.style,
        )

    def test_firefox_motion_rule_keeps_login_icon_alignment_transforms(self):
        geometry_rule = re.search(
            r"(?P<selectors>[^{}]+)\{\s*transform:\s*none\s*!important;"
            r"\s*translate:\s*none\s*!important;"
            r"\s*scale:\s*none\s*!important;",
            self.firefox_css,
            re.DOTALL,
        )
        self.assertIsNotNone(geometry_rule)
        self.assertNotIn(".crm-page-entry-surface *", geometry_rule.group("selectors"))
        self.assertNotIn(".auth-shell *", geometry_rule.group("selectors"))
        self.assertNotIn(".auth-footer", geometry_rule.group("selectors"))
        self.assertIn("transform: translateY(-50%);", self.style)

    def test_firefox_keeps_auth_credit_and_users_table_geometry(self):
        template = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn(
            '<span class="auth-footer-line-main">CRM от Худовердиева В.С.</span>',
            template,
        )
        self.assertIn(
            "body.app-body:has(.users-page) .users-table {\n"
            "    width: 100% !important;\n"
            "    min-width: 0 !important;\n"
            "    max-width: 100% !important;\n"
            "    table-layout: fixed !important;",
            self.style,
        )
        self.assertNotIn(".users-table *", self.firefox_css)

    def test_firefox_releases_apartment_cards_when_entry_animation_is_disabled(self):
        self.assertRegex(
            self.firefox_css,
            r"desktop-firefox-stable-motion[^{]*"
            r":is\(\.objects-grid,\s*\.apartments-grid,[^)]*\)\s*>\s*\*\s*\{"
            r"\s*opacity:\s*1\s*!important;",
        )

    def test_selected_user_role_uses_question_button_green_tokens(self):
        role_rules = re.findall(
            r"body\.app-body:has\(\.users-page\) "
            r"\.users-role-option:has\(\.users-role-input:checked\) \{"
            r"(?P<body>.*?)\}",
            self.style,
            re.DOTALL,
        )
        self.assertTrue(role_rules)
        final_rule = role_rules[-1]
        self.assertIn("var(--peredacha-action-green)", final_rule)
        self.assertIn("var(--peredacha-action-green-hover)", final_rule)
        self.assertIn("var(--peredacha-action-green-shadow)", final_rule)


if __name__ == "__main__":
    unittest.main()
