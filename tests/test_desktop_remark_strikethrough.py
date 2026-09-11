import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"


class DesktopRemarkStrikethroughTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = DESKTOP_CSS.read_text(encoding="utf-8")

    def test_completed_remark_cell_does_not_decorate_its_action_controls(self):
        selector = (
            r"html\.desktop-like-pointer body\.app-body:has\(\.remarks-page-head\)\s+"
            r"\.remarks-export-table-shell \.done-task \.task-text\s*"
            r"\{(?P<rules>[^}]*)\}"
        )
        match = re.search(selector, self.css)

        self.assertIsNotNone(match)
        self.assertIn("text-decoration: none !important", match.group("rules"))

    def test_completed_remark_strike_is_scoped_to_the_text(self):
        selector = (
            r"html\.desktop-like-pointer body\.app-body:has\(\.remarks-page-head\)\s+"
            r"\.remarks-export-table-shell \.done-task \.task-text \.inline-text\s*"
            r"\{(?P<rules>[^}]*)\}"
        )
        match = re.search(selector, self.css)

        self.assertIsNotNone(match)
        self.assertIn("text-decoration: line-through !important", match.group("rules"))


if __name__ == "__main__":
    unittest.main()
