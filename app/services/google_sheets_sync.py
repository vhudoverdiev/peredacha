from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import current_app
from google.oauth2 import service_account
from googleapiclient.discovery import build
from app import db
from app.models import Project, SyncLog, Task
from app.services.task_service import sync_rows
from app.services.sync_rollback import build_project_rollback_data

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheets_service():
    credentials_path = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not credentials_path:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not configured")
    credentials = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=credentials)


def spreadsheet_id(override: str | None = None) -> str:
    value = override or current_app.config.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not value:
        raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is not configured")
    return value


def parse_sheet_name_from_range(a1_range: str) -> str:
    if "!" not in a1_range:
        return "Таблица"
    sheet = a1_range.split("!", 1)[0].strip("'")
    return sheet


def get_sheet_metadata(service, spreadsheet_id_override: str | None = None) -> dict[str, int]:
    response = service.spreadsheets().get(spreadsheetId=spreadsheet_id(spreadsheet_id_override)).execute()
    result: dict[str, int] = {}
    for sheet in response.get("sheets", []):
        props = sheet.get("properties", {})
        result[props.get("title")] = props.get("sheetId")
    return result


def read_range(service, a1_range: str, spreadsheet_id_override: str | None = None) -> list[list[Any]]:
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id(spreadsheet_id_override), range=a1_range).execute()
    return result.get("values", [])


def sync_google_sheets(project_name: str = "100 Квартал 7 очередь", spreadsheet_id_override: str | None = None) -> dict:
    service = get_sheets_service()
    range_name = current_app.config.get("GOOGLE_SHEETS_MAIN_RANGE", "Таблица!A1:ZZ10000")
    project = Project.query.filter_by(name=project_name).first()
    sync_log = SyncLog(source_type="google_sheets", source_name=range_name, started_at=datetime.utcnow(), status="running", project_id=project.id if project else None)
    sync_log.rollback_data = build_project_rollback_data(project.id if project else None)
    db.session.add(sync_log)
    db.session.commit()
    try:
        rows = read_range(service, range_name, spreadsheet_id_override=spreadsheet_id_override)
        sheet_name = parse_sheet_name_from_range(range_name)
        result = sync_rows(rows, sheet_name=sheet_name, project_name=project_name, source_name=range_name)
        project = Project.query.filter_by(name=project_name).first()
        sync_log.project_id = project.id if project else sync_log.project_id
        sync_log.created_count = int(result.get("created_count", 0))
        sync_log.updated_count = int(result.get("updated_count", 0))
        sync_log.missing_count = int(result.get("missing_count", 0))
        sync_log.status = "success"
        sync_log.finished_at = datetime.utcnow()
        db.session.commit()
        return result
    except Exception as exc:
        db.session.rollback()
        sync_log.status = "error"
        sync_log.error_message = str(exc)
        sync_log.finished_at = datetime.utcnow()
        db.session.add(sync_log)
        db.session.commit()
        raise


def build_repeat_cell_request(sheet_id: int, row_index_1_based: int, col_index_1_based: int, strike: bool) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_index_1_based - 1,
                "endRowIndex": row_index_1_based,
                "startColumnIndex": col_index_1_based - 1,
                "endColumnIndex": col_index_1_based,
            },
            "cell": {"userEnteredFormat": {"textFormat": {"strikethrough": bool(strike)}}},
            "fields": "userEnteredFormat.textFormat.strikethrough",
        }
    }


def update_task_strike_in_google_sheet(task: Task, strike: bool | None = None) -> None:
    """Apply or remove strikethrough for the source cell of one task."""
    if not task.source_sheet_name or not task.source_row_index or not task.source_column_index:
        raise ValueError("Task does not have source cell coordinates")
    service = get_sheets_service()
    sheet_ids = get_sheet_metadata(service)
    sheet_id = sheet_ids.get(task.source_sheet_name)
    if sheet_id is None:
        raise ValueError(f"Sheet not found: {task.source_sheet_name}")
    request = build_repeat_cell_request(
        sheet_id=sheet_id,
        row_index_1_based=task.source_row_index,
        col_index_1_based=task.source_column_index,
        strike=task.is_done if strike is None else strike,
    )
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id(), body={"requests": [request]}).execute()


def update_all_done_strikes_in_google_sheet(limit: int = 1000) -> int:
    """Push CRM statuses to Google Sheets. Done tasks get strike; undone tasks remove strike."""
    service = get_sheets_service()
    sheet_ids = get_sheet_metadata(service)
    requests = []
    tasks = Task.query.filter(Task.source_sheet_name.isnot(None), Task.source_row_index.isnot(None), Task.source_column_index.isnot(None)).limit(limit).all()
    for task in tasks:
        sheet_id = sheet_ids.get(task.source_sheet_name)
        if sheet_id is None:
            continue
        requests.append(build_repeat_cell_request(sheet_id, task.source_row_index, task.source_column_index, task.is_done))
    if requests:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id(), body={"requests": requests}).execute()
    return len(requests)
