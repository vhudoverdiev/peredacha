import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from openpyxl.styles import Font

from config import Config
from app import create_app, db
from app.models import ChangeLog, STATUS_DONE, SyncLog, Task
from app.services.excel_import import sync_excel_file


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "excel-import-new-completed-task-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ExcelImportNewCompletedTaskTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.tempdir.cleanup()

    def _completed_remark_workbook(self) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Замечания"
        sheet.append(["№ кв", "Строительный номер", "10. Маляры"])
        sheet.append(["1", "1-1-1", "Устранить замечание"])
        sheet["C2"].font = Font(strike=True)
        path = Path(self.tempdir.name) / "completed-remark.xlsx"
        workbook.save(path)
        return path

    def test_new_struck_remark_is_saved_before_its_status_history(self):
        workbook_path = self._completed_remark_workbook()
        result = sync_excel_file(
            workbook_path,
            project_name="Excel completed task QA",
        )

        self.assertEqual(result["created_count"], 1)
        task = Task.query.one()
        self.assertIsNotNone(task.id)
        self.assertEqual(task.status, STATUS_DONE)
        self.assertTrue(task.is_done)

        changes = ChangeLog.query.filter_by(task_id=task.id).order_by(ChangeLog.id.asc()).all()
        self.assertEqual(
            [(change.action, change.old_value, change.new_value) for change in changes],
            [
                ("status_change", "not_started", "done"),
                ("created_from_sync", "", "completed-remark.xlsx / Замечания"),
            ],
        )
        self.assertTrue(all(change.task_id == task.id for change in changes))

        retry_result = sync_excel_file(workbook_path, project_name="Excel completed task QA")
        self.assertEqual(retry_result["created_count"], 0)
        self.assertEqual(retry_result["updated_count"], 1)
        self.assertEqual(Task.query.count(), 1)
        self.assertEqual(ChangeLog.query.filter_by(task_id=task.id).count(), 2)

    def test_failed_import_marks_sync_log_as_error_after_transaction_rollback(self):
        workbook_path = Path(self.tempdir.name) / "broken.xlsx"
        workbook_path.write_text("not used by patched reader", encoding="utf-8")

        with patch(
            "app.services.excel_import.workbook_sheets_to_rows_with_strikes",
            side_effect=RuntimeError("reader boom"),
        ):
            with self.assertRaisesRegex(RuntimeError, "reader boom"):
                sync_excel_file(workbook_path, project_name="Failed import QA")

        sync_log = SyncLog.query.one()
        self.assertEqual(sync_log.status, "error")
        self.assertIn("reader boom", sync_log.error_message)
        self.assertIsNotNone(sync_log.finished_at)


if __name__ == "__main__":
    unittest.main()
