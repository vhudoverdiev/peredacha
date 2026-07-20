import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DETAIL_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "material_request_detail.html"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
MOBILE_CSS = PROJECT_ROOT / "app" / "static" / "mobile-only.css"


class MaterialRequestDeleteHoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = DETAIL_TEMPLATE.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")

    def test_detail_delete_button_has_scoped_class(self):
        self.assertIn(
            'btn btn-outline-danger material-request-detail-delete-btn',
            self.template,
        )

    def test_desktop_interaction_states_force_white_text(self):
        selector = (
            "html.desktop-like-pointer body.app-body:has(.materials-page-head)\n"
            "  .material-request-detail-delete-btn:is(:hover, :focus, :focus-visible, :active)"
        )
        selector_start = self.desktop_css.index(selector)
        rule_end = self.desktop_css.index("}", selector_start)
        rule = self.desktop_css[selector_start:rule_end]

        self.assertIn("color: #ffffff !important", rule)
        self.assertIn("-webkit-text-fill-color: #ffffff !important", rule)

    def test_mobile_styles_do_not_override_detail_delete_button(self):
        self.assertNotIn("material-request-detail-delete-btn", self.mobile_css)


if __name__ == "__main__":
    unittest.main()
