import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "app" / "templates" / "material_request_detail.html"
ROUTES_PATH = ROOT / "app" / "routes.py"
MOBILE_CSS_PATH = ROOT / "app" / "static" / "mobile-only.css"


class MaterialRequestDetailExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        cls.routes = ROUTES_PATH.read_text(encoding="utf-8")

    def test_detail_page_links_to_existing_request_export(self):
        self.assertIn("url_for('main.material_request_export', request_id=material_request.id)", self.template)
        self.assertIn("download-excel-btn material-request-detail-export-btn", self.template)
        self.assertIn("<span>Скачать Excel</span>", self.template)

    def test_export_button_is_permission_gated_and_desktop_only(self):
        button_block = re.search(
            r"\{% if can_export_material_request %\}(.*?)\{% endif %\}",
            self.template,
            re.DOTALL,
        )
        self.assertIsNotNone(button_block)
        self.assertIn("material-request-detail-export-btn", button_block.group(1))
        self.assertIn("d-none d-md-inline-flex", button_block.group(1))

    def test_detail_route_passes_export_permission_to_template(self):
        detail_route = re.search(
            r"def material_request_detail\(request_id: int\):(.*?)\n\n@bp\.route",
            self.routes,
            re.DOTALL,
        )
        self.assertIsNotNone(detail_route)
        self.assertIn("can_export_material_request=can_export(current_user)", detail_route.group(1))

    def test_mobile_styles_are_unchanged_for_export_button(self):
        mobile_css = MOBILE_CSS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("material-request-detail-export-btn", mobile_css)


if __name__ == "__main__":
    unittest.main()
