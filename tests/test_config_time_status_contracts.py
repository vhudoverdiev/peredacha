from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import config
from app.models import STATUS_DONE, STATUS_NOT_STARTED, STATUS_PROBLEM
from app.routes import format_ru_date, format_ru_day_month, format_ru_weekday
from app.services.status_rules import is_problem_details_required
from app.time_utils import MOSCOW_TIMEZONE, to_moscow_datetime, utc_now


class ConfigTimeStatusContractsTests(unittest.TestCase):
    def test_database_url_normalization_resolves_relative_sqlite_against_project_root(self):
        normalized = config._normalize_database_url("sqlite:///instance/test.sqlite")

        self.assertTrue(normalized.startswith("sqlite:///"))
        self.assertIn("Peredacha/instance/test.sqlite", normalized.replace("\\", "/"))

    def test_database_url_normalization_preserves_absolute_sqlite_and_non_sqlite_urls(self):
        self.assertEqual(config._normalize_database_url("sqlite:///C:/data/crm.sqlite"), "sqlite:///C:/data/crm.sqlite")
        self.assertEqual(config._normalize_database_url("postgresql://user:pass@example/db"), "postgresql://user:pass@example/db")

    def test_filesystem_path_normalization_uses_base_dir_for_relative_values(self):
        normalized = config._normalize_fs_path("uploads/custom", "fallback")

        self.assertTrue(normalized.replace("\\", "/").endswith("/Peredacha/uploads/custom"))

    def test_bool_and_csv_env_parsing_accept_common_forms_and_normalize_case(self):
        with patch.dict("os.environ", {"FLAG": "YeS", "NAMES": " Admin, manager ,, ADMIN "}, clear=False):
            self.assertTrue(config._bool_env("FLAG"))
            self.assertEqual(config._csv_env("NAMES"), {"admin", "manager"})

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(config._bool_env("MISSING"))
            self.assertTrue(config._bool_env("MISSING", default=True))

    def test_moscow_datetime_treats_naive_database_values_as_utc(self):
        naive = datetime(2026, 7, 29, 10, 30)
        aware = datetime(2026, 7, 29, 10, 30, tzinfo=timezone.utc)

        self.assertEqual(to_moscow_datetime(naive).tzinfo, MOSCOW_TIMEZONE)
        self.assertEqual(to_moscow_datetime(naive).hour, 13)
        self.assertEqual(to_moscow_datetime(aware).hour, 13)

    def test_utc_now_keeps_legacy_naive_utc_contract(self):
        value = utc_now()

        self.assertIsNone(value.tzinfo)

    def test_route_date_formatters_treat_datetime_as_its_calendar_date(self):
        value = datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc)

        self.assertEqual(format_ru_date(value), format_ru_date(value.date()))
        self.assertEqual(format_ru_day_month(value), format_ru_day_month(value.date()))
        self.assertEqual(format_ru_weekday(value), format_ru_weekday(value.date()))

    def test_problem_details_required_only_for_problem_without_meaningful_comment(self):
        self.assertTrue(is_problem_details_required(STATUS_PROBLEM, None))
        self.assertTrue(is_problem_details_required(STATUS_PROBLEM, "   "))
        self.assertFalse(is_problem_details_required(STATUS_PROBLEM, "Broken lock"))
        self.assertFalse(is_problem_details_required(STATUS_DONE, None))
        self.assertFalse(is_problem_details_required(STATUS_NOT_STARTED, ""))


if __name__ == "__main__":
    unittest.main()
