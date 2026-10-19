from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import config
from app import create_app
from app.models import STATUS_DONE, STATUS_NOT_STARTED, STATUS_PROBLEM
from app.routes import format_ru_date, format_ru_day_month, format_ru_weekday
from app.services.status_rules import is_problem_details_required
from app.time_utils import MOSCOW_TIMEZONE, to_moscow_datetime, utc_now


class ConfigTimeStatusContractsTests(unittest.TestCase):
    def test_database_url_normalization_requires_explicit_database_url(self):
        self.assertEqual(config._normalize_database_url(None), "")
        self.assertEqual(config._normalize_database_url("   "), "")

    def test_database_url_normalization_keeps_explicit_sqlite_url_for_test_configs(self):
        self.assertEqual(
            config._normalize_database_url("sqlite:///instance/test.sqlite"),
            "sqlite:///instance/test.sqlite",
        )

    def test_non_testing_app_rejects_sqlite_database_url(self):
        class SQLiteRuntimeConfig(config.Config):
            TESTING = False
            SECRET_KEY = "strong-test-secret"
            SQLALCHEMY_DATABASE_URI = "sqlite://"

        with self.assertRaisesRegex(RuntimeError, "SQLite DATABASE_URL is not supported"):
            create_app(SQLiteRuntimeConfig)

    def test_non_testing_app_requires_mariadb_database_url(self):
        class EmptyRuntimeConfig(config.Config):
            TESTING = False
            SECRET_KEY = "strong-test-secret"
            SQLALCHEMY_DATABASE_URI = ""

        class PostgresRuntimeConfig(config.Config):
            TESTING = False
            SECRET_KEY = "strong-test-secret"
            SQLALCHEMY_DATABASE_URI = "postgresql://user:pass@example/db"

        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL must be set"):
            create_app(EmptyRuntimeConfig)
        with self.assertRaisesRegex(RuntimeError, "Only MariaDB DATABASE_URL"):
            create_app(PostgresRuntimeConfig)

    def test_database_url_normalization_preserves_mariadb_url(self):
        url = "mysql+pymysql://user:pass@127.0.0.1:3306/peredacha?charset=utf8mb4"

        self.assertEqual(config._normalize_database_url(url), url)

    def test_filesystem_path_normalization_uses_base_dir_for_relative_values(self):
        normalized = config._normalize_fs_path("uploads/custom", "fallback")

        self.assertTrue(normalized.replace("\\", "/").endswith("/uploads/custom"))

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
