from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GlassDeleteConfirmModalTest(unittest.TestCase):
    def test_glass_order_delete_uses_crm_confirm_modal_instead_of_native_confirm(self):
        script = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")

        self.assertNotIn("window.confirm(", script)
        self.assertIn("window.crmShowActionConfirm = showCrmActionConfirm;", script)
        self.assertIn("await window.crmShowActionConfirm(confirmMessage)", script)
        self.assertIn("const confirmMessage = normalizeConfirmText(", script)
        self.assertIn("modal.classList.add('d-none')", script)

    def test_desktop_hidden_state_wins_over_modal_flex_layout(self):
        desktop_css = (ROOT / "app" / "static" / "desktop-only.css").read_text(encoding="utf-8")

        self.assertIn(".crm-confirm-overlay.d-none", desktop_css)
        self.assertIn("display: none !important", desktop_css)

    def test_confirm_modal_script_cache_buster_is_synchronized(self):
        template = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        worker = (ROOT / "app" / "static" / "service-worker.js").read_text(encoding="utf-8")

        self.assertIn("script.js') }}?v=v669-material-edit-actions-top", template)
        self.assertIn("/static/script.js?v=v669-material-edit-actions-top", worker)
        self.assertIn("peredacha-static-v151-confirm-modal-actions", worker)


if __name__ == "__main__":
    unittest.main()
