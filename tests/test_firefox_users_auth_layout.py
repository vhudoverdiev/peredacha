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
        self.assertIn("transform: translateY(-50%);", self.style)

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
