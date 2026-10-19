import unittest
from pathlib import Path
from types import SimpleNamespace

from app.routes import _apartment_group_contact_values


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app" / "templates" / "apartments.html").read_text(encoding="utf-8")
STYLE = (ROOT / "app" / "static" / "style.css").read_text(encoding="utf-8")
DESKTOP_STYLE = (ROOT / "app" / "static" / "desktop-only.css").read_text(encoding="utf-8")


class ApartmentCardContactsTests(unittest.TestCase):
    def test_group_contacts_are_trimmed_and_deduplicated(self):
        apartments = [
            SimpleNamespace(owner_name="Иванов Иван\nПетров Пётр", phone="+7 900 000-00-01"),
            SimpleNamespace(owner_name="иванов иван\nСидорова Анна", phone="+7 900 000-00-01\n+7 900 000-00-02"),
        ]

        self.assertEqual(
            _apartment_group_contact_values(apartments, "owner_name"),
            ["Иванов Иван", "Петров Пётр", "Сидорова Анна"],
        )
        self.assertEqual(
            _apartment_group_contact_values(apartments, "phone"),
            ["+7 900 000-00-01", "+7 900 000-00-02"],
        )

    def test_unsold_marker_is_not_shown_as_owner_name(self):
        apartments = [
            SimpleNamespace(owner_name="не продано", phone=""),
            SimpleNamespace(owner_name="Не продана", phone=""),
        ]

        self.assertEqual(_apartment_group_contact_values(apartments, "owner_name"), [])

    def test_card_renders_owner_and_phone_without_mobile_guard(self):
        self.assertIn("Собственник: {{ row.owner_names|join(', ') if row.owner_names else '—' }}", TEMPLATE)
        self.assertIn("Телефон: {{ row.phones|join(', ') if row.phones else '—' }}", TEMPLATE)
        contact_start = TEMPLATE.index('class="apartment-owner-line"')
        contact_end = TEMPLATE.index("{% if row.mode", contact_start)
        self.assertNotIn("is_mobile_phone_request", TEMPLATE[contact_start:contact_end])

    def test_unsold_cards_have_translucent_yellow_state(self):
        self.assertIn("apartment-card-unsold", TEMPLATE)
        self.assertIn(".apartment-card.apartment-card-unsold", STYLE)
        self.assertIn("rgba(255, 214, 102, 0.18)", STYLE)
        self.assertIn("body.app-body:has(.apartments-page) .apartments-grid .apartment-card.apartment-card-unsold", STYLE)
        self.assertIn("rgba(255, 214, 102, 0.12) !important", STYLE)
        self.assertIn(".apartment-card.apartment-card-unsold:active", STYLE)
        self.assertIn(".apartment-card.apartment-card-unsold .apartment-card-link:active", STYLE)
        self.assertIn(".apartment-card.apartment-card-unsold .apartment-card-info", STYLE)
        self.assertIn(".apartment-card.apartment-card-unsold .apartment-card-link:active .apartment-card-info", STYLE)
        self.assertIn(".apartment-card.apartment-card-unsold .apartment-card-link:active .apartment-card-info span", STYLE)
        self.assertIn("body.app-body .apartments-page .apartments-grid .apartment-card.apartment-card-unsold", STYLE)
        self.assertIn(".apartment-card.apartment-card-unsold .apartment-card-link:active .apartment-card-info i", STYLE)
        self.assertIn("html.desktop-like-pointer body.app-body .apartments-page .apartments-grid .apartment-card.apartment-card-unsold", DESKTOP_STYLE)
        self.assertIn(".apartment-card.apartment-card-unsold .apartment-card-link:active .apartment-card-info i", DESKTOP_STYLE)

    def test_unsold_cards_do_not_render_inspection_badge(self):
        self.assertIn("row.inspection_status and row.mode != 'не продана'", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
