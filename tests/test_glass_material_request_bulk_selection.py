import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "app" / "templates" / "glass_measurements.html"
SCRIPT_PATH = ROOT / "app" / "static" / "script.js"
ROUTES_PATH = ROOT / "app" / "routes.py"


class GlassMaterialRequestBulkSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")
        cls.routes = ROUTES_PATH.read_text(encoding="utf-8")

    def test_ordered_table_persists_measurement_ids_into_request_form(self):
        ordered_scope = re.search(
            r'<div class="card table-shell glass-table-shell js-bulk-selectable"[^>]+>',
            self.template,
        )
        self.assertIsNotNone(ordered_scope)
        self.assertIn('data-bulk-persist-form="#glass-bulk-request-form"', ordered_scope.group(0))
        self.assertIn('data-bulk-persist-name="measurement_ids"', ordered_scope.group(0))

    def test_persisted_inputs_use_the_scope_specific_field_name(self):
        function = re.search(
            r"const syncBulkPersistedInputs = \(scope\) => \{(.*?)\n  \};",
            self.script,
            re.DOTALL,
        )
        self.assertIsNotNone(function)
        self.assertIn("const inputName = scope.dataset.bulkPersistName || 'task_ids';", function.group(1))
        self.assertIn("input.name = inputName;", function.group(1))
        self.assertIn("input.value = selectedId;", function.group(1))

    def test_server_accepts_all_posted_measurements_without_a_count_slice(self):
        route = re.search(
            r"def glass_create_material_request\(\):(.*?)\n\n@bp\.route",
            self.routes,
            re.DOTALL,
        )
        self.assertIsNotNone(route)
        self.assertIn('request.form.getlist("measurement_ids")', route.group(1))
        self.assertNotRegex(route.group(1), r"getlist\(\"measurement_ids\"\)\s*\[:")


if __name__ == "__main__":
    unittest.main()
