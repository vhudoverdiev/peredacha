from __future__ import annotations

from copy import copy
from datetime import datetime
from pathlib import Path
import re
from typing import Iterable

from flask import current_app
from openpyxl import Workbook, load_workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from app.models import Task, STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR
from app.services.task_service import get_setting


HEADER_FILL = PatternFill(fill_type="solid", fgColor="D9EAF7")
THIN_BORDER = Border(left=Side(style="thin", color="D0D5DD"), right=Side(style="thin", color="D0D5DD"), top=Side(style="thin", color="D0D5DD"), bottom=Side(style="thin", color="D0D5DD"))


def style_header_row(ws) -> None:
    ws.row_dimensions[1].height = 32
    for cell in ws[1]:
        cell.font = Font(bold=True, color="111827")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def apply_borders(ws) -> None:
    for row in ws.iter_rows():
        for cell in row:
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def set_column_widths(ws, widths) -> None:
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = width


def auto_adjust_row_heights(ws) -> None:
    for row_idx in range(2, ws.max_row + 1):
        max_len = 0
        for cell in ws[row_idx]:
            value = str(cell.value or "")
            if value:
                max_len = max(max_len, len(value))
        if max_len > 240:
            ws.row_dimensions[row_idx].height = 90
        elif max_len > 120:
            ws.row_dimensions[row_idx].height = 62
        elif max_len > 60:
            ws.row_dimensions[row_idx].height = 45
        else:
            ws.row_dimensions[row_idx].height = 30


def apply_worksheet_style(ws, widths=None) -> None:
    style_header_row(ws)
    apply_borders(ws)
    if widths:
        set_column_widths(ws, widths)
    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions
    auto_adjust_row_heights(ws)


EXPORT_HEADERS = [
    "Помещение",
    "Строительный номер",
    "Собственник",
    "Телефон",
    "Вид отделки",
    "Пункт",
    "Название пункта",
    "Текст замечания",
    "Ответственный",
    "Статус",
    "Приоритет",
    "Плановая дата",
    "Фактическая дата",
    "Примечание",
    "Нет в новой таблице",
]

EXPORT_STATUS_SUFFIXES = {
    STATUS_DONE: "(лб)",
    STATUS_FINISHERS: "(чистовики)",
    STATUS_CONTRACTOR: "(подрядчик)",
}


def export_tasks_to_excel(tasks: Iterable[Task], filename_prefix: str = "tasks_export") -> Path:
    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    path = folder / filename

    wb = Workbook()
    ws = wb.active
    ws.title = "Задачи CRM"
    ws.append(EXPORT_HEADERS)

    for task in tasks:
        ws.append(
            [
                (task.apartment.label() if task.apartment else ""),
                task.apartment.construction_number,
                task.apartment.owner_name,
                task.apartment.phone,
                task.apartment.finishing_type,
                task.work_point.point_number,
                task.work_point.display_name,
                task.description or task.source_cell_value,
                task.responsible.full_name if task.responsible else "",
                task.status_label(),
                task.priority,
                task.planned_date.isoformat() if task.planned_date else "",
                task.completed_date.isoformat(sep=" ", timespec="minutes") if task.completed_date else "",
                task.comment,
                "Да" if task.is_missing_in_latest_sync else "Нет",
            ]
        )
        if task.is_done:
            for cell in ws[ws.max_row]:
                new_font = copy(cell.font)
                new_font.strike = True
                cell.font = new_font

    apply_worksheet_style(ws, [18, 18, 28, 18, 18, 10, 30, 100, 28, 20, 14, 18, 20, 42, 18])
    wb.save(path)
    return path


def export_simple_tasks_excel(tasks: Iterable[Task], filename_prefix: str, title: str = "Задачи") -> Path:
    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(["Помещение", "Отделка", "Пункт", "Замечание", "Статус", "Дата выполнения"])
    for task in tasks:
        ws.append(
            [
                (task.apartment.label() if task.apartment else ""),
                task.apartment.finishing_type or "",
                task.work_point.display_name,
                task.description or task.source_cell_value or "",
                task.status_label(),
                task.completed_date.strftime("%d.%m.%Y") if task.completed_date else "",
            ]
        )
    apply_worksheet_style(ws, [18, 22, 30, 100, 20, 18])
    wb.save(path)
    return path


