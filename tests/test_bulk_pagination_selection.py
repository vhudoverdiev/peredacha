import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "app" / "static" / "script.js"
MATERIALS_TEMPLATE_PATH = ROOT / "app" / "templates" / "materials.html"


class BulkPaginationSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")
        cls.materials_template = MATERIALS_TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_ajax_morph_keeps_runtime_binding_markers(self):
        self.assertIn(
            "attribute.name.startsWith('data-') && attribute.name.endsWith('-bound')",
            self.script,
        )
        self.assertIn("!nextElement.hasAttribute(attribute.name) && !isRuntimeBindingMarker", self.script)

    def test_material_bulk_forms_persist_selection_across_pages(self):
        expected_links = (
            ('#material-balance-delete-form', 'material_keys'),
            ('#material-requests-delete-form', 'request_ids'),
            ('#material-writeoffs-delete-form', 'writeoff_ids'),
        )
        for form_selector, field_name in expected_links:
            with self.subTest(form_selector=form_selector):
                self.assertIn(f'data-bulk-persist-form="{form_selector}"', self.materials_template)
                self.assertIn(f'data-bulk-persist-name="{field_name}"', self.materials_template)


if __name__ == "__main__":
    unittest.main()
