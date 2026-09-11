from datetime import datetime
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from config import Config
from app import create_app, db
from app.models import (
    Apartment,
    Contractor,
    Project,
    STATUS_CONCESSION,
    STATUS_CONTRACTOR,
    STATUS_DONE,
    STATUS_GUARANTEE,
    STATUS_NOT_STARTED,
    Task,
    WorkPoint,
)
from app.services.excel_export import (
    _append_status_suffix,
    _combined_completed_by,
    _combined_task_lines,
    _excel_commercial_label,
    _excel_premise_finish_label,
    _excel_premise_label,
    _prefix_dash_for_struck_cell,
    _safe_filename_part,
    style_header_row,
    style_report_header_row,
    _task_export_value,
    _task_remark_text,
    build_export_path,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "excel-export-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ExcelExportPureContractsTests(unittest.TestCase):
    def test_commercial_labels_normalize_common_user_entered_forms(self):
        self.assertEqual(_excel_commercial_label("к15/к2"), "коммерция 15/корпус 2")
        self.assertEqual(_excel_commercial_label("15", "2"), "коммерция 15/корпус 2")
        self.assertEqual(_excel_commercial_label("коммерция 17"), "коммерция 17")
        self.assertEqual(_excel_commercial_label("storage", "3"), "коммерция storage/корпус 3")

    def test_status_suffix_replaces_stale_terminal_suffixes_instead_of_stacking_them(self):
        self.assertEqual(_append_status_suffix("Fix window (лб)", "(подрядчик)"), "Fix window (подрядчик)")
        self.assertEqual(_append_status_suffix("Fix window (лб) (чистовики)", "(подрядчик)"), "Fix window (подрядчик)")
        self.assertEqual(_append_status_suffix("", "(лб)"), "(лб)")

    def test_strike_prefix_is_idempotent_for_empty_and_existing_marked_values(self):
        self.assertEqual(_prefix_dash_for_struck_cell(None), "-")
        self.assertEqual(_prefix_dash_for_struck_cell("Fix"), "- Fix")
        self.assertEqual(_prefix_dash_for_struck_cell("- Fix"), "- Fix")

    def test_safe_filename_part_strips_windows_forbidden_characters_and_has_fallback(self):
        self.assertEqual(_safe_filename_part('A/B:C*D?"E<>|'), "A B C D E")
        self.assertEqual(_safe_filename_part("   "), "object")

    def test_header_style_helpers_keep_identical_layout_and_fill(self):
        workbook = Workbook()
        regular = workbook.active
        regular.append(["A", "B"])
        report = workbook.create_sheet("report")
        report.append(["A", "B"])

        style_header_row(regular)
        style_report_header_row(report)

        for sheet in (regular, report):
            self.assertEqual(sheet.row_dimensions[1].height, 32)
            for cell in sheet[1]:
                self.assertTrue(cell.font.bold)
                self.assertEqual(cell.font.color.rgb, "00111827")
                self.assertEqual(cell.alignment.horizontal, "center")
                self.assertEqual(cell.alignment.vertical, "center")
                self.assertTrue(cell.alignment.wrap_text)
                self.assertEqual(cell.border.left.style, "thin")
                self.assertEqual(cell.fill.fgColor.rgb, "FFE2F0D9")


class ExcelExportDatabaseContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.project = Project(name="Excel export QA")
        self.apartment = Apartment(project=self.project, apartment_number="15", finishing_type="White box")
        self.commercial = Apartment(project=self.project, apartment_number="17", building="2", premise_type="commercial")
        self.point = WorkPoint(point_number="10", short_name="Window", original_column_name="Window")
        db.session.add_all([self.project, self.apartment, self.commercial, self.point])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _task(self, uid: str, *, status: str = STATUS_NOT_STARTED, description: str = "Window: fix seal") -> Task:
        task = Task(
            source_uid=uid,
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            status=status,
            description=description,
        )
        db.session.add(task)
        db.session.flush()
        return task

    def test_premise_labels_include_finish_and_support_missing_apartment(self):
        self.assertEqual(_excel_premise_label(None), "")
        self.assertIn("15", _excel_premise_label(self.apartment))
        self.assertEqual(_excel_premise_finish_label(self.apartment).splitlines()[-1], "White box")
        self.assertEqual(_excel_premise_label(self.commercial).lower(), "коммерция 17/корпус 2")

    def test_task_remark_text_strips_redundant_point_prefixes_but_keeps_meaningful_text(self):
        prefixed = self._task("remark-prefixed", description="Window: replace handle")
        numbered = self._task("remark-numbered", description="пункт 10. replace seal")
        plain = self._task("remark-plain", description="replace glass")

        self.assertEqual(_task_remark_text(prefixed), "replace handle")
        self.assertEqual(_task_remark_text(numbered), "replace seal")
        self.assertEqual(_task_remark_text(plain), "replace glass")

    def test_combined_task_lines_number_multiple_tasks_and_optionally_include_point(self):
        first = self._task("combined-first", status=STATUS_DONE, description="Window: replace handle")
        second = self._task("combined-second", status=STATUS_CONTRACTOR, description="Window: replace seal")

        lines = _combined_task_lines([first, second], include_status=True, include_point=True)

        self.assertIn("1. Window: replace handle", lines)
        self.assertIn("2. Window: replace seal", lines)
        self.assertIn(first.status_label(), lines)
        self.assertIn(second.status_label(), lines)

    def test_completed_by_labels_deduplicate_terminal_executors_and_expand_guarantee_contractor(self):
        done = self._task("done", status=STATUS_DONE)
        contractor = self._task("contractor", status=STATUS_CONTRACTOR)
        concession = self._task("concession", status=STATUS_CONCESSION)
        guarantee_contractor = Contractor(project=self.project, name="Warranty LLC")
        db.session.add(guarantee_contractor)
        db.session.flush()
        self.apartment.contractors.append(guarantee_contractor)
        self.point.contractors.append(guarantee_contractor)
        guarantee = self._task("guarantee", status=STATUS_GUARANTEE)
        db.session.commit()

        labels = _combined_completed_by([done, done, contractor, concession, guarantee])

        self.assertEqual(labels.splitlines(), ["Личная бригада", "Подрядчик", "Отступные", "Warranty LLC"])

    def test_task_export_value_prefers_crm_text_updates_status_suffix_and_marks_completed_source_cell(self):
        done = self._task("export-done", status=STATUS_DONE, description="Updated CRM text (подрядчик)")
        open_task = self._task("export-open", status=STATUS_NOT_STARTED, description="")
        open_task.source_cell_value = "Original source"

        self.assertEqual(_task_export_value(done, "Old source"), "- Updated CRM text (лб)")
        self.assertEqual(_task_export_value(open_task, "Fallback"), "- Original source")

    def test_build_export_path_sanitizes_prefix_cache_key_and_uses_configured_export_folder(self):
        fixed_now = datetime(2026, 7, 29, 12, 0)

        with patch("app.services.excel_export.datetime") as datetime_mock:
            datetime_mock.now.return_value = fixed_now
            path = build_export_path("bad/name", cache_key='object:"42"')

        self.assertTrue(path.parent.exists())
        self.assertTrue(str(path).replace("\\", "/").endswith("/bad name_2026-07-29_object 42.xlsx"))


if __name__ == "__main__":
    unittest.main()
