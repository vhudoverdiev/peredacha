import unittest
from pathlib import Path

from app.routes import (
    GLASS_ITEM_TYPES,
    GLASS_STATUS_ORDERED,
    GLASS_STATUS_REPLACED,
    _glass_item_noun,
    _glass_status_verb,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app" / "templates" / "glass_measurements.html").read_text(encoding="utf-8")


class GlassDoorTypeTests(unittest.TestCase):
    def test_door_is_an_allowed_type_rendered_by_every_type_select(self):
        self.assertIn("Дверь", GLASS_ITEM_TYPES)
        self.assertGreaterEqual(TEMPLATE.count("{% for item_type in glass_item_types %}"), 3)

    def test_door_has_correct_order_and_replacement_labels(self):
        singular, gender = _glass_item_noun("Дверь", 1)
        plural, plural_gender = _glass_item_noun("Дверь", 2)

        self.assertEqual((singular, gender), ("дверь", "f"))
        self.assertEqual((plural, plural_gender), ("двери", "f"))
        self.assertEqual(_glass_status_verb(GLASS_STATUS_ORDERED, gender, 1), "Заказана")
        self.assertEqual(_glass_status_verb(GLASS_STATUS_REPLACED, gender, 1), "Поменяна")
        self.assertEqual(_glass_status_verb(GLASS_STATUS_ORDERED, plural_gender, 2), "Заказаны")


if __name__ == "__main__":
    unittest.main()
