import unittest
from datetime import date
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


if __name__ == "__main__":
    unittest.main()
