import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_CSS = (ROOT / "app" / "static" / "desktop-only.css").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")


class ObjectsCardVisibilityTests(unittest.TestCase):
    def test_sensitive_project_requisites_are_not_rendered_on_object_cards(self):
        template = (ROOT / "app" / "templates" / "objects.html").read_text(encoding="utf-8")

        description_block = template.split('class="object-description{% if not has_object_details %} object-description-empty{% endif %}"', 1)[1].split("</div>", 1)[0]
        self.assertNotIn("ИНН/КПП", description_block)
        self.assertNotIn("ОГРН", description_block)
        self.assertNotIn("Юр. адрес", description_block)
        self.assertNotIn("Директор СЗ", description_block)
        self.assertNotIn("project.inn_kpp", description_block)
        self.assertNotIn("project.ogrn", description_block)
        self.assertNotIn("project.legal_address", description_block)
        self.assertNotIn("project.developer_director", description_block)

    def test_desktop_object_cards_stay_three_per_row_when_window_narrows(self):
        self.assertIn(
            "html.desktop-like-pointer body.app-body:has(.objects-page) .objects-grid {\n"
            "  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;\n"
            "  min-width: 0 !important;",
            DESKTOP_CSS,
        )
        self.assertIn(
            "html.desktop-like-pointer body.app-body:has(.objects-page) .objects-page {\n"
            "  overflow-x: visible !important;",
            DESKTOP_CSS,
        )
        self.assertNotIn(
            "@media (max-width: 1480px) {\n"
            "  html.desktop-like-pointer body.app-body:has(.objects-page) .objects-grid",
            DESKTOP_CSS,
        )
        self.assertNotIn(
            "@media (max-width: 980px) {\n"
            "  html.desktop-like-pointer body.app-body:has(.objects-page) .objects-grid",
            DESKTOP_CSS,
        )

    def test_object_card_stats_start_after_a_fixed_details_area(self):
        template = (ROOT / "app" / "templates" / "objects.html").read_text(encoding="utf-8")

        self.assertIn("has_object_details =", template)
        self.assertIn('class="object-description{% if not has_object_details %} object-description-empty{% endif %}"', template)
        self.assertNotIn("object-description-spacer\" aria-hidden=\"true\"", template)

        self.assertIn(
            "html.desktop-like-pointer body.app-body:has(.objects-page) .object-card {\n"
            "  display: grid !important;\n"
            "  grid-template-rows: auto auto auto minmax(6.65rem, auto) auto !important;",
            STYLE_CSS,
        )
        self.assertIn(
            "html.desktop-like-pointer body.app-body:has(.objects-page) .object-title {\n"
            "  min-height: 3.05rem !important;",
            STYLE_CSS,
        )
        self.assertIn(
            "html.desktop-like-pointer body.app-body:has(.objects-page) .object-address {\n"
            "  min-height: 3.05rem !important;",
            STYLE_CSS,
        )
        self.assertIn(
            "html.desktop-like-pointer body.app-body:has(.objects-page) .object-description {\n"
            "  min-height: 6.65rem !important;",
            STYLE_CSS,
        )
        self.assertIn(
            "html.desktop-like-pointer body.app-body:has(.objects-page) .object-meta-stats,\n"
            "html.desktop-like-pointer body.app-body:has(.objects-page) .object-meta-stats-no-commercial {\n"
            "  margin-top: 0 !important;",
            STYLE_CSS,
        )
        self.assertIn(
            "html:is(.mobile-viewport, .adaptive-mobile-viewport, .touch-app-device) body.app-body:has(.objects-page) .object-description-empty {\n"
            "    display: none !important;",
            STYLE_CSS,
        )


if __name__ == "__main__":
    unittest.main()
