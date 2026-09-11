import unittest
from pathlib import Path
from types import SimpleNamespace

from app.routes import _apartment_group_contact_values


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app" / "templates" / "apartments.html").read_text(encoding="utf-8")


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

    def test_card_renders_owner_and_phone_without_mobile_guard(self):
        self.assertIn("Собственник: {{ row.owner_names|join(', ') if row.owner_names else '—' }}", TEMPLATE)
        self.assertIn("Телефон: {{ row.phones|join(', ') if row.phones else '—' }}", TEMPLATE)
        contact_start = TEMPLATE.index('class="apartment-owner-line"')
        contact_end = TEMPLATE.index("{% if row.mode", contact_start)
        self.assertNotIn("is_mobile_phone_request", TEMPLATE[contact_start:contact_end])


if __name__ == "__main__":
    unittest.main()
