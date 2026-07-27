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


if __name__ == "__main__":
    unittest.main()
