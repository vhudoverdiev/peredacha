import unittest

from app.services.mapping_service import DEFAULT_POINT_MAPPING, MAIN_POINT_NUMBERS
from app.services.task_service import MAIN_WORK_POINT_NUMBERS
from app.routes import _contractor_point_options
from app.work_points import CONTRACTOR_POINT_LABELS, WORK_POINT_LABELS


class WorkPointLabelsContractsTests(unittest.TestCase):
    def test_contractor_points_cover_first_twenty_six_numbers(self):
        self.assertEqual(set(WORK_POINT_LABELS), {str(number) for number in range(1, 27)} - {"16"})
        self.assertEqual(CONTRACTOR_POINT_LABELS, WORK_POINT_LABELS)
        self.assertEqual([item["number"] for item in _contractor_point_options()], [str(number) for number in range(10, 27) if number != 16])

    def test_table_point_names_match_source_sheet_headers(self):
        self.assertNotIn("16", WORK_POINT_LABELS)
        self.assertEqual(WORK_POINT_LABELS["17"], "Работы по монтажу ПВХ блоков")
        self.assertEqual(WORK_POINT_LABELS["19"], "Ростелеком")
        self.assertEqual(WORK_POINT_LABELS["20"], "Работы по монтажу холодного витражного остекления балконов")
        self.assertEqual(WORK_POINT_LABELS["21"], "Работы по монтажу системы отопления")
        self.assertEqual(WORK_POINT_LABELS["22"], "Работы по монтажу канализации, в/с")
        self.assertEqual(WORK_POINT_LABELS["23"], "Работы по монтажу входных дверей")
        self.assertEqual(WORK_POINT_LABELS["24"], "Электрика")
        self.assertEqual(WORK_POINT_LABELS["25"], "Прочее")
        self.assertEqual(WORK_POINT_LABELS["26"], "Отступное (ТМЦ)")

    def test_visible_work_points_include_twenty_five(self):
        self.assertIn("25", MAIN_WORK_POINT_NUMBERS)
        self.assertEqual(MAIN_WORK_POINT_NUMBERS, MAIN_POINT_NUMBERS)

    def test_default_category_mapping_uses_shifted_table_numbers(self):
        self.assertNotIn("16", DEFAULT_POINT_MAPPING["Разнорабочие"])
        self.assertNotIn("16", DEFAULT_POINT_MAPPING["Витражники"])
        self.assertIn("17", DEFAULT_POINT_MAPPING["Витражники"])
        self.assertIn("20", DEFAULT_POINT_MAPPING["Витражники"])


if __name__ == "__main__":
    unittest.main()
