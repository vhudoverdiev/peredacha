import unittest
from datetime import datetime
from unittest.mock import patch

from config import Config
from app import create_app, db
from app.models import Apartment, Project, STATUS_DONE, STATUS_NOT_STARTED, SyncLog, Task, WorkPoint
from app.services.google_sheets_sync import (
    build_repeat_cell_request,
    get_sheet_metadata,
    parse_sheet_name_from_range,
    read_range,
    spreadsheet_id,
    sync_google_sheets,
    update_all_done_strikes_in_google_sheet,
    update_task_strike_in_google_sheet,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "google-sheets-sync-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    GOOGLE_SHEETS_SPREADSHEET_ID = "configured-sheet-id"


class _Execute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeValues:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return _Execute(self.payload)


class _FakeSpreadsheets:
    def __init__(self, values_payload=None, metadata_payload=None):
        self.values_resource = _FakeValues(values_payload or {})
        self.metadata_payload = metadata_payload or {}
        self.get_calls = []
        self.batch_update_calls = []

    def values(self):
        return self.values_resource

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return _Execute(self.metadata_payload)

    def batchUpdate(self, **kwargs):
        self.batch_update_calls.append(kwargs)
        return _Execute({"updated": True})


class _FakeSheetsService:
    def __init__(self, spreadsheets):
        self.spreadsheets_resource = spreadsheets

    def spreadsheets(self):
        return self.spreadsheets_resource


class GoogleSheetsPureContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_spreadsheet_id_prefers_override_and_fails_fast_when_missing(self):
        self.assertEqual(spreadsheet_id(), "configured-sheet-id")
        self.assertEqual(spreadsheet_id("runtime-sheet-id"), "runtime-sheet-id")

        self.app.config["GOOGLE_SHEETS_SPREADSHEET_ID"] = ""
        with self.assertRaisesRegex(RuntimeError, "GOOGLE_SHEETS_SPREADSHEET_ID"):
            spreadsheet_id()

    def test_parse_sheet_name_handles_plain_quoted_and_default_ranges(self):
        self.assertEqual(parse_sheet_name_from_range("Main!A1:B2"), "Main")
        self.assertEqual(parse_sheet_name_from_range("'Transfer Sheet'!A1:Z9"), "Transfer Sheet")
        self.assertTrue(parse_sheet_name_from_range("A1:Z9"))

    def test_read_range_and_metadata_use_configured_spreadsheet_contract(self):
        spreadsheets = _FakeSpreadsheets(
            values_payload={"values": [["apartment", "remark"]]},
            metadata_payload={
                "sheets": [
                    {"properties": {"title": "Main", "sheetId": 101}},
                    {"properties": {"title": "Archive", "sheetId": 202}},
                ]
            },
        )
        service = _FakeSheetsService(spreadsheets)

        self.assertEqual(get_sheet_metadata(service), {"Main": 101, "Archive": 202})
        self.assertEqual(read_range(service, "Main!A1:B2"), [["apartment", "remark"]])
        self.assertEqual(spreadsheets.get_calls[0], {"spreadsheetId": "configured-sheet-id"})
        self.assertEqual(
            spreadsheets.values_resource.calls[0],
            {"spreadsheetId": "configured-sheet-id", "range": "Main!A1:B2"},
        )

    def test_repeat_cell_request_maps_one_based_cell_to_google_zero_based_grid(self):
        request = build_repeat_cell_request(sheet_id=42, row_index_1_based=5, col_index_1_based=3, strike=True)

        self.assertEqual(request["repeatCell"]["range"], {
            "sheetId": 42,
            "startRowIndex": 4,
            "endRowIndex": 5,
            "startColumnIndex": 2,
            "endColumnIndex": 3,
        })
        self.assertEqual(
            request["repeatCell"]["cell"],
            {"userEnteredFormat": {"textFormat": {"strikethrough": True}}},
        )
        self.assertEqual(request["repeatCell"]["fields"], "userEnteredFormat.textFormat.strikethrough")


class GoogleSheetsDatabaseContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.project = Project(name="Project")
        self.apartment = Apartment(project=self.project, apartment_number="12")
        self.work_point = WorkPoint(point_number="1", short_name="Windows")
        db.session.add_all([self.project, self.apartment, self.work_point])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _task(self, *, sheet="Main", row=2, col=4, status=STATUS_NOT_STARTED):
        task = Task(
            source_uid=f"{sheet or 'none'}-{row or 'none'}-{col or 'none'}-{Task.query.count()}",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Fix handle",
            status=status,
            is_done=status == STATUS_DONE,
            source_sheet_name=sheet,
            source_row_index=row,
            source_column_index=col,
        )
        db.session.add(task)
        db.session.commit()
        return task

    def test_update_task_strike_pushes_exact_cell_format_and_respects_explicit_strike(self):
        task = self._task(status=STATUS_DONE)
        spreadsheets = _FakeSpreadsheets(metadata_payload={"sheets": [{"properties": {"title": "Main", "sheetId": 7}}]})
        service = _FakeSheetsService(spreadsheets)

        with patch("app.services.google_sheets_sync.get_sheets_service", return_value=service):
            update_task_strike_in_google_sheet(task, strike=False)

        self.assertEqual(len(spreadsheets.batch_update_calls), 1)
        call = spreadsheets.batch_update_calls[0]
        self.assertEqual(call["spreadsheetId"], "configured-sheet-id")
        request = call["body"]["requests"][0]["repeatCell"]
        self.assertEqual(request["range"]["sheetId"], 7)
        self.assertEqual(request["range"]["startRowIndex"], 1)
        self.assertEqual(request["range"]["startColumnIndex"], 3)
        self.assertFalse(request["cell"]["userEnteredFormat"]["textFormat"]["strikethrough"])

    def test_sync_google_sheets_records_successful_sync_log_times(self):
        service = _FakeSheetsService(_FakeSpreadsheets())
        started = datetime(2026, 8, 3, 10, 0, 0)
        finished = datetime(2026, 8, 3, 10, 0, 5)

        with patch("app.services.google_sheets_sync.get_sheets_service", return_value=service):
            with patch("app.services.google_sheets_sync.read_range", return_value=[["row"]]):
                with patch("app.services.google_sheets_sync.sync_rows", return_value={"created_count": 1, "updated_count": 2, "missing_count": 3}):
                    with patch("app.services.google_sheets_sync.utc_now", side_effect=[started, finished]):
                        result = sync_google_sheets(project_name=self.project.name)

        self.assertEqual(result, {"created_count": 1, "updated_count": 2, "missing_count": 3})
        sync_log = SyncLog.query.one()
        self.assertEqual(sync_log.status, "success")
        self.assertEqual(sync_log.started_at, started)
        self.assertEqual(sync_log.finished_at, finished)
        self.assertEqual(sync_log.created_count, 1)
        self.assertEqual(sync_log.updated_count, 2)
        self.assertEqual(sync_log.missing_count, 3)

    def test_update_task_strike_rejects_missing_coordinates_and_unknown_sheet(self):
        no_coordinates = self._task(sheet=None, row=None, col=None)
        known_sheet_service = _FakeSheetsService(
            _FakeSpreadsheets(metadata_payload={"sheets": [{"properties": {"title": "Main", "sheetId": 7}}]})
        )
        with patch("app.services.google_sheets_sync.get_sheets_service", return_value=known_sheet_service):
            with self.assertRaisesRegex(ValueError, "source cell coordinates"):
                update_task_strike_in_google_sheet(no_coordinates)

        task = self._task(sheet="Missing")
        missing_sheet_service = _FakeSheetsService(
            _FakeSpreadsheets(metadata_payload={"sheets": [{"properties": {"title": "Main", "sheetId": 7}}]})
        )
        with patch("app.services.google_sheets_sync.get_sheets_service", return_value=missing_sheet_service):
            with self.assertRaisesRegex(ValueError, "Sheet not found"):
                update_task_strike_in_google_sheet(task)

    def test_update_all_done_strikes_batches_known_sheets_and_skips_unknown_sources(self):
        self._task(sheet="Main", row=2, col=4, status=STATUS_DONE)
        self._task(sheet="Main", row=3, col=4, status=STATUS_NOT_STARTED)
        self._task(sheet="Missing", row=4, col=4, status=STATUS_DONE)
        spreadsheets = _FakeSpreadsheets(metadata_payload={"sheets": [{"properties": {"title": "Main", "sheetId": 11}}]})
        service = _FakeSheetsService(spreadsheets)

        with patch("app.services.google_sheets_sync.get_sheets_service", return_value=service):
            updated = update_all_done_strikes_in_google_sheet()

        self.assertEqual(updated, 2)
        requests = spreadsheets.batch_update_calls[0]["body"]["requests"]
        self.assertEqual([request["repeatCell"]["range"]["startRowIndex"] for request in requests], [1, 2])
        self.assertEqual(
            [request["repeatCell"]["cell"]["userEnteredFormat"]["textFormat"]["strikethrough"] for request in requests],
            [True, False],
        )

    def test_update_all_done_strikes_does_not_call_google_when_no_known_cells(self):
        self._task(sheet="Missing", row=2, col=4, status=STATUS_DONE)
        spreadsheets = _FakeSpreadsheets(metadata_payload={"sheets": [{"properties": {"title": "Main", "sheetId": 11}}]})
        service = _FakeSheetsService(spreadsheets)

        with patch("app.services.google_sheets_sync.get_sheets_service", return_value=service):
            updated = update_all_done_strikes_in_google_sheet()

        self.assertEqual(updated, 0)
        self.assertEqual(spreadsheets.batch_update_calls, [])


if __name__ == "__main__":
    unittest.main()
