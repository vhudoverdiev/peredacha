import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app" / "templates" / "apartment_detail.html").read_text(encoding="utf-8")


class ApartmentDetailContactsTests(unittest.TestCase):
    def test_detail_shows_owner_and_phone_for_desktop_and_mobile(self):
        self.assertIn("ФИО собственника", TEMPLATE)
        self.assertIn("Номер телефона", TEMPLATE)
        self.assertIn("row.owner_names|join(', ') if row.owner_names else '—'", TEMPLATE)
        self.assertIn("row.phones|join(', ') if row.phones else '—'", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
