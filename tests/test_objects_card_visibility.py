import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_CSS = (ROOT / "app" / "static" / "desktop-only.css").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")


class ObjectsCardVisibilityTests(unittest.TestCase):
    def test_sensitive_project_requisites_are_not_rendered_on_object_cards(self):
        template = (ROOT / "app" / "templates" / "objects.html").read_text(encoding="utf-8")

        details = template.split("{% set object_details = [", 1)[1].split("] %}", 1)[0]
        for field in ("technical_customer", "developer_name", "developer_representative", "developer_representative_phone"):
            self.assertIn(f"project.{field}", details)
        for field in ("inn_kpp", "ogrn", "legal_address", "developer_director"):
            self.assertNotIn(f"project.{field}", details)

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

        self.assertIn('class="object-description"', template)
        self.assertIn("value or 'Не указано'", template)
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
    def test_mobile_objects_use_flat_canvas(self):
        self.assertIn(
            "body.app-body.app-body.app-body:has(.objects-page) {\n"
            "    --crm-mobile-unified-surface: #f6f8fb !important;\n"
            "    background: var(--crm-mobile-unified-surface) !important;",
            STYLE_CSS,
        )


if __name__ == "__main__":
    unittest.main()