def export_remark_tasks_excel(tasks: Iterable[Task], filename_prefix: str, title: str = "Замечания") -> Path:
    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

    wb = Workbook()
    ws_open = wb.active
    ws_open.title = "Не выполненные"
    ws_done = wb.create_sheet("Выполненные")
    headers = ["Помещение", "Отделка", "Замечание"]
    ws_open.append(headers)
    ws_done.append(headers)

    for task in tasks:
        ws = ws_done if task.is_done else ws_open
        remark_text = task.description or task.source_cell_value or ""
        ws.append([
            (task.apartment.label() if task.apartment else ""),
            task.apartment.finishing_type if task.apartment else "",
            remark_text,
        ])
        _apply_remark_strike_style(ws.cell(row=ws.max_row, column=3), remark_text)

    for ws in (ws_open, ws_done):
        apply_worksheet_style(ws, [18, 22, 110])
    wb.save(path)
    return path


def _apply_remark_strike_style(cell, value: object) -> None:
    text = "" if value is None else str(value)
    if not text:
        return
    if text.lstrip().startswith("-"):
        new_font = copy(cell.font)
        new_font.strike = True
        cell.font = new_font
        return
    rich_value = _quoted_strike_rich_text(text)
    if rich_value is not None:
        cell.value = rich_value


def _quoted_strike_rich_text(text: str) -> CellRichText | None:
    quote_pairs = {'"': '"', "«": "»"}
    parts = []
    plain_buffer = []
    index = 0
    found = False

    def flush_plain() -> None:
        if plain_buffer:
            parts.append("".join(plain_buffer))
            plain_buffer.clear()

    while index < len(text):
        opener = text[index]
        closer = quote_pairs.get(opener)
        if not closer:
            plain_buffer.append(text[index])
            index += 1
            continue
        end = text.find(closer, index + 1)
        if end == -1:
            plain_buffer.append(text[index])
            index += 1
            continue
        flush_plain()
        parts.append(opener)
        inner = text[index + 1:end]
        if inner:
            parts.append(TextBlock(InlineFont(strike=True), inner))
            found = True
        parts.append(closer)
        index = end + 1
    flush_plain()
    return CellRichText(parts) if found else None


