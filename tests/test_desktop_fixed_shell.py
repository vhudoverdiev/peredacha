import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"


class DesktopFixedShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        css = DESKTOP_CSS.read_text(encoding="utf-8")
        marker = "/* Cross-browser desktop shell."
        cls.shell_css = css[css.index(marker) :]

    def test_sidebar_and_topbar_use_fixed_positioning(self):
        self.assertIn(".app-layout > .app-sidebar", self.shell_css)
        self.assertIn(".app-main > .app-topbar", self.shell_css)
        self.assertGreaterEqual(self.shell_css.count("position: fixed !important"), 3)
        self.assertNotIn("position: sticky", self.shell_css)

    def test_main_content_reserves_fixed_shell_space(self):
        self.assertIn(
            "margin-left: var(--desktop-sidebar-width, 230px) !important",
            self.shell_css,
        )
        self.assertIn("padding-top: 4.9rem !important", self.shell_css)

    def test_fixed_shell_stays_below_modal_layer(self):
        self.assertIn("z-index: 1040 !important", self.shell_css)
        self.assertGreaterEqual(self.shell_css.count("z-index: 1035 !important"), 2)

    def test_standalone_desktop_pages_reserve_their_topbar(self):
        self.assertIn("padding-top: 5.75rem !important", self.shell_css)
        self.assertIn(
            "width: var(--desktop-reference-width, 1920px) !important",
            self.shell_css,
        )


if __name__ == "__main__":
    unittest.main()
