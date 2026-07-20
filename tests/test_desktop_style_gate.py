import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"


class DesktopStyleGateMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = BASE_TEMPLATE.read_text(encoding="utf-8")

    def test_desktop_gate_is_enabled_before_stylesheets_are_requested(self):
        desktop_branch = self.template.index(
            "if (!isTouchAppDevice && !useAdaptiveMobileViewport)"
        )
        gate_enabled = self.template.index(
            "document.documentElement.classList.add('desktop-styles-pending')"
        )
        first_stylesheet = self.template.index("vendor/bootstrap/bootstrap.min.css")

        self.assertLess(desktop_branch, gate_enabled)
        self.assertLess(gate_enabled, first_stylesheet)

    def test_firefox_is_not_excluded_from_the_opaque_desktop_canvas(self):
        self.assertNotIn("if (!isFirefoxBrowser)", self.template)
        self.assertNotIn("const isFirefoxBrowser", self.template)

    def test_prepared_firefox_navigation_does_not_enter_the_shell_only_gate(self):
        prepared_marker = self.template.index("const preparedDesktopNavigationToken = (() =>")
        desktop_branch = self.template.index(
            "if (!isTouchAppDevice && !useAdaptiveMobileViewport)"
        )
        prepared_guard = self.template.index(
            "if (!isPreparedDesktopNavigation)", desktop_branch
        )
        gate_enabled = self.template.index(
            "document.documentElement.classList.add('desktop-styles-pending')",
            prepared_guard,
        )

        self.assertLess(prepared_marker, desktop_branch)
        self.assertLess(prepared_guard, gate_enabled)
        snapshot_restore = self.template.index(
            "window.sessionStorage.getItem(snapshotStorageKey)",
            prepared_guard,
        )
        self.assertLess(snapshot_restore, self.template.index("</head>"))

    def test_desktop_shell_canvas_stays_visible_while_body_is_pending(self):
        self.assertIn(
            "desktop-styles-pending.desktop-shell-with-sidebar::before",
            self.template,
        )
        self.assertIn(
            "html.app-root.desktop-like-pointer.desktop-styles-pending::after",
            self.template,
        )
        self.assertIn(
            "html.desktop-like-pointer.desktop-styles-pending body",
            self.template,
        )
        self.assertIn("visibility: hidden !important", self.template)
        self.assertNotIn(
            "html.touch-app-device.desktop-styles-pending body",
            self.template,
        )

    def test_gate_is_released_after_every_application_stylesheet(self):
        self.assertIn(
            "if (!root.classList.contains('desktop-like-pointer')) return",
            self.template,
        )
        release = self.template.index(
            "root.classList.remove('desktop-styles-pending')"
        )
        stylesheet_markers = (
            "vendor/bootstrap/bootstrap.min.css",
            "vendor/bootstrap/bootstrap-icons.min.css",
            "filename='style.css'",
            "filename='mobile-only.css'",
            "filename='desktop-only.css'",
        )

        for marker in stylesheet_markers:
            with self.subTest(stylesheet=marker):
                self.assertLess(self.template.index(marker), release)
        self.assertLess(release, self.template.index("</head>"))


if __name__ == "__main__":
    unittest.main()