def _clean_report_remark(value: object) -> str:
    text = "" if value is None else str(value).strip()
    text = re.sub(r"^\s*-\s*", "", text)
    text = re.sub(r"\s*\((?:лб|чистовики|подрядчик)\)\s*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def export_report_tasks_excel(tasks: Iterable[Task], filename_prefix: str) -> Path:
    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Отчет"
    ws.append(["Помещение", "Замечание", "Дата выполнения"])
    for task in tasks:
        ws.append(
            [
                (task.apartment.label() if task.apartment else ""),
                _clean_report_remark(task.description or task.source_cell_value),
                task.completed_date.strftime("%d.%m.%Y") if task.completed_date else "",
            ]
        )
    apply_worksheet_style(ws, [18, 110, 20])
    wb.save(path)
    return path


def _append_status_suffix(value: object, suffix: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return suffix
    # Если отметка уже была в исходнике/предыдущем экспорте — заменяем её на актуальную,
    # а не добавляем второй хвост.
    known_suffixes = sorted((s for s in EXPORT_STATUS_SUFFIXES.values()), key=len, reverse=True)
    changed = True
    while changed:
        changed = False
        lower = text.lower().rstrip()
        for existing_suffix in known_suffixes:
            if lower.endswith(existing_suffix.lower()):
                text = text[: -len(existing_suffix)].rstrip()
                changed = True
                break
    return f"{text} {suffix}"


def _prefix_dash_for_struck_cell(value: object) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return "-"
    return text if text.startswith("-") else f"- {text}"


def _task_export_value(task: Task, current_cell_value: object) -> str:
    # Если текст правили в CRM — выгружаем именно актуальный текст из CRM.
    base = task.description or task.source_cell_value or current_cell_value or ""
    suffix = EXPORT_STATUS_SUFFIXES.get(task.status)
    value = _append_status_suffix(base, suffix) if suffix else str(base)
    return _prefix_dash_for_struck_cell(value)


def _is_tmc_column(ws, column_index: int) -> bool:
    for row_idx in range(1, min(ws.max_row, 8) + 1):
        value = str(ws.cell(row=row_idx, column=column_index).value or "").lower()
        normalized = value.replace("ё", "е")
        if "отступ" in normalized and "тмц" in normalized:
            return True
    return False


def _safe_filename_part(value: str | None) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", " ", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text or "object"


def export_source_excel_with_strikes(source_path: str | None = None, project_name: str | None = None) -> Path:
    """Return a copy of the latest source Excel with CRM statuses applied to source cells."""
    source = source_path or get_setting("latest_excel_path")
    if not source:
        raise FileNotFoundError("Нет последнего Excel-файла. Сначала загрузите .xlsx.")
    source_file = Path(source)
    if not source_file.exists():
        raise FileNotFoundError(f"Файл не найден: {source_file}")

    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    target = folder / f"{_safe_filename_part(project_name)}_{today}.xlsx"

    wb = load_workbook(source_file)
    tasks = (
        Task.query.filter(Task.is_done.is_(True))
        .filter(Task.source_sheet_name.isnot(None))
        .filter(Task.source_row_index.isnot(None))
        .filter(Task.source_column_index.isnot(None))
        .order_by(Task.updated_at.asc(), Task.id.asc())
        .all()
    )
    for task in tasks:
        if not task.source_sheet_name or not task.source_row_index or not task.source_column_index:
            continue
        if task.source_sheet_name not in wb.sheetnames:
            continue
        ws = wb[task.source_sheet_name]
        cell = ws.cell(row=task.source_row_index, column=task.source_column_index)
        cell.value = _task_export_value(task, cell.value)
        if not _is_tmc_column(ws, task.source_column_index):
            new_font = copy(cell.font)
            new_font.strike = True
            cell.font = new_font
    manual_query = Task.query.filter(Task.is_done.is_(True), Task.manually_edited.is_(True))
    if project_name:
        manual_query = manual_query.filter(Task.project.has(name=project_name))
    manual_tasks = [
        task for task in manual_query.order_by(Task.updated_at.asc(), Task.id.asc()).all()
        if not task.source_sheet_name or not task.source_row_index or not task.source_column_index
    ]
    if manual_tasks:
        ws_manual = wb.create_sheet("Добавлено вручную")
        ws_manual.append(["Помещение", "Пункт", "Замечание", "Статус", "Дата выполнения"])
        for task in manual_tasks:
            ws_manual.append([
                task.apartment.label() if task.apartment else "",
                task.work_point.display_name if task.work_point else "",
                task.description or task.source_cell_value or "",
                task.status_label(),
                task.completed_date.strftime("%d.%m.%Y") if task.completed_date else "",
            ])
    for ws in wb.worksheets:
        apply_worksheet_style(ws)
    wb.save(target)
    return target


def export_glass_measurements_excel(rows: Iterable[dict], filename_prefix: str = "glass_measurements") -> Path:
    """Export rows from the glass measurement screen.

    rows is a list of dictionaries with keys: task, measurement, status/status_label.
    """
    folder = Path(current_app.config["EXPORT_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_safe_filename_part(filename_prefix)}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Сделать замер"
    ws.append([
        "№ квартиры/помещения",
        "Корпус",
        "Тип помещения",
        "Текст замечания",
        "Подрядчик / категория",
        "Статус по стеклам",
        "Ширина",
        "Высота",
        "Количество",
        "Тип стеклопакета/стекла",
        "Комментарий",
    ])
    for row in rows:
        task = row.get("task")
        measurement = row.get("measurement")
        apartment = task.apartment if task else None
        ws.append([
            apartment.label() if apartment else "",
            getattr(apartment, "building", "") or "",
            "Коммерция" if apartment and apartment.premise_type == "commercial" else "Квартира",
            (task.description or task.source_cell_value or "") if task else "",
            task.work_point.display_name if task and task.work_point else "",
            row.get("status_label") or (measurement.status_label() if measurement else "Без замера"),
            getattr(measurement, "width", None) or "",
            getattr(measurement, "height", None) or "",
            getattr(measurement, "quantity", None) or "",
            getattr(measurement, "glass_type", None) or "",
            getattr(measurement, "comment", None) or "",
        ])
    apply_worksheet_style(ws, [20, 14, 16, 100, 30, 22, 14, 14, 14, 28, 42])
    wb.save(path)
    return path
