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

    def test_confirm_modal_script_cache_buster_is_synchronized(self):
        template = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
        worker = (ROOT / "app" / "static" / "service-worker.js").read_text(encoding="utf-8")

        self.assertIn("script.js') }}?v=v668-crm-confirm-modal", template)
        self.assertIn("/static/script.js?v=v668-crm-confirm-modal", worker)
        self.assertIn("peredacha-static-v149-material-edit-save-top", worker)


if __name__ == "__main__":
    unittest.main()
