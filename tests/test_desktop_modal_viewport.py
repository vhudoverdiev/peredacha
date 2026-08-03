import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
MOBILE_CSS = PROJECT_ROOT / "app" / "static" / "mobile-only.css"
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class DesktopModalViewportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_bootstrap_modals_are_fixed_to_visible_desktop_viewport(self):
        selector = "html.desktop-like-pointer body.app-body .modal.show"
        self.assertIn(selector, self.desktop_css)
        start = self.desktop_css.index(selector)
        rule = self.desktop_css[start : self.desktop_css.index("}", start)]

        self.assertIn("position: fixed !important", rule)
        self.assertIn("inset: 0 !important", rule)
        self.assertIn("height: 100dvh !important", rule)
        self.assertIn("overflow: hidden !important", rule)
        self.assertIn("pointer-events: auto !important", rule)

    def test_modal_content_scrolls_instead_of_hiding_action_buttons(self):
        dialog_selector = "html.desktop-like-pointer body.app-body .modal.show .modal-dialog"
        content_selector = "html.desktop-like-pointer body.app-body .modal.show .modal-content"
        body_selector = "html.desktop-like-pointer body.app-body .modal.show .modal-body"

        for selector in (dialog_selector, content_selector):
            with self.subTest(selector=selector):
                start = self.desktop_css.index(selector)
                rule = self.desktop_css[start : self.desktop_css.index("}", start)]
                self.assertIn("max-height: calc(100dvh - 2rem) !important", rule)

        dialog_rule = self.desktop_css[
            self.desktop_css.index(dialog_selector) : self.desktop_css.index("}", self.desktop_css.index(dialog_selector))
        ]
        self.assertIn("zoom: 1 !important", dialog_rule)
        self.assertIn("display: block !important", dialog_rule)
        self.assertIn("height: auto !important", dialog_rule)

        body_rule = self.desktop_css[
            self.desktop_css.index(body_selector) : self.desktop_css.index("}", self.desktop_css.index(body_selector))
        ]
        self.assertIn("flex: 0 1 auto !important", body_rule)
        self.assertIn("max-height: calc(100dvh - 10rem) !important", body_rule)
        self.assertIn("overflow-y: auto !important", body_rule)

    def test_custom_confirm_overlays_are_also_viewport_bound(self):
        selector = "html.desktop-like-pointer body.app-body .crm-confirm-overlay"
        self.assertIn(selector, self.desktop_css)
        start = self.desktop_css.index(selector)
        rule = self.desktop_css[start : self.desktop_css.index("}", start)]
        self.assertIn("position: fixed !important", rule)
        self.assertIn("height: 100dvh !important", rule)
        self.assertIn("pointer-events: auto !important", rule)

        card_selector = "html.desktop-like-pointer body.app-body .crm-confirm-card"
        start = self.desktop_css.index(card_selector)
        card_rule = self.desktop_css[start : self.desktop_css.index("}", start)]
        self.assertIn("max-height: calc(100dvh - 2rem) !important", card_rule)
        self.assertIn("overflow-y: auto !important", card_rule)

    def test_hidden_custom_confirm_overlay_cannot_be_forced_visible(self):
        selector = "html.desktop-like-pointer body.app-body .crm-confirm-overlay.d-none"
        self.assertIn(selector, self.desktop_css)
        start = self.desktop_css.index(selector)
        rule = self.desktop_css[start : self.desktop_css.index("}", start)]

        self.assertIn("display: none !important", rule)
        self.assertIn("pointer-events: none !important", rule)

    def test_sync_log_modal_buttons_keep_page_design_after_body_lift(self):
        rollback_selector = (
            "html.desktop-like-pointer body.app-body:has(.sync-logs-page) .sync-modal-btn-rollback"
        )
        delete_selector = (
            "html.desktop-like-pointer body.app-body:has(.sync-logs-page) .sync-modal-btn-delete"
        )
        for selector, color in ((rollback_selector, "#e7a025"), (delete_selector, "#e04b4b")):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.desktop_css)
                start = self.desktop_css.index(selector)
                rule = self.desktop_css[start : self.desktop_css.index("}", start)]
                self.assertIn("color: #ffffff !important", rule)
                self.assertIn(f"background: {color} !important", rule)
                self.assertIn(f"border-color: {color} !important", rule)

    def test_bootstrap_modals_are_lifted_out_of_scaled_page_shell_on_desktop_only(self):
        start = self.script.index("const isDesktopModalViewport")
        end = self.script.index("document.querySelectorAll('[data-digits-only=\"1\"]')", start)
        section = self.script[start:end]

        self.assertIn("ensureBootstrapModalInBody", section)
        self.assertIn("show.bs.modal", section)
        self.assertIn("document.body.appendChild(modal)", section)
        self.assertIn("mobile-viewport", section)
        self.assertIn("adaptive-mobile-viewport", section)
        self.assertIn("touch-app-device", section)

    def test_modal_fix_is_not_added_to_mobile_css(self):
        self.assertNotIn("ensureBootstrapModalInBody", self.mobile_css)
        self.assertNotIn("html.desktop-like-pointer body.app-body .modal.show", self.mobile_css)

    def test_changed_assets_have_matching_cache_busters(self):
        script_template = re.search(r"script\.js'\) }}\?v=([^\"]+)", self.base).group(1)
        script_worker = re.search(r"/static/script\.js\?v=([^']+)", self.worker).group(1)
        css_template = re.search(r"desktop-only\.css'\) }}\?v=([^\"]+)", self.base).group(1)
        css_worker = re.search(r"/static/desktop-only\.css\?v=([^']+)", self.worker).group(1)

        self.assertEqual(script_template, "v671-site-error-native-select-hidden")
        self.assertEqual(css_template, "v68-confirm-modal-actions")
        self.assertEqual(script_template, script_worker)
        self.assertEqual(css_template, css_worker)


if __name__ == "__main__":
    unittest.main()
