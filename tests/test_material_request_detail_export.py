import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "app" / "templates" / "material_request_detail.html"
ROUTES_PATH = ROOT / "app" / "routes.py"
MOBILE_CSS_PATH = ROOT / "app" / "static" / "mobile-only.css"
DESKTOP_CSS_PATH = ROOT / "app" / "static" / "desktop-only.css"


class MaterialRequestDetailExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = TEMPLATE_PATH.read_text(encoding="utf-8")
        cls.routes = ROUTES_PATH.read_text(encoding="utf-8")

    def test_detail_page_links_to_existing_request_export(self):
        self.assertIn("url_for('main.material_request_export', request_id=material_request.id)", self.template)
        self.assertIn("download-excel-btn material-request-detail-export-btn", self.template)
        self.assertIn('data-download-mode="native"', self.template)
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

    def test_detail_renderer_passes_export_permission_to_template(self):
        detail_renderer = re.search(
            r"def _render_material_request_detail\((.*?)\n\n\ndef ",
            self.routes,
            re.DOTALL,
        )
        self.assertIsNotNone(detail_renderer)
        self.assertIn("can_export_material_request=can_export(current_user)", detail_renderer.group(1))

    def test_mobile_styles_are_unchanged_for_export_button(self):
        mobile_css = MOBILE_CSS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("material-request-detail-export-btn", mobile_css)

    def test_native_download_mode_bypasses_blob_fetch_for_request_export(self):
        script = (ROOT / "app" / "static" / "script.js").read_text(encoding="utf-8")
        self.assertIn(
            "link.dataset.downloadMode !== 'native'",
            script,
            "The request export must use the browser's native download path.",
        )

    def test_desktop_edit_save_replaces_export_in_page_header(self):
        desktop_css = DESKTOP_CSS_PATH.read_text(encoding="utf-8")

        self.assertIn('id="material-request-edit-form"', self.template)
        self.assertIn('form="material-request-edit-form"', self.template)
        self.assertIn("material-request-edit-save-top", self.template)
        self.assertIn("material-request-edit-save-bottom", self.template)
        self.assertIn(
            "body.app-body:has(.js-material-request-edit-form:not(.d-none))",
            desktop_css,
        )
        self.assertIn(".material-request-detail-export-btn", desktop_css)
        self.assertIn(".material-request-edit-save-bottom", desktop_css)

    def test_mobile_keeps_the_bottom_edit_save(self):
        mobile_css = MOBILE_CSS_PATH.read_text(encoding="utf-8")

        self.assertNotIn("material-request-edit-save-top", mobile_css)
        self.assertNotIn("material-request-edit-save-bottom", mobile_css)


if __name__ == "__main__":
    unittest.main()
