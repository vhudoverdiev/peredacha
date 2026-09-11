import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.routes import (
    GLASS_ORDERED_REQUEST_NONE,
    GLASS_ORDERED_SORT_APARTMENT_ASC,
    GLASS_ORDERED_SORT_DATE_DESC,
    _filter_sort_ordered_glass_rows,
    _ordered_glass_request_options,
)


def make_row(apartment_number, ordered_at, request_id=None, request_title=None, task_id=1):
    apartment = SimpleNamespace(
        premise_type="apartment",
        apartment_number=str(apartment_number),
        construction_number=None,
        building="",
    )
    task = SimpleNamespace(
        id=task_id,
        apartment=apartment,
        work_point=SimpleNamespace(point_number="16"),
    )
    material_request = None
    if request_id is not None:
        material_request = SimpleNamespace(
            id=request_id,
            title=request_title,
            comment=None,
            request_date=ordered_at,
        )
    request_item = SimpleNamespace(request=material_request) if material_request else None
    measurement = SimpleNamespace(
        ordered_at=ordered_at,
        material_request_item=request_item,
    )
    return {"task": task, "measurement": measurement}


class GlassOrderedFiltersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (
            Path(__file__).resolve().parents[1] / "app" / "templates" / "glass_measurements.html"
        ).read_text(encoding="utf-8")

    def setUp(self):
        self.rows = [
            make_row(10, date(2026, 7, 18), 8, "Заявка из замеров №8", 10),
            make_row(2, date(2026, 7, 20), None, None, 2),
            make_row(1, date(2026, 7, 20), 9, "Заявка из замеров №9", 1),
            make_row(3, None, None, None, 3),
        ]

    def test_request_filter_includes_explicit_not_created_option(self):
        filtered = _filter_sort_ordered_glass_rows(
            self.rows,
            request_filter=GLASS_ORDERED_REQUEST_NONE,
            sort_order=GLASS_ORDERED_SORT_APARTMENT_ASC,
        )

        self.assertEqual([row["task"].apartment.apartment_number for row in filtered], ["2", "3"])

    def test_request_filter_selects_a_specific_request(self):
        filtered = _filter_sort_ordered_glass_rows(
            self.rows,
            request_filter="8",
            sort_order=GLASS_ORDERED_SORT_DATE_DESC,
        )

        self.assertEqual([row["task"].apartment.apartment_number for row in filtered], ["10"])

    def test_date_sort_is_newest_first_then_apartment_ascending(self):
        sorted_rows = _filter_sort_ordered_glass_rows(
            self.rows,
            sort_order=GLASS_ORDERED_SORT_DATE_DESC,
        )

        self.assertEqual(
            [row["task"].apartment.apartment_number for row in sorted_rows],
            ["1", "2", "10", "3"],
        )

    def test_apartment_sort_uses_natural_numeric_order(self):
        sorted_rows = _filter_sort_ordered_glass_rows(
            self.rows,
            sort_order=GLASS_ORDERED_SORT_APARTMENT_ASC,
        )

        self.assertEqual(
            [row["task"].apartment.apartment_number for row in sorted_rows],
            ["1", "2", "3", "10"],
        )

    def test_request_options_are_unique_and_newest_first(self):
        duplicate_request = make_row(11, date(2026, 7, 18), 8, "Заявка из замеров №8", 11)
        options = _ordered_glass_request_options([*self.rows, duplicate_request])

        self.assertEqual(
            options,
            [
                {"id": 9, "label": "Заявка из замеров №9"},
                {"id": 8, "label": "Заявка из замеров №8"},
            ],
        )

    def test_empty_request_filter_has_a_filter_specific_message(self):
        self.assertIn(
            "{% elif ordered_status or ordered_request %}По выбранным фильтрам ничего не найдено",
            self.template,
        )

    def test_new_filters_use_the_existing_mobile_native_selects(self):
        self.assertIn(
            '<select class="form-select mobile-native-select" name="ordered_request">',
            self.template,
        )
        self.assertIn(
            '<select class="form-select mobile-native-select" name="ordered_sort">',
            self.template,
        )
        self.assertIn(
            '<option value="none" {% if ordered_request == \'none\' %}selected{% endif %}>Не создана</option>',
            self.template,
        )
    def test_sort_labels_are_short_in_all_layouts(self):
        self.assertIn(
            '<option value="date_desc" {% if ordered_sort == \'date_desc\' %}selected{% endif %}>По дате</option>',
            self.template,
        )
        self.assertIn(
            '<option value="apartment_asc" {% if ordered_sort == \'apartment_asc\' %}selected{% endif %}>По помещению</option>',
            self.template,
        )
        self.assertNotIn("По дате — сначала новые", self.template)
        self.assertNotIn("По квартире — 1, 2, 3…", self.template)


if __name__ == "__main__":
    unittest.main()
