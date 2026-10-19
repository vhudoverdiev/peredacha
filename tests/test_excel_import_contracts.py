from datetime import datetime, timedelta
from io import BytesIO
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from openpyxl.styles import Color, Font, PatternFill

from config import Config
from app import create_app, db
from app.models import Apartment, Project, SyncLog, Task, WorkPoint
from app.services.task_service import dashboard_stats, sync_rows
from app.services.excel_import import (
    inspect_remarks_workbook,
    mark_missing_tasks,
    mark_stale_running_sync_logs,
    preview_excel,
    save_upload,
    workbook_sheets_to_rows_with_strikes,
    worksheet_to_rows,
    worksheet_to_rows_with_strikes,
)
from werkzeug.datastructures import FileStorage


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "excel-import-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ExcelImportContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _workbook_path(self, name="excel-import-contract.xlsx"):
        return self.app.config["UPLOAD_FOLDER"] / name if hasattr(self.app.config["UPLOAD_FOLDER"], "__truediv__") else None

    def _save_workbook(self, filename: str, workbook: Workbook):
        from pathlib import Path

        path = Path(self.app.config["UPLOAD_FOLDER"]) / filename
        workbook.save(path)
        return path

    def test_mark_stale_running_sync_logs_only_marks_expired_logs_for_selected_project(self):
        project = Project(name="Stale sync project")
        other_project = Project(name="Other project")
        now = datetime(2026, 7, 29, 12, 0)
        stale = SyncLog(project=project, source_type="excel", status="running", started_at=now - timedelta(minutes=6))
        fresh = SyncLog(project=project, source_type="excel", status="running", started_at=now - timedelta(minutes=4))
        other = SyncLog(project=other_project, source_type="excel", status="running", started_at=now - timedelta(minutes=10))
        db.session.add_all([project, other_project, stale, fresh, other])
        db.session.commit()

        changed = mark_stale_running_sync_logs(project.id, now=now)

        self.assertEqual(changed, 1)
        self.assertEqual(stale.status, "error")
        self.assertEqual(stale.finished_at, now)
        self.assertIn("не завершилась", stale.error_message)
        self.assertEqual(fresh.status, "running")
        self.assertEqual(other.status, "running")

    def test_mark_missing_tasks_flags_visible_active_tasks_and_ignores_archived_hidden_and_seen(self):
        project = Project(name="Missing tasks project")
        apartment = Apartment(project=project, apartment_number="1")
        visible_point = WorkPoint(point_number="10")
        hidden_point = WorkPoint(point_number="5")
        seen = Task(source_uid="seen", project=project, apartment=apartment, work_point=visible_point)
        missing = Task(source_uid="missing", project=project, apartment=apartment, work_point=visible_point)
        hidden = Task(source_uid="hidden", project=project, apartment=apartment, work_point=hidden_point)
        archived = Task(source_uid="archived", project=project, apartment=apartment, work_point=visible_point, is_archived=True)
        db.session.add_all([project, apartment, visible_point, hidden_point, seen, missing, hidden, archived])
        db.session.commit()

        changed = mark_missing_tasks(project.id, {"seen"})
        db.session.commit()

        self.assertEqual(changed, 1)
        self.assertFalse(seen.is_missing_in_latest_sync)
        self.assertTrue(missing.is_missing_in_latest_sync)
        self.assertFalse(hidden.is_missing_in_latest_sync)
        self.assertFalse(archived.is_missing_in_latest_sync)

    def test_save_upload_uses_secure_filename_and_timestamped_upload_folder(self):
        file = FileStorage(stream=BytesIO(b"content"), filename="../../bad name.xlsx")
        fixed_now = datetime(2026, 7, 29, 12, 34, 56)

        with patch("app.services.excel_import.utc_now", return_value=fixed_now):
            path = save_upload(file)

        self.assertTrue(path.exists())
        self.assertEqual(path.name, "20260729_123456_bad_name.xlsx")
        self.assertEqual(path.read_bytes(), b"content")

    def test_worksheet_readers_return_values_struck_cells_and_orange_unsold_cells(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Remarks"
        sheet["A1"] = "Header"
        sheet["A2"] = "Done remark"
        sheet["A2"].font = Font(strike=True)
        sheet["B2"] = "Unsold"
        sheet["B2"].fill = PatternFill(fill_type="solid", fgColor="FFFBBC04")
        path = self._save_workbook("strikes-orange.xlsx", workbook)

        title, rows = worksheet_to_rows(path)
        struck_title, struck_rows, struck, orange = worksheet_to_rows_with_strikes(path)

        self.assertEqual(title, "Remarks")
        self.assertEqual(rows[1][0], "Done remark")
        self.assertEqual(struck_title, "Remarks")
        self.assertEqual(struck_rows[1][1], "Unsold")
        self.assertIn((2, 1), struck)
        self.assertIn((2, 2), orange)

    def test_workbook_sheet_detection_keeps_only_remark_like_sheets_and_preview_is_bounded(self):
        workbook = Workbook()
        remark = workbook.active
        remark.title = "Remarks"
        remark.append(["Квартира", "Пункт 10"])
        remark.append(["1", "Replace handle"])
        empty = workbook.create_sheet("Empty")
        empty.append([""])
        unrelated = workbook.create_sheet("Notes")
        unrelated.append(["Name", "Comment"])
        unrelated.append(["Only", "notes"])
        path = self._save_workbook("remark-detection.xlsx", workbook)

        sheets = workbook_sheets_to_rows_with_strikes(path)
        info = inspect_remarks_workbook(path)
        preview = preview_excel(path, limit=1)

        self.assertEqual([sheet[0] for sheet in sheets], ["Remarks"])
        self.assertEqual(info["matched_sheets"], ["Remarks"])
        self.assertEqual(info["sheet_count"], 3)
        self.assertEqual(preview["active_sheet"], "Remarks")
        self.assertEqual(len(preview["rows"]), 1)

    def test_workbook_sheet_detection_keeps_parking_and_commercial_registry_sheets(self):
        workbook = Workbook()
        apartments = workbook.active
        apartments.title = "Квартиры"
        apartments.append(["№ кв", "Ф.И.О. Дольщиков", "Телефон"])
        apartments.append([1, "Apartment Owner", "+7999"])
        parking = workbook.create_sheet("Паркинг")
        parking.append(["№ паркинга", "Ф.И.О. Дольщиков", "Телефон"])
        parking.append([1, "Parking Owner", "+7998"])
        commercial = workbook.create_sheet("Коммерция")
        commercial.append(["№ ком.\nпомещения", "Ф.И.О. Дольщиков", "Телефон"])
        commercial.append([1, "Commercial Owner", "+7997"])
        path = self._save_workbook("premise-detection.xlsx", workbook)

        sheets = workbook_sheets_to_rows_with_strikes(path)
        info = inspect_remarks_workbook(path)

        self.assertEqual([sheet[0] for sheet in sheets], ["Квартиры", "Паркинг", "Коммерция"])
        self.assertEqual(info["matched_sheets"], ["Квартиры", "Паркинг", "Коммерция"])

    def test_new_project_workbook_imports_storerooms_and_theme_marked_unsold_commercial(self):
        workbook = Workbook()
        storerooms = workbook.active
        storerooms.title = "Кладовые"
        storerooms.append(["Журнал замечаний по объекту строительства"])
        storerooms.append([])
        storerooms.append(["Объект:", "Neo 2 queue test"])
        storerooms.append(["№ кл.", "Собственник", "Номер телефона"])
        storerooms.append([None, None, None, "Дата осмотра", "АПП", "Срок устранения замечаний по АПП", "Стены и потолки"])
        storerooms.append([1, 3, 4, 6, 7, 8, 10])
        storerooms.append([1, "Owner 1", "+79990000001", None, datetime(2026, 10, 1), datetime(2026, 11, 1), "Замечание по кладовке"])
        storerooms.append([2, None, None, None, None, None, None])

        commercial = workbook.create_sheet("Коммерция")
        commercial.append(["Журнал замечаний по объекту строительства"])
        commercial.append([])
        commercial.append(["Объект:", "Neo 2 queue test"])
        commercial.append(["№ кв. проект", "Собственник", "Номер телефона"])
        commercial.append([None, None, None, "Дата осмотра", "АПП", "Срок устранения замечаний по АПП", "Стены и потолки"])
        commercial.append([1, 3, 4, 6, 7, 8, 10])
        commercial.append([1, "Commercial owner", "+79990000002", None, None, None, None])
        commercial.append([2, None, None, None, None, None, None])
        commercial["A8"].fill = PatternFill(fill_type="solid", fgColor=Color(theme=6))
        workbook.loaded_theme = (
            b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            b'<a:themeElements><a:clrScheme name="Test">'
            b'<a:accent3><a:srgbClr val="FBBC04"/></a:accent3>'
            b'</a:clrScheme></a:themeElements></a:theme>'
        )
        path = self._save_workbook("neo-2-registers.xlsx", workbook)

        sheets = workbook_sheets_to_rows_with_strikes(path)
        self.assertIn("Кладовые", [sheet[0] for sheet in sheets])
        self.assertIn("Коммерция", [sheet[0] for sheet in sheets])

        project = Project(name="Neo 2 queue test", has_apartments=True, has_commercial=True, has_storerooms=True)
        db.session.add(project)
        db.session.commit()
        for sheet_name, rows, struck, orange in sheets:
            sync_rows(
                rows,
                sheet_name,
                project_name=project.name,
                struck_cells=struck,
                unsold_color_cells=orange,
                mark_missing=False,
            )
        db.session.commit()

        stats = dashboard_stats(project.id)
        self.assertEqual(stats["storeroom_count"], 2)
        self.assertEqual(stats["accepted_with_remarks_storeroom"], 1)
        self.assertEqual(stats["not_accepted_storeroom_count"], 1)
        self.assertEqual(stats["unsold_commercial_count"], 1)
        self.assertTrue(Apartment.query.filter_by(project_id=project.id, premise_type="commercial", apartment_number="2").one().is_unsold)


if __name__ == "__main__":
    unittest.main()
