from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import random
import re
import traceback
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import or_, and_
from werkzeug.exceptions import HTTPException

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import Integer, cast, distinct, func
from sqlalchemy.orm import selectinload
from openpyxl import Workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from app import db
from app.forms import CommentForm, ProjectForm, TaskEditForm, UploadExcelForm, UserForm, UserPasswordForm
from app.models import (
    Apartment,
    MaterialRequest,
    MaterialRequestItem,
    MaterialWriteOff,
    MaterialWriteOffItem,
    GlassMeasurement,
    GlassMeasurementItem,
    Project,
    SyncConflict,
    SyncLog,
    SiteErrorReport,
    DeletionActionLog,
    ChangeLog,
    Task,
    TaskComment,
    TASK_STATUSES,
    User,
    WorkCategory,
    WorkPoint,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_EXECUTOR,
    ROLE_VERIFIER,
    ROLE_VIEWER,
    ROLE_LABELS,
    WORKER_ROLES,
    STATUS_DONE,
    STATUS_NOT_STARTED,
    STATUS_FINISHERS,
    STATUS_CONTRACTOR,
    DONE_STATUSES,
)
from app.permissions import can_change_task, can_export, can_manage_mapping, can_manage_sync, role_required
from app.services.changelog_service import log_change
from app.services.document_flow import (
    addendum_field_keys,
    addendum_fields_for_template,
    addendum_options_for_template,
    build_addendum_docx,
    create_builtin_addendum_template,
    prepare_uploaded_word_file,
    safe_docx_filename,
    validate_addendum_template,
)
from app.services.avr_document import (
    build_avr_docx,
    default_avr_phrase,
    format_doc_date,
    format_input_date,
    safe_avr_filename,
)
from app.services.excel_export import export_glass_measurements_excel, export_remark_tasks_excel, export_report_tasks_excel, export_simple_tasks_excel, export_source_excel_with_strikes, export_tasks_to_excel
from app.services.pdf_export import export_assignment_worker_pdf, export_table_pdf, export_tasks_pdf
from app.services.excel_import import preview_excel, save_upload, sync_excel_file
from app.services.google_sheets_sync import sync_google_sheets, update_task_strike_in_google_sheet
from app.services.mapping_service import ensure_default_categories, update_category_points
from app.services.transfer_import import _is_app_mode, _parse_app_date, sync_transfer_statistics
from app.services.task_service import (
    MAIN_WORK_POINT_NUMBERS,
    VISIBLE_WORK_POINT_NUMBERS,
    build_task_query,
    category_stats,
    change_task_status,
    dashboard_stats,
    detect_search_mode,
    get_setting,
    is_apartment_unsold,
    parse_date,
    premise_matches_search,
    set_setting,
    AVR_STATUS_NEEDED,
    AVR_STATUS_SIGNED,
    APP_DEADLINE_EXPIRING,
    APP_DEADLINE_EXPIRED,
    APP_DEADLINE_NO_REMARKS,
)
from app.services.status_rules import is_problem_details_required
from app.services.sync_rollback import apply_sync_rollback
from app.services.uid_service import build_task_uid, stable_hash
from app.services.remark_format import remark_text_html
from app.security import hit_rate_limit, security_event, validate_upload

bp = Blueprint("main", __name__)


TRUE_SETTING_VALUES = {"1", "true", "yes", "on", "да", "checked"}


def _setting_bool(key: str, default: bool = False) -> bool:
    value = get_setting(key, "1" if default else "0")
    return str(value or "").strip().lower() in TRUE_SETTING_VALUES


def _set_setting_bool(key: str, enabled: bool) -> None:
    set_setting(key, "1" if enabled else "0")


def _setting_csv(key: str) -> set[str]:
    value = get_setting(key, "") or ""
    return {item.strip() for item in str(value).split(",") if item.strip()}


def _set_setting_csv(key: str, values) -> None:
    cleaned = sorted({str(value).strip() for value in values if str(value).strip()})
    set_setting(key, ",".join(cleaned))


SECTION_LOCK_CHOICES = [
    {
        "key": "objects",
        "label": "Объекты",
        "icon": "bi-buildings",
        "endpoints": {
            "main.objects", "main.object_new", "main.object_edit", "main.object_delete",
            "main.object_delete_confirm", "main.object_open",
        },
    },
    {"key": "dashboard", "label": "Дашборд", "icon": "bi-grid-1x2", "endpoints": {"main.dashboard"}},
    {
        "key": "remarks",
        "label": "Замечания",
        "icon": "bi-card-checklist",
        "endpoints": {
            "main.task_list", "main.task_detail", "main.task_new", "main.task_delete",
            "main.update_task", "main.add_task_comment", "main.quick_status", "main.inline_update_text",
        },
    },
    {
        "key": "contractors",
        "label": "Подрядчики",
        "icon": "bi-person-gear",
        "endpoints": {"main.contractors_list", "main.contractors_export"},
    },
    {
        "key": "apartments",
        "label": "Квартиры",
        "icon": "bi-building",
        "endpoints": {
            "main.apartments", "main.apartment_detail", "main.update_apartment_po_status",
            "main.update_apartment_inspection_status", "main.update_apartment_inspection_note",
            "main.update_apartment_comment", "main.update_apartment_avr_status",
        },
    },
    {"key": "avr", "label": "АВР", "icon": "bi-file-earmark-check", "endpoints": {"main.avr"}},
    {
        "key": "assignments",
        "label": "Выдача задач",
        "icon": "bi-person-check",
        "endpoints": {
            "main.assignments", "main.assignment_unassign", "main.assignment_delete_from_employee",
            "main.assignment_issued_employee_export", "main.assignment_manual_task_new",
        },
    },
    {
        "key": "report",
        "label": "Отчет",
        "icon": "bi-file-earmark-bar-graph",
        "endpoints": {
            "main.work_report", "main.work_report_export", "main.assignments_report",
            "main.assignments_report_worker_pdf",
        },
    },
    {
        "key": "materials",
        "label": "Расход материалов",
        "icon": "bi-box-seam",
        "endpoints": {
            "main.materials", "main.material_balance_delete", "main.material_request_detail",
            "main.material_request_rename", "main.material_request_update", "main.material_request_delete",
            "main.material_requests_bulk_delete", "main.material_request_export", "main.material_writeoff_edit",
            "main.material_writeoff_delete", "main.material_writeoffs_bulk_delete", "main.material_expense_export",
            "main.material_request_new", "main.material_writeoff_new", "main.material_manual_task_new",
        },
    },
    {
        "key": "glass",
        "label": "Замеры",
        "icon": "bi-window",
        "endpoints": {
            "main.glass_measurements", "main.glass_need_measure", "main.glass_measurement_save",
            "main.glass_status_update", "main.glass_order_export", "main.glass_create_material_request",
            "main.glass_measurements_delete", "main.glass_order",
        },
    },
    {
        "key": "documents",
        "label": "Документы",
        "icon": "bi-files",
        "endpoints": {"main.documents", "main.documents_addendum", "main.documents_download"},
    },
    {
        "key": "notifications",
        "label": "Уведомления",
        "icon": "bi-bell",
        "endpoints": {"main.notifications", "main.archive_apartment_avr"},
    },
    {
        "key": "users",
        "label": "Пользователи",
        "icon": "bi-people",
        "endpoints": {
            "main.users", "main.user_set_password", "main.user_set_password_page",
            "main.user_delete_confirm", "main.user_delete",
        },
    },
    {
        "key": "service",
        "label": "Импорт, синхронизация и распределение",
        "icon": "bi-sliders",
        "endpoints": {
            "main.upload_excel", "main.sync_google", "main.sync_logs", "main.delete_sync_log",
            "main.rollback_sync_log", "main.sync_conflicts", "main.resolve_conflict",
            "main.resolve_conflicts_bulk", "main.mapping_settings",
        },
    },
    {
        "key": "site_errors",
        "label": "Для разработчика",
        "icon": "bi-bug",
        "endpoints": {"main.site_errors", "main.site_error_close", "main.site_error_delete", "main.developer_delete_logs", "main.developer_delete_log_undo"},
    },
    {
        "key": "worker_tasks",
        "label": "Мои задачи сотрудников",
        "icon": "bi-check2-square",
        "endpoints": {"main.my_tasks", "main.my_task_done", "main.my_task_return"},
    },
]


def _section_lock_choice_for_endpoint(endpoint: str | None):
    if not endpoint or endpoint == "main.site_settings":
        return None
    for choice in SECTION_LOCK_CHOICES:
        if endpoint in choice["endpoints"]:
            return choice
    return None


def _future_features():
    return [
        {
            "icon": "bi-person-check",
            "title": "Задачи станут удобнее",
            "text": "Сотрудники смогут получать, принимать и закрывать задачи быстрее, а руководитель — видеть весь процесс без лишних действий.",
        },
        {
            "icon": "bi-box-seam",
            "title": "Отчёты по материалам",
            "text": "По каждой задаче появится понятная отчётность: какие материалы были использованы, в каком объёме и кем.",
        },
        {
            "icon": "bi-file-earmark-text",
            "title": "Документы в пару кликов",
            "text": "АПП, дополнительные соглашения и другие формы можно будет быстро подготовить, отредактировать и отправить на подписание.",
        },
        {
            "icon": "bi-phone",
            "title": "Сильная мобильная версия",
            "text": "Интерфейс будет аккуратно адаптирован под телефон, чтобы работать на объекте было удобно прямо с экрана смартфона.",
        },
        {
            "icon": "bi-phone-vibrate",
            "title": "Отдельное приложение",
            "text": "Следующий шаг — не просто сайт, а полноценное мобильное приложение для быстрых уведомлений и работы в полях.",
        },
        {
            "icon": "bi-house-add",
            "title": "Объекты с кладовками",
            "text": "Структура объектов станет шире: можно будет добавлять и вести кладовые помещения вместе с квартирами и коммерцией.",
        },
    ]


def _documents_under_development_response():
    return render_template(
        "under_development.html",
        layout_mode="documents",
        title="Документы",
        message="Технические работы",
        subtitle="Мы временно скрыли раздел, чтобы не показывать незавершённый функционал.",
        icon="bi-tools",
    )


def _maintenance_response(
    *,
    title: str = "Технические работы",
    message: str = "На сайте ведутся технические работы",
    subtitle: str = "Мы уже обновляем систему и скоро вернём доступ. Пожалуйста, попробуйте зайти немного позже.",
    hint: str = "Доступ для инженера остаётся открытым, чтобы завершить настройку сайта.",
):
    return render_template(
        "maintenance.html",
        title=title,
        message=message,
        subtitle=subtitle,
        hint=hint,
        future_features=_future_features(),
    ), 503


def _blocked_section_response(section_label: str):
    return _maintenance_response(
        title=f"{section_label} временно закрыт",
        message=f"Раздел «{section_label}» временно закрыт",
        subtitle="Мы готовим обновление этого раздела. Как только работы будут завершены, доступ снова появится автоматически.",
    )


def _refresh_sync_dashboard_settings(project_id: int) -> None:
    latest_log = (
        SyncLog.query.filter(
            SyncLog.project_id == project_id,
            SyncLog.status == "success",
            SyncLog.rolled_back_at.is_(None),
        )
        .order_by(SyncLog.started_at.desc())
        .first()
    )
    if latest_log:
        set_setting("last_sync_at", latest_log.started_at.isoformat())
        set_setting("last_sync_source", latest_log.source_name or latest_log.source_type)
    else:
        set_setting("last_sync_at", "—")
        set_setting("last_sync_source", "—")


RU_WEEKDAYS = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}
RU_MONTHS_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_ru_date(value: date | datetime | None = None) -> str:
    value = value or date.today()
    if isinstance(value, datetime):
        value = value.date()
    return f"{value.day} {RU_MONTHS_GENITIVE.get(value.month, '')}".strip()


def format_ru_weekday(value: date | datetime | None = None) -> str:
    value = value or date.today()
    if isinstance(value, datetime):
        value = value.date()
    return RU_WEEKDAYS.get(value.weekday(), "")


def _save_site_error(message: str, kind: str = "user", traceback_text: str | None = None, page_url: str | None = None) -> SiteErrorReport | None:
    message = (message or "").strip()
    if not message:
        return None
    try:
        project = selected_project()
    except Exception:
        project = None
    try:
        user_id = current_user.id if current_user.is_authenticated else None
    except Exception:
        user_id = None
    report = SiteErrorReport(
        project_id=project.id if project else None,
        user_id=user_id,
        kind=kind,
        message=message[:5000],
        page_url=(page_url or request.form.get("page_url") or request.referrer or request.url or "")[:500],
        user_agent=(request.headers.get("User-Agent") or "")[:500],
        traceback_text=(traceback_text or None),
        status="new",
    )
    db.session.add(report)
    db.session.commit()
    return report


def _record_deletion_action(
    action_key: str,
    entity_type: str,
    entity_id: int | None,
    entity_title: str,
    description: str,
    snapshot: dict | None,
    project_id: int | None = None,
) -> DeletionActionLog | None:
    """Write a restorable deletion/unassignment action into developer logs."""
    try:
        log = DeletionActionLog(
            project_id=project_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            action_key=(action_key or "")[:80],
            entity_type=(entity_type or "")[:80],
            entity_id=entity_id,
            entity_title=(entity_title or "")[:255],
            description=(description or "")[:2000],
            snapshot_json=json.dumps(snapshot or {}, ensure_ascii=False, default=str),
            is_undone=False,
        )
        db.session.add(log)
        return log
    except Exception:
        current_app.logger.exception("Failed to record deletion action")
        return None


def _snapshot_model(obj, extra: dict | None = None) -> dict:
    snapshot = {}
    for column in getattr(getattr(obj, "__table__", None), "columns", []):
        value = getattr(obj, column.name, None)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        snapshot[column.name] = value
    if extra:
        snapshot.update(extra)
    return snapshot


def _record_simple_deletion(
    action_key: str,
    entity_type: str,
    obj,
    entity_title: str,
    description: str,
    project_id: int | None = None,
    extra: dict | None = None,
) -> DeletionActionLog | None:
    return _record_deletion_action(
        action_key,
        entity_type,
        getattr(obj, "id", None),
        entity_title,
        description,
        _snapshot_model(obj, extra),
        project_id=project_id,
    )


PO_STATUS_NOT_READY = "not_ready"
PO_STATUS_TO_THROW = "to_throw"
PO_STATUS_THROWN = "thrown"
PO_STATUS_PO = "po"
PO_STATUS_LABELS = {
    PO_STATUS_NOT_READY: "Не готова",
    PO_STATUS_TO_THROW: "Кинуть",
    PO_STATUS_THROWN: "Кинуто",
    PO_STATUS_PO: "ПО",
}
PO_STATUS_CLASSES = {
    PO_STATUS_NOT_READY: "status-pill-danger",
    PO_STATUS_TO_THROW: "status-pill-warning",
    PO_STATUS_THROWN: "status-pill-info",
    PO_STATUS_PO: "status-pill-success",
}
WALL_POINT_NUMBERS = {"11"}

CONTRACTOR_POINT_LABELS = {
    "10": "Вентиляция",
    "11": "Стены. Потолки (штукатурка/шпаклёвка)",
    "12": "Возведение коробки здания",
    "13": "Работы по устройству подстилающего слоя",
    "14": "Работы по возведению блочных перегородок",
    "15": "Разнорабочие",
    "16": "Работы по монтажу ПВХ блоков",
    "17": "Работы по монтажу откосов и подоконников",
    "18": "Работы по монтажу холодного витражного остекления балконов",
    "19": "Работы по монтажу системы отопления, в/с, канализации",
    "20": "Работы по монтажу входных дверей",
    "21": "Электрика",
    "22": "Прочее",
}


@bp.app_context_processor
def inject_globals():
    project_id = current_user.project_id if current_user.is_authenticated and current_user.project_id else session.get("current_project_id")
    current_project = db.session.get(Project, project_id) if project_id else None
    new_site_errors_count = 0
    if current_user.is_authenticated and current_user.role in {ROLE_ADMIN, ROLE_MANAGER}:
        error_query = SiteErrorReport.query.filter(SiteErrorReport.status == "new")
        if current_project:
            error_query = error_query.filter(or_(SiteErrorReport.project_id == current_project.id, SiteErrorReport.project_id.is_(None)))
        new_site_errors_count = error_query.count()
    return {
        "TASK_STATUSES": TASK_STATUSES,
        "STATUS_DONE": STATUS_DONE,
        "DONE_STATUSES": DONE_STATUSES,
        "ROLE_LABELS": ROLE_LABELS,
        "current_project": current_project,
        "new_site_errors_count": new_site_errors_count,
        "hide_documents_section": _setting_bool("hide_documents_section"),
        "mobile_version_under_development": _setting_bool("mobile_version_under_development"),
        "site_maintenance_mode": _setting_bool("site_maintenance_mode"),
        "blocked_site_sections": _setting_csv("blocked_site_sections"),
        "section_lock_choices": SECTION_LOCK_CHOICES,
        "fmt_quantity": fmt_quantity,
        "ru_plural": ru_plural,
        "task_word": task_word,
        "task_count_label": task_count_label,
        "format_ru_date": format_ru_date,
        "format_ru_weekday": format_ru_weekday,
        "remark_text": remark_text_html,
    }


def selected_project() -> Project | None:
    # Если пользователь привязан к конкретному объекту, нельзя подменить объект
    # через session/current_project_id или прямую ссылку.
    if current_user.is_authenticated and current_user.project_id:
        project = db.session.get(Project, current_user.project_id)
        if project:
            session["current_project_id"] = project.id
            return project
        session.pop("current_project_id", None)
        return None

    project_id = session.get("current_project_id")
    if project_id:
        project = db.session.get(Project, project_id)
        if project:
            return project
        session.pop("current_project_id", None)
    return None


def _is_local_redirect(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/")


def _safe_redirect(target: str | None, fallback_endpoint: str = "main.dashboard"):
    return redirect(target if _is_local_redirect(target) else url_for(fallback_endpoint))


def _project_access_allowed(project: Project | None) -> bool:
    if project is None:
        return False
    if current_user.role == ROLE_ADMIN:
        return True
    return not current_user.project_id or current_user.project_id == project.id


def _abort_if_project_forbidden(project: Project | None) -> Project:
    if not _project_access_allowed(project):
        abort(404)
    return project


def _user_can_work_in_project(user: User | None, project: Project | None) -> bool:
    if not user or not project or not user.is_active:
        return False
    return user.role in WORKER_ROLES and (user.project_id is None or user.project_id == project.id)


def _abort_if_user_outside_current_project(user: User | None, project: Project | None = None) -> User:
    project = project or selected_project()
    if user is None:
        abort(404)
    if project and user.project_id is not None and user.project_id != project.id:
        abort(404)
    return user


def _task_for_current_project(task_id: int, project: Project | None = None) -> Task:
    project = project or selected_project()
    if project is None:
        abort(404)
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    return task


def _role_home_endpoint() -> str:
    if current_user.role in WORKER_ROLES:
        return "main.my_tasks"
    if current_user.role == ROLE_VERIFIER:
        return "main.work_report"
    if current_user.role == ROLE_VIEWER:
        return "main.dashboard"
    return "main.dashboard"


def _deny_or_redirect():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return redirect(url_for(_role_home_endpoint()))
    abort(403)


WORKER_ALLOWED_ENDPOINTS = {
    "main.my_tasks",
    "main.my_task_done",
    "main.my_task_return",
    "main.report_error",
}

VERIFIER_ALLOWED_ENDPOINTS = {
    "main.objects",
    "main.object_open",
    "main.work_report",
    "main.work_report_export",
    "main.documents",
    "main.documents_addendum",
    "main.documents_download",
    "main.report_error",
}

VIEWER_ALLOWED_GET_ENDPOINTS = {
    "main.objects",
    "main.object_open",
    "main.dashboard",
    "main.task_list",
    "main.task_detail",
    "main.contractors_list",
    "main.apartments",
    "main.apartment_detail",
    "main.avr",
    "main.glass_measurements",
    "main.materials",
    "main.material_request_detail",
    "main.work_report",
    "main.documents",
    "main.documents_download",
}


@bp.before_request
def enforce_role_access():
    # Единая защита всех main-маршрутов: сначала аутентификация, затем доступ по роли.
    endpoint = request.endpoint or ""
    # Репорт ошибки доступен и со стартового экрана. Он всё равно защищён CSRF и rate limit.
    if endpoint == "main.report_error":
        return None

    if not current_user.is_authenticated:
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("auth.login", next=next_url))

    locked_section = _section_lock_choice_for_endpoint(endpoint)
    if locked_section and locked_section["key"] in _setting_csv("blocked_site_sections"):
        return _blocked_section_response(locked_section["label"])

    if _setting_bool("site_maintenance_mode") and current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        return _maintenance_response()

    if current_user.role in {ROLE_ADMIN, ROLE_MANAGER}:
        return None

    if current_user.role in WORKER_ROLES:
        if endpoint in WORKER_ALLOWED_ENDPOINTS:
            return None
        return _deny_or_redirect()

    if current_user.role == ROLE_VERIFIER:
        if endpoint in VERIFIER_ALLOWED_ENDPOINTS:
            return None
        return _deny_or_redirect()

    if current_user.role == ROLE_VIEWER:
        if request.method in {"GET", "HEAD", "OPTIONS"} and endpoint in VIEWER_ALLOWED_GET_ENDPOINTS:
            return None
        if endpoint == "main.report_error":
            return None
        return _deny_or_redirect()

    abort(403)


def fmt_quantity(value) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return str(int(number))
    return (f"{number:.3f}".rstrip("0").rstrip(".")) or "0"


def ru_plural(value, one: str, few: str, many: str) -> str:
    try:
        number = abs(int(value or 0))
    except (TypeError, ValueError):
        number = 0
    mod10 = number % 10
    mod100 = number % 100
    if mod10 == 1 and mod100 != 11:
        return one
    if 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        return few
    return many


def task_word(value) -> str:
    return ru_plural(value, "задача", "задачи", "задач")


def task_count_label(value) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    return f"{number} {task_word(number)}"


def _can_edit_materials() -> bool:
    return current_user.is_authenticated and current_user.role != "viewer"


def _parse_quantity(value: str | None) -> float | None:
    text_value = str(value or "").strip().replace(",", ".")
    if not text_value:
        return None
    try:
        quantity = float(text_value)
    except ValueError:
        return None
    if quantity <= 0:
        return None
    return quantity


MATERIAL_KEY_SEP = "|||"


def _read_material_rows_from_form(limit: int = 10) -> list[dict[str, object]]:
    names = request.form.getlist("name[]")
    quantities = request.form.getlist("quantity[]")
    units = request.form.getlist("unit[]")
    rows = []
    for idx in range(min(limit, max(len(names), len(quantities), len(units)))):
        name = (names[idx] if idx < len(names) else "").strip()
        unit = (units[idx] if idx < len(units) else "").strip()
        quantity = _parse_quantity(quantities[idx] if idx < len(quantities) else "")
        if not name and quantity is None and not unit:
            continue
        if not name or quantity is None or not unit:
            raise ValueError("Заполните наименование, количество и единицу измерения у каждой позиции")
        rows.append({"name": name, "quantity": quantity, "unit": unit})
    return rows


def _material_key(name: str, unit: str) -> str:
    return f"{name}{MATERIAL_KEY_SEP}{unit}"


def _split_material_key(value: str | None) -> tuple[str, str] | None:
    text = str(value or "")
    if MATERIAL_KEY_SEP not in text:
        return None
    name, unit = text.split(MATERIAL_KEY_SEP, 1)
    name = name.strip()
    unit = unit.strip()
    if not name or not unit:
        return None
    return name, unit


def _normalize_material_identity(name: str, unit: str) -> tuple[str, str]:
    return (" ".join(str(name or "").strip().lower().split()), " ".join(str(unit or "").strip().lower().split()))


def _balance_options(project_id: int) -> list[dict[str, object]]:
    options = []
    for row in _material_balance_rows(project_id):
        balance = float(row.get("balance") or 0)
        if balance <= 0:
            continue
        name = str(row.get("name") or "").strip()
        unit = str(row.get("unit") or "").strip()
        options.append({**row, "key": _material_key(name, unit), "label": f"{name} — остаток {fmt_quantity(balance)} {unit}"})
    return options


def _read_balance_writeoff_row(project_id: int) -> dict[str, object]:
    parsed = _split_material_key(request.form.get("material_key"))
    quantity = _parse_quantity(request.form.get("quantity"))
    if parsed is None:
        raise ValueError("Выберите материал с баланса")
    if quantity is None:
        raise ValueError("Введите корректное количество")
    name, unit = parsed
    balance_rows = _material_balance_rows(project_id)
    row = next((item for item in balance_rows if str(item.get("name")) == name and str(item.get("unit")) == unit), None)
    if row is None or float(row.get("balance") or 0) <= 0:
        raise ValueError("Этого материала нет на балансе")
    balance = float(row.get("balance") or 0)
    if quantity > balance + 0.000001:
        raise ValueError(f"Нельзя списать больше остатка. Доступно: {fmt_quantity(balance)} {unit}")
    return {"name": name, "unit": unit, "quantity": quantity, "balance": balance}


def _task_material_weight(task: Task) -> float:
    text = f"{task.description or ''} {task.source_cell_value or ''}".strip()
    length = max(len(text), 20)
    return float(length) * random.uniform(0.75, 1.35)


def _distribute_material_quantity(tasks: list[Task], quantity: float) -> dict[int, float]:
    if not tasks:
        return {}
    total_int = int(round(float(quantity or 0)))
    if total_int <= 0:
        return {}

    weights = [_task_material_weight(task) for task in tasks]
    if total_int < len(tasks):
        winners = sorted(range(len(tasks)), key=lambda idx: weights[idx], reverse=True)[:total_int]
        return {tasks[idx].id: 1.0 for idx in winners}

    weight_sum = sum(weights) or float(len(tasks))
    raw = [max(1, int(round(total_int * weight / weight_sum))) for weight in weights]
    diff = total_int - sum(raw)
    order = sorted(range(len(tasks)), key=lambda idx: weights[idx], reverse=(diff > 0))
    while diff != 0 and order:
        for idx in order:
            if diff == 0:
                break
            if diff > 0:
                raw[idx] += 1
                diff -= 1
            elif raw[idx] > 1:
                raw[idx] -= 1
                diff += 1
    return {task.id: float(value) for task, value in zip(tasks, raw)}


def _material_balance_rows(project_id: int) -> list[dict[str, object]]:
    balances: dict[tuple[str, str], dict[str, object]] = {}

    def row_for(name: str, unit: str) -> dict[str, object]:
        key = (" ".join(name.strip().lower().split()), " ".join(unit.strip().lower().split()))
        if key not in balances:
            balances[key] = {"name": name.strip(), "unit": unit.strip(), "key": _material_key(name.strip(), unit.strip()), "received": 0.0, "spent": 0.0, "balance": 0.0}
        return balances[key]

    request_items = (
        MaterialRequestItem.query.join(MaterialRequest)
        .filter(MaterialRequest.project_id == project_id)
        .all()
    )
    for item in request_items:
        row = row_for(item.name, item.unit)
        row["received"] = float(row["received"]) + float(item.quantity or 0)

    writeoff_items = (
        MaterialWriteOffItem.query.join(MaterialWriteOff)
        .filter(MaterialWriteOff.project_id == project_id)
        .all()
    )
    for item in writeoff_items:
        row = row_for(item.name, item.unit)
        row["spent"] = float(row["spent"]) + float(item.quantity or 0)

    for row in balances.values():
        row["balance"] = float(row["received"]) - float(row["spent"])

    return sorted(balances.values(), key=lambda row: (str(row["name"]).lower(), str(row["unit"]).lower()))


def _material_task_options(project_id: int, params=None) -> list[Task]:
    # Отдельно нормализуем параметры: раньше фильтр/сортировка в списании материала
    # мог работать нестабильно из-за ImmutableMultiDict и пустых значений.
    raw_params = dict(params or {})
    normalized = {key: (value.strip() if isinstance(value, str) else value) for key, value in raw_params.items()}
    normalized = {key: value for key, value in normalized.items() if value not in (None, "")}
    # В списании материалов сортировку/фильтр по статусу убрали: поиск должен работать
    # как в замечаниях и не прятать строки из-за старого выбранного статуса.
    normalized.pop("status", None)
    normalized.setdefault("sort", "apartment")
    query = build_task_query(normalized, project_id=project_id)
    acceptance_status = normalized.get("acceptance_status")
    if acceptance_status == "accepted":
        query = query.filter(Apartment.is_app_mode.is_(True))
    elif acceptance_status == "waiting":
        query = query.filter(Apartment.is_app_mode.is_(False))
    return (
        query.options(selectinload(Task.apartment), selectinload(Task.work_point))
        .limit(500)
        .all()
    )

def project_stats(project: Project) -> dict[str, int]:
    stats = dashboard_stats(project.id)
    return {
        "tasks": int(stats.get("tasks") or 0),
        "done": int(stats.get("done") or 0),
        "apartments": int(stats.get("apartment_count") or 0),
        "commercial_count": int(stats.get("commercial_count") or 0),
        "premises": int(stats.get("apartments") or 0),
        "transferred": int(stats.get("accepted") or 0),
        "not_transferred": int(stats.get("not_accepted") or 0),
        "unsold": int(stats.get("unsold") or 0),
    }


@bp.route("/objects")
@login_required
def objects():
    projects_query = Project.query.order_by(Project.created_at.desc())
    if current_user.project_id:
        projects_query = projects_query.filter(Project.id == current_user.project_id)
    projects = projects_query.all()
    changed = False
    for project in projects:
        if project.name == "100 Квартал 7 очередь":
            if not project.address:
                project.address = "Архангельск, ул. Поморская, 34"
                changed = True
    if changed:
        db.session.commit()
    project_cards = [{"project": project, "stats": project_stats(project)} for project in projects]
    return render_template("objects.html", project_cards=project_cards)


@bp.route("/objects/new", methods=["GET", "POST"])
@login_required
def object_new():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    form = ProjectForm()
    if form.validate_on_submit():
        if form.has_storerooms.data:
            flash("Кладовки пока нельзя добавить: раздел находится в разработке.", "warning")
            return render_template("object_form.html", form=form, form_title="Добавить объект", submit_label="Создать объект")
        if not (form.has_apartments.data or form.has_commercial.data):
            flash("Выберите хотя бы один тип помещений: квартиры или коммерции.", "warning")
            return render_template("object_form.html", form=form, form_title="Добавить объект", submit_label="Создать объект")
        project = Project(
            name=form.name.data.strip(),
            address=form.address.data.strip() if form.address.data else None,
            has_apartments=bool(form.has_apartments.data),
            has_commercial=bool(form.has_commercial.data),
            has_storerooms=False,
        )
        db.session.add(project)
        db.session.commit()
        session["current_project_id"] = project.id
        flash("Объект создан", "success")
        return redirect(url_for("main.dashboard"))
    return render_template("object_form.html", form=form, form_title="Добавить объект", submit_label="Создать объект")


@bp.route("/objects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def object_edit(project_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = _abort_if_project_forbidden(db.session.get(Project, project_id) or abort(404))
    form = ProjectForm(obj=project)
    if form.validate_on_submit():
        if form.has_storerooms.data:
            flash("Кладовки пока нельзя добавить: раздел находится в разработке.", "warning")
            return render_template("object_form.html", form=form, form_title="Редактировать объект", submit_label="Сохранить")
        if not (form.has_apartments.data or form.has_commercial.data):
            flash("Выберите хотя бы один тип помещений: квартиры или коммерции.", "warning")
            return render_template("object_form.html", form=form, form_title="Редактировать объект", submit_label="Сохранить")
        project.name = form.name.data.strip()
        project.address = form.address.data.strip() if form.address.data else None
        project.has_apartments = bool(form.has_apartments.data)
        project.has_commercial = bool(form.has_commercial.data)
        project.has_storerooms = False
        db.session.commit()
        flash("Объект обновлён", "success")
        return redirect(url_for("main.objects"))
    return render_template("object_form.html", form=form, form_title="Редактировать объект", submit_label="Сохранить")


@bp.route("/objects/<int:project_id>/delete", methods=["POST"])
@login_required
def object_delete(project_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = _abort_if_project_forbidden(db.session.get(Project, project_id) or abort(404))
    _record_simple_deletion(
        "object_delete",
        "project",
        project,
        project.name,
        f"Удалён объект «{project.name}».",
        project_id=None,
        extra={
            "apartments_count": Apartment.query.filter(Apartment.project_id == project.id).count(),
            "tasks_count": Task.query.filter(Task.project_id == project.id).count(),
        },
    )
    task_ids = [task_id for (task_id,) in db.session.query(Task.id).filter(Task.project_id == project.id).all()]
    if task_ids:
        SyncConflict.query.filter(SyncConflict.task_id.in_(task_ids)).delete(synchronize_session=False)
    db.session.delete(project)
    if session.get("current_project_id") == project_id:
        session.pop("current_project_id", None)
    db.session.commit()
    flash("Объект удалён", "success")
    return redirect(url_for("main.objects"))


@bp.route("/objects/<int:project_id>/delete/confirm", methods=["GET"])
@login_required
def object_delete_confirm(project_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = _abort_if_project_forbidden(db.session.get(Project, project_id) or abort(404))
    return render_template("object_delete_confirm.html", project=project)


@bp.route("/objects/<int:project_id>/open")
@login_required
def object_open(project_id: int):
    project = _abort_if_project_forbidden(db.session.get(Project, project_id) or abort(404))
    session["current_project_id"] = project.id
    if current_user.role == ROLE_VERIFIER:
        return redirect(url_for("main.work_report"))
    return redirect(url_for("main.dashboard"))



@bp.route("/")
@login_required
def dashboard():
    if current_user.role in WORKER_ROLES:
        return redirect(url_for("main.my_tasks"))
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    ensure_default_categories()
    db.session.commit()
    stats = dashboard_stats(project.id)
    categories = category_stats(project.id)
    return render_template("dashboard.html", stats=stats, categories=categories, project=project)


@bp.route("/sync/google", methods=["POST"])
@login_required
def sync_google():
    if not can_manage_sync(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    try:
        result = sync_google_sheets(project_name=project.name, spreadsheet_id_override=project.google_sheet_id)
        pending_conflicts = (
            SyncConflict.query.join(Task, SyncConflict.task_id == Task.id)
            .filter(SyncConflict.status == "pending", Task.project_id == project.id)
            .count()
        )
        flash(
            f"Добавлено новых - {result.get('created_count', 0)} , несостыковок - {pending_conflicts}",
            "success",
        )
    except Exception as exc:
        current_app.logger.exception("Google Sheets sync failed")
        flash(f"Ошибка синхронизации Google Sheets: {exc}", "danger")
    return redirect(url_for("main.dashboard"))


@bp.route("/report-error", methods=["POST"])
def report_error():
    if hit_rate_limit("report-error", 6, 300):
        security_event("report_error_rate_limited", "Слишком много сообщений об ошибке", severity="warning")
        abort(429)
    message = (request.form.get("message") or "").strip()
    if not message:
        flash("Опишите ошибку текстом", "warning")
    else:
        _save_site_error(message[:5000], kind="user")
        flash("Ошибка отправлена. Спасибо, разберём.", "success")
    return _safe_redirect(request.form.get("page_url") or request.referrer, "auth.login")


@bp.route("/site-errors")
@login_required
def site_errors():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    query = SiteErrorReport.query.options(selectinload(SiteErrorReport.user), selectinload(SiteErrorReport.project))
    if project:
        query = query.filter(or_(SiteErrorReport.project_id == project.id, SiteErrorReport.project_id.is_(None)))
    status = request.args.get("status") or ""
    kind = request.args.get("kind") or ""
    if status:
        query = query.filter(SiteErrorReport.status == status)
    if kind:
        query = query.filter(SiteErrorReport.kind == kind)
    reports = query.order_by(SiteErrorReport.created_at.desc()).limit(300).all()
    return render_template("site_errors.html", reports=reports, project=project, status=status, kind=kind)


@bp.route("/site-errors/<int:report_id>/close", methods=["POST"])
@login_required
def site_error_close(report_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    report = db.session.get(SiteErrorReport, report_id) or abort(404)
    project = selected_project()
    if project and report.project_id not in {None, project.id}:
        abort(404)
    report.status = "closed" if report.status != "closed" else "new"
    db.session.commit()
    flash("Статус ошибки обновлен", "success")
    return redirect(request.referrer or url_for("main.site_errors"))


@bp.route("/site-errors/<int:report_id>/delete", methods=["POST"])
@login_required
def site_error_delete(report_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    report = db.session.get(SiteErrorReport, report_id) or abort(404)
    project = selected_project()
    if project and report.project_id not in {None, project.id}:
        abort(404)
    snapshot = {
        "kind": report.kind,
        "message": report.message,
        "page_url": report.page_url,
        "user_agent": report.user_agent,
        "traceback_text": report.traceback_text,
        "status": report.status,
        "project_id": report.project_id,
        "user_id": report.user_id,
    }
    _record_deletion_action(
        "site_error_delete",
        "site_error_report",
        report.id,
        "Заявка на регистрацию" if report.kind == "registration" else "Запись для разработчика",
        "Удалена запись из раздела «Для разработчика».",
        snapshot,
        project_id=report.project_id,
    )
    db.session.delete(report)
    db.session.commit()
    flash("Запись удалена. Действие можно отменить в логах удалений.", "success")
    return redirect(url_for("main.site_errors"))


@bp.route("/developer/delete-logs")
@login_required
def developer_delete_logs():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    query = DeletionActionLog.query.options(
        selectinload(DeletionActionLog.user),
        selectinload(DeletionActionLog.project),
        selectinload(DeletionActionLog.undone_by),
    )
    if project:
        query = query.filter(or_(DeletionActionLog.project_id == project.id, DeletionActionLog.project_id.is_(None)))
    logs = query.order_by(DeletionActionLog.created_at.desc(), DeletionActionLog.id.desc()).limit(300).all()
    return render_template("developer_delete_logs.html", logs=logs, project=project)


@bp.route("/developer/delete-logs/<int:log_id>/undo", methods=["POST"])
@login_required
def developer_delete_log_undo(log_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    log = db.session.get(DeletionActionLog, log_id) or abort(404)
    project = selected_project()
    if project and log.project_id not in {None, project.id}:
        abort(404)
    if log.is_undone:
        flash("Это действие уже отменено.", "info")
        return redirect(request.referrer or url_for("main.developer_delete_logs"))
    try:
        snapshot = json.loads(log.snapshot_json or "{}")
    except Exception:
        snapshot = {}

    if log.action_key == "assignment_delete_from_employee":
        task_id = int(snapshot.get("task_id") or log.entity_id or 0)
        task = db.session.get(Task, task_id) or abort(404)
        if log.project_id and task.project_id != log.project_id:
            abort(404)
        responsible_id = snapshot.get("responsible_id")
        responsible = db.session.get(User, int(responsible_id)) if responsible_id else None
        if not responsible or not _user_can_work_in_project(responsible, task.project):
            flash("Не удалось вернуть исполнителя: пользователь больше недоступен для этого объекта.", "warning")
            return redirect(request.referrer or url_for("main.developer_delete_logs"))
        old_responsible = task.responsible_id
        old_date = task.planned_date
        restored_date = parse_date(snapshot.get("planned_date"))
        task.responsible_id = responsible.id
        task.planned_date = restored_date
        task.manually_edited = True
        log_change(task, "field_update", "responsible_id", old_responsible, responsible.id, user_id=current_user.id)
        if old_date != restored_date:
            log_change(task, "field_update", "planned_date", old_date, restored_date, user_id=current_user.id)
        log.is_undone = True
        log.undone_at = datetime.utcnow()
        log.undone_by_user_id = current_user.id
        db.session.commit()
        flash("Удаление задачи у исполнителя отменено. Исполнитель восстановлен.", "success")
        return redirect(request.referrer or url_for("main.developer_delete_logs"))

    if log.action_key == "site_error_delete":
        restored = SiteErrorReport(
            project_id=snapshot.get("project_id"),
            user_id=snapshot.get("user_id"),
            kind=(snapshot.get("kind") or "user")[:30],
            message=(snapshot.get("message") or "Восстановленная запись")[:5000],
            page_url=(snapshot.get("page_url") or "")[:500],
            user_agent=(snapshot.get("user_agent") or "")[:500],
            traceback_text=snapshot.get("traceback_text"),
            status=(snapshot.get("status") or "new")[:30],
        )
        db.session.add(restored)
        log.is_undone = True
        log.undone_at = datetime.utcnow()
        log.undone_by_user_id = current_user.id
        db.session.commit()
        flash("Удалённая запись для разработчика восстановлена.", "success")
        return redirect(url_for("main.site_errors"))

    flash("Для этого действия отмена пока недоступна.", "warning")
    return redirect(request.referrer or url_for("main.developer_delete_logs"))


@bp.app_errorhandler(Exception)
def handle_unexpected_exception(exc):
    if isinstance(exc, HTTPException):
        return exc
    current_app.logger.exception("Unhandled site error")
    try:
        db.session.rollback()
        _save_site_error(str(exc), kind="system", traceback_text=traceback.format_exc(), page_url=request.url)
    except Exception:
        current_app.logger.exception("Failed to save site error report")
        db.session.rollback()
    return render_template("site_error_500.html"), 500


@bp.route("/tasks")
@login_required
def task_list():
    return _task_list_response(contractor_page=False)


@bp.route("/contractors")
@login_required
def contractors_list():
    return _task_list_response(contractor_page=True)


@bp.route("/contractors/export")
@login_required
def contractors_export():
    if not can_export(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    query_args = request.args.to_dict()
    query_args["sort"] = "point"
    tasks = _export_tasks_from_request(query_args, project.id).all()
    point = request.args.get("point")
    point_label = CONTRACTOR_POINT_LABELS.get(point, "Все пункты") if point else "Все пункты"
    path = export_simple_tasks_excel(tasks, f"{project.name}_Подрядчики", title=f"Подрядчики - {point_label}")
    return send_file(path, as_attachment=True, download_name=Path(path).name)


def _selected_task_ids_from_request() -> list[int]:
    task_ids = []
    seen = set()
    for raw_id in request.args.getlist("task_ids"):
        try:
            task_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if task_id in seen:
            continue
        seen.add(task_id)
        task_ids.append(task_id)
    return task_ids


def _export_tasks_from_request(query_args: dict, project_id: int, category_id: int | None = None):
    task_ids = _selected_task_ids_from_request()
    if task_ids:
        return (
            Task.query.options(selectinload(Task.apartment), selectinload(Task.work_point), selectinload(Task.responsible))
            .join(Apartment)
            .join(WorkPoint)
            .filter(Task.project_id == project_id, Task.id.in_(task_ids))
            .order_by(Task.is_done.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc(), WorkPoint.point_number.asc(), Task.id.asc())
        )
    return build_task_query(query_args, category_id=category_id, project_id=project_id)


def _executor_users(project_id: int | None = None) -> list[User]:
    query = User.query.filter(User.is_active.is_(True), User.role.in_(WORKER_ROLES))
    if project_id:
        query = query.filter((User.project_id == project_id) | (User.project_id.is_(None)))
    return query.order_by(User.full_name.asc().nullslast(), User.username.asc()).all()


def _assignment_base_query(project_id: int, params=None):
    params = dict(params or {})
    params.setdefault("sort", "apartment")
    query = build_task_query(params, project_id=project_id).options(
        selectinload(Task.apartment),
        selectinload(Task.work_point),
        selectinload(Task.responsible),
    )
    query = query.filter(
        Task.status.notin_([STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR]),
        Task.is_done.is_(False),
        Task.is_archived.is_(False),
        Task.is_missing_in_latest_sync.is_(False),
    )
    return query


ASSIGNMENT_SMART_BATCH_LIMIT = 10
ASSIGNMENT_DAILY_MAX = None  # дневной лимит выдачи задач отключён


def _display_user_name(user: User | None) -> str:
    if user is None:
        return "Сотрудник"
    return user.full_name or user.username or f"ID {user.id}"


def _assignment_issue_date_map(tasks: list[Task]) -> dict[int, datetime]:
    task_ids = [task.id for task in tasks if task.id]
    if not task_ids:
        return {}
    rows = (
        ChangeLog.query.filter(
            ChangeLog.task_id.in_(task_ids),
            ChangeLog.field_name == "responsible_id",
            ChangeLog.new_value.isnot(None),
            ChangeLog.new_value != "",
        )
        .order_by(ChangeLog.created_at.asc())
        .all()
    )
    result: dict[int, datetime] = {}
    current_responsible = {task.id: str(task.responsible_id or "") for task in tasks}
    for row in rows:
        if current_responsible.get(row.task_id) and str(row.new_value or "") == current_responsible[row.task_id]:
            result[row.task_id] = row.created_at
    for task in tasks:
        result.setdefault(task.id, task.updated_at or task.created_at or datetime.utcnow())
    return result


def _issued_status_payload(task: Task) -> dict[str, str]:
    if task.status == STATUS_DONE or task.is_done:
        return {"label": "Выполнено", "class": "success"}
    return {"label": "Не выполнено", "class": "secondary"}


def _assignment_issued_day_filter(value: str | None) -> tuple[str, date | None]:
    normalized = (value or "today").strip().lower()
    today = date.today()
    if normalized == "tomorrow":
        return "tomorrow", today + timedelta(days=1)
    if normalized == "overdue":
        return "overdue", None
    if normalized == "all":
        return "all", None
    return "today", today


def _assigned_tasks_count_for_day(project_id: int, user_id: int, planned_day: date, exclude_task_ids: list[int] | None = None) -> int:
    query = Task.query.filter(
        Task.project_id == project_id,
        Task.responsible_id == user_id,
        Task.planned_date == planned_day,
        Task.status.notin_([STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR]),
        Task.is_done.is_(False),
        Task.is_archived.is_(False),
        Task.is_missing_in_latest_sync.is_(False),
    )
    if exclude_task_ids:
        query = query.filter(~Task.id.in_(exclude_task_ids))
    return query.count()


def _assignment_export_filename_part(value: str | None) -> str:
    bad_chars = '\\/:*?"<>|'
    cleaned = ''.join(' ' if char in bad_chars else char for char in str(value or '').strip())
    cleaned = ' '.join(cleaned.split())
    return cleaned or 'tasks'


def _assignment_issued_filter_label(issued_filter: str, issued_filter_date: date | None) -> str:
    if issued_filter == 'tomorrow':
        return f"Завтра, {issued_filter_date.strftime('%d.%m.%Y')}" if issued_filter_date else 'Завтра'
    if issued_filter == 'overdue':
        return 'Просроченные задачи'
    if issued_filter == 'all':
        return 'Все выданные задачи'
    return f"Сегодня, {issued_filter_date.strftime('%d.%m.%Y')}" if issued_filter_date else 'Сегодня'


@bp.route("/assignments", methods=["GET", "POST"])
@login_required
def assignments():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    users = _executor_users(project.id)
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"
    view_mode = (request.args.get("view") or "issue").strip()
    if view_mode not in {"issue", "issued"}:
        view_mode = "issue"

    def assignment_task_payload(task: Task):
        responsible = task.responsible
        is_overdue = bool(
            task.responsible_id
            and task.planned_date
            and task.planned_date < date.today()
            and task.status != STATUS_DONE
            and not task.is_done
        )
        return {
            "ok": True,
            "task_id": task.id,
            "responsible_id": task.responsible_id,
            "responsible_name": (responsible.full_name or responsible.username) if responsible else None,
            "planned_date": task.planned_date.strftime("%d.%m.%Y") if task.planned_date else "—",
            "planned_date_iso": task.planned_date.isoformat() if task.planned_date else "",
            "is_overdue": is_overdue,
        }

    def assignment_error(message: str, status_code: int = 400):
        if wants_json:
            return jsonify({"ok": False, "message": message}), status_code
        flash(message, "warning")
        return redirect(request.referrer or url_for("main.assignments"))

    if request.method == "POST":
        update_date_task_id = request.form.get("update_date_task_id", type=int)
        toggle_employee_status_task_id = request.form.get("toggle_employee_status_task_id", type=int)
        postpone_task_id = request.form.get("postpone_task_id", type=int)
        remove_assignee_task_id = request.form.get("remove_assignee_task_id", type=int)
        change_assignee_task_id = request.form.get("change_assignee_task_id", type=int)

        if change_assignee_task_id:
            task = db.session.get(Task, change_assignee_task_id) or abort(404)
            if task.project_id != project.id:
                abort(404)
            new_responsible_id = request.form.get("new_responsible_id", type=int)
            new_responsible = db.session.get(User, new_responsible_id) if new_responsible_id else None
            if not _user_can_work_in_project(new_responsible, project):
                return assignment_error("Выберите нового исполнителя")
            if task.responsible_id == new_responsible.id:
                return assignment_error("Этот исполнитель уже назначен на задачу")
            old_responsible = task.responsible_id
            task.responsible_id = new_responsible.id
            task.manually_edited = True
            log_change(task, "field_update", "responsible_id", old_responsible, new_responsible.id, user_id=current_user.id)
            db.session.commit()
            responsible_name = new_responsible.full_name or new_responsible.username
            if wants_json:
                return jsonify(assignment_task_payload(task) | {"changed_assignee": True, "message": f"Исполнитель изменён: {responsible_name}"})
            flash(f"Исполнитель изменён: {responsible_name}", "success")
            return redirect(request.referrer or url_for("main.assignments", view="issued"))

        if remove_assignee_task_id:
            task = db.session.get(Task, remove_assignee_task_id) or abort(404)
            if task.project_id != project.id:
                abort(404)
            if not task.responsible_id:
                return assignment_error("У задачи уже нет исполнителя")
            old_responsible = task.responsible_id
            task.responsible_id = None
            task.manually_edited = True
            log_change(task, "field_update", "responsible_id", old_responsible, None, user_id=current_user.id)
            db.session.commit()
            if wants_json:
                return jsonify(assignment_task_payload(task) | {"removed": True, "message": "Исполнитель снят. Задача снова без исполнителя."})
            flash("Исполнитель снят. Задача снова без исполнителя.", "success")
            return redirect(request.referrer or url_for("main.assignments", view="issued"))

        if toggle_employee_status_task_id:
            task = db.session.get(Task, toggle_employee_status_task_id) or abort(404)
            if task.project_id != project.id:
                abort(404)
            if not task.responsible_id:
                return assignment_error("Сначала назначьте исполнителя")
            new_status = STATUS_NOT_STARTED if (task.is_done or task.status == STATUS_DONE) else STATUS_DONE
            change_task_status(task, new_status, user_id=current_user.id)
            if wants_json:
                return jsonify(assignment_task_payload(task) | {"status_label": task.status_label(), "status_class": task.status_class(), "is_done": task.is_done, "message": f"Статус сотрудника изменён: {task.status_label()}"})
            flash(f"Статус сотрудника изменён: {task.status_label()}", "success")
            return redirect(request.referrer or url_for("main.assignments", view="issued"))

        if update_date_task_id:
            task = db.session.get(Task, update_date_task_id) or abort(404)
            if task.project_id != project.id:
                abort(404)
            if task.is_done or task.status == STATUS_DONE:
                return assignment_error("Выполненной задаче нельзя изменить дату")
            if not task.responsible_id:
                return assignment_error("Сначала назначьте исполнителя")
            planned_date = parse_date(request.form.get(f"planned_date_{update_date_task_id}") or request.form.get("planned_date"))
            if not planned_date:
                return assignment_error("Выберите дату выполнения задачи")
            old_date = task.planned_date
            task.planned_date = planned_date
            task.manually_edited = True
            if old_date != planned_date:
                log_change(task, "field_update", "planned_date", old_date, planned_date, user_id=current_user.id)
            db.session.commit()
            if wants_json:
                return jsonify(assignment_task_payload(task) | {"message": "Дата выполнения задачи изменена"})
            flash("Дата выполнения задачи изменена", "success")
            return redirect(request.referrer or url_for("main.assignments", view="issued"))

        if postpone_task_id:
            task = db.session.get(Task, postpone_task_id) or abort(404)
            if task.project_id != project.id:
                abort(404)
            if task.is_done or task.status == STATUS_DONE:
                return assignment_error("Выполненную задачу нельзя перенести")
            if not task.responsible_id:
                return assignment_error("Сначала назначьте исполнителя")
            old_date = task.planned_date
            base_date = task.planned_date or date.today()
            task.planned_date = base_date + timedelta(days=1)
            task.manually_edited = True
            log_change(task, "field_update", "planned_date", old_date, task.planned_date, user_id=current_user.id)
            db.session.commit()
            if wants_json:
                return jsonify(assignment_task_payload(task) | {"message": "Задача перенесена на следующий день"})
            flash("Задача перенесена на следующий день", "success")
            return redirect(request.referrer or url_for("main.assignments", view="issued"))

        task_ids = []
        seen_task_ids = set()
        for raw_id in request.form.getlist("task_ids"):
            try:
                task_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if task_id in seen_task_ids:
                continue
            seen_task_ids.add(task_id)
            task_ids.append(task_id)
        responsible_id = request.form.get("responsible_id", type=int)
        planned_date = parse_date(request.form.get("planned_date")) or date.today()
        responsible = db.session.get(User, responsible_id) if responsible_id else None
        if not task_ids:
            flash("Выберите хотя бы одну задачу", "warning")
        elif not _user_can_work_in_project(responsible, project):
            flash("Выберите исполнителя", "warning")
        else:
            existing_tasks = (
                Task.query.filter(Task.project_id == project.id, Task.id.in_(task_ids))
                .filter(Task.status.notin_([STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR]), Task.is_done.is_(False))
                .all()
            )
            already_assigned = [task for task in existing_tasks if task.responsible_id]
            tasks = [task for task in existing_tasks if not task.responsible_id]
            if not tasks:
                skipped = len(already_assigned)
                if skipped:
                    flash(f"Задача уже выдана сотруднику. Повторная выдача не выполнена. Пропущено: {task_count_label(skipped)}", "warning")
                else:
                    flash("Нет доступных задач для выдачи", "warning")
                return redirect(url_for("main.assignments"))
            for task in tasks:
                old_responsible = task.responsible_id
                old_date = task.planned_date
                task.responsible_id = responsible.id
                task.planned_date = planned_date
                task.manually_edited = True
                if old_responsible != responsible.id:
                    log_change(task, "field_update", "responsible_id", old_responsible, responsible.id, user_id=current_user.id)
                if old_date != planned_date:
                    log_change(task, "field_update", "planned_date", old_date, planned_date, user_id=current_user.id)
            db.session.commit()
            message = f"Выдано: {task_count_label(len(tasks))}"
            if already_assigned:
                message += f". Уже были выданы и пропущены: {task_count_label(len(already_assigned))}"
            flash(message, "success" if not already_assigned else "warning")
            return redirect(url_for("main.assignments"))

    # В выдаче задач оставляем один умный поиск. Старые параметры сортировки/узких фильтров
    # намеренно не тащим дальше, чтобы экран не путал пользователя.
    query_args = {"q": (request.args.get("q") or "").strip()}
    smart_mode = request.args.get("smart") == "1"
    smart_user_id = request.args.get("smart_user_id", type=int)
    smart_date = parse_date(request.args.get("smart_date")) or date.today()
    smart_user = db.session.get(User, smart_user_id) if smart_user_id else None
    if smart_user and not _user_can_work_in_project(smart_user, project):
        smart_user = None
    smart_limit = ASSIGNMENT_SMART_BATCH_LIMIT
    assigned_today_count = 0

    if smart_mode and smart_user:
        assigned_today_count = (
            Task.query.filter(
                Task.project_id == project.id,
                Task.responsible_id == smart_user.id,
                Task.planned_date == smart_date,
                Task.status.notin_([STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR]),
                Task.is_done.is_(False),
                Task.is_archived.is_(False),
                Task.is_missing_in_latest_sync.is_(False),
            ).count()
        )
        smart_limit = ASSIGNMENT_SMART_BATCH_LIMIT
        smart_args = {k: v for k, v in query_args.items() if k not in {"smart", "smart_user_id", "smart_date", "page"}}
        smart_args["status"] = "not_done"
        query = _assignment_base_query(project.id, smart_args).filter(Task.responsible_id.is_(None))
        tasks = query.limit(smart_limit).all() if smart_limit > 0 else []
        pagination = None
        prev_args = {}
        next_args = {}
        assignment_total = len(tasks)
    else:
        query = _assignment_base_query(project.id, query_args).filter(Task.responsible_id.is_(None))
        page = request.args.get("page", 1, type=int)
        pagination = query.paginate(page=page, per_page=80, error_out=False)
        tasks = pagination.items
        prev_args = {k: v for k, v in query_args.items() if v}
        next_args = {k: v for k, v in query_args.items() if v}
        if pagination.has_prev:
            prev_args["page"] = pagination.prev_num
        if pagination.has_next:
            next_args["page"] = pagination.next_num
        assignment_total = pagination.total

    today_value = date.today()
    issued_filter, issued_filter_date = _assignment_issued_day_filter(request.args.get("issued_day"))
    issued_query_builder = (
        Task.query.options(selectinload(Task.apartment), selectinload(Task.work_point), selectinload(Task.responsible))
        .filter(
            Task.project_id == project.id,
            Task.responsible_id.isnot(None),
            Task.status.notin_([STATUS_FINISHERS, STATUS_CONTRACTOR]),
            Task.is_archived.is_(False),
            Task.is_missing_in_latest_sync.is_(False),
        )
    )
    overdue_filter = (
        Task.planned_date.isnot(None),
        Task.planned_date < today_value,
        Task.status != STATUS_DONE,
        Task.is_done.is_(False),
    )
    overdue_total = issued_query_builder.filter(*overdue_filter).count()
    if issued_filter == "overdue":
        issued_query_builder = issued_query_builder.filter(*overdue_filter)
        issued_order = (Task.planned_date.asc().nullslast(), Task.responsible_id.asc(), Task.id.asc())
    else:
        if issued_filter_date is not None:
            issued_query_builder = issued_query_builder.filter(Task.planned_date == issued_filter_date)
        issued_order = (Task.responsible_id.asc(), Task.is_done.asc(), Task.planned_date.asc().nullslast(), Task.id.asc())
    issued_query = (
        issued_query_builder
        .order_by(*issued_order)
        .limit(1000 if issued_filter == "overdue" else 800)
        .all()
    )
    issue_dates = _assignment_issue_date_map(issued_query)
    issued_groups = []
    issued_overdue_day_groups = []
    issued_total = len(issued_query)

    def make_issued_row(task: Task) -> dict:
        overdue_days = (today_value - task.planned_date).days if task.planned_date else 0
        return {
            "task": task,
            "issued_at": issue_dates.get(task.id),
            "employee_status": _issued_status_payload(task),
            "overdue_days": max(overdue_days, 0),
        }

    if issued_filter == "overdue":
        rows_by_day: dict[date, list[dict]] = {}
        for task in issued_query:
            if task.planned_date is None:
                continue
            rows_by_day.setdefault(task.planned_date, []).append(make_issued_row(task))
        for planned_day in sorted(rows_by_day):
            day_rows = rows_by_day[planned_day]
            day_groups = []
            for user in users:
                user_rows = [row for row in day_rows if row["task"].responsible_id == user.id]
                if user_rows:
                    day_groups.append({"user": user, "rows": user_rows, "tasks": [row["task"] for row in user_rows]})
            if day_groups:
                issued_overdue_day_groups.append({
                    "date": planned_day,
                    "label": planned_day.strftime("%d.%m.%Y"),
                    "total": len(day_rows),
                    "groups": day_groups,
                })
    else:
        for user in users:
            user_rows = [
                make_issued_row(task)
                for task in issued_query
                if task.responsible_id == user.id
            ]
            if user_rows:
                issued_groups.append({"user": user, "rows": user_rows, "tasks": [row["task"] for row in user_rows]})

    finishing_types = [
        x[0]
        for x in db.session.query(distinct(Apartment.finishing_type))
        .filter(Apartment.project_id == project.id, Apartment.finishing_type.isnot(None))
        .all()
    ]
    return render_template(
        "assignments.html",
        project=project,
        tasks=tasks,
        pagination=pagination,
        users=users,
        points=_contractor_point_options(),
        finishing_types=finishing_types,
        args=request.args,
        prev_args=prev_args,
        next_args=next_args,
        smart_mode=smart_mode,
        smart_user=smart_user,
        smart_date=smart_date,
        smart_limit=smart_limit,
        assigned_today_count=assigned_today_count,
        assignment_total=assignment_total,
        view_mode=view_mode,
        issued_groups=issued_groups,
        issued_overdue_day_groups=issued_overdue_day_groups,
        issued_total=issued_total,
        overdue_total=overdue_total,
        issued_filter=issued_filter,
        issued_filter_date=issued_filter_date,
        today=today_value,
    )


@bp.route("/assignments/<int:task_id>/unassign", methods=["POST"])
@login_required
def assignment_unassign(task_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "message": "Выберите объект"}), 400
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"
    if not task.responsible_id:
        if wants_json:
            return jsonify({"ok": False, "message": "У задачи уже нет исполнителя"}), 400
        flash("У задачи уже нет исполнителя", "warning")
        return redirect(request.referrer or url_for("main.assignments", view="issued"))

    old_responsible = task.responsible_id
    task.responsible_id = None
    task.manually_edited = True
    log_change(task, "field_update", "responsible_id", old_responsible, None, user_id=current_user.id)
    db.session.commit()

    payload = {
        "ok": True,
        "task_id": task.id,
        "responsible_id": None,
        "responsible_name": None,
        "planned_date": task.planned_date.strftime("%d.%m.%Y") if task.planned_date else "—",
        "planned_date_iso": task.planned_date.isoformat() if task.planned_date else "",
        "removed": True,
        "message": "Исполнитель снят. Задача снова без исполнителя.",
    }
    if wants_json:
        return jsonify(payload)
    flash(payload["message"], "success")
    return redirect(request.referrer or url_for("main.assignments", view="issued"))


@bp.route("/assignments/<int:task_id>/delete-from-employee", methods=["POST"])
@login_required
def assignment_delete_from_employee(task_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    if not task.responsible_id:
        flash("У задачи уже нет исполнителя", "warning")
        return redirect(request.referrer or url_for("main.assignments", view="issued"))

    old_responsible = task.responsible_id
    old_responsible_user = task.responsible
    old_date = task.planned_date
    _record_deletion_action(
        "assignment_delete_from_employee",
        "task_assignment",
        task.id,
        f"Задача #{task.id}",
        f"Задача удалена у исполнителя: {((old_responsible_user.full_name or old_responsible_user.username) if old_responsible_user else '—')}.",
        {
            "task_id": task.id,
            "responsible_id": old_responsible,
            "planned_date": old_date.isoformat() if old_date else None,
            "status": task.status,
            "is_done": bool(task.is_done),
        },
        project_id=task.project_id,
    )
    task.responsible_id = None
    task.planned_date = None
    task.manually_edited = True
    log_change(task, "field_update", "responsible_id", old_responsible, None, user_id=current_user.id)
    if old_date is not None:
        log_change(task, "field_update", "planned_date", old_date, None, user_id=current_user.id)
    db.session.commit()
    flash("Задача удалена у сотрудника и снова доступна без исполнителя. Действие можно отменить в логах удалений.", "success")
    return redirect(request.referrer or url_for("main.assignments", view="issued"))


@bp.route("/assignments/issued/<int:user_id>/export")
@login_required
def assignment_issued_employee_export(user_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))

    employee = db.session.get(User, user_id) or abort(404)
    if employee.role not in WORKER_ROLES or (employee.project_id is not None and employee.project_id != project.id):
        abort(404)

    today_value = date.today()
    issued_filter, issued_filter_date = _assignment_issued_day_filter(request.args.get("issued_day"))
    query = (
        Task.query.options(selectinload(Task.apartment), selectinload(Task.work_point), selectinload(Task.responsible))
        .filter(
            Task.project_id == project.id,
            Task.responsible_id == employee.id,
            Task.status.notin_([STATUS_FINISHERS, STATUS_CONTRACTOR]),
            Task.is_archived.is_(False),
            Task.is_missing_in_latest_sync.is_(False),
        )
    )
    if issued_filter == "overdue":
        query = query.filter(
            Task.planned_date.isnot(None),
            Task.planned_date < today_value,
            Task.status != STATUS_DONE,
            Task.is_done.is_(False),
        )
        order_by = (Task.planned_date.asc().nullslast(), Task.id.asc())
    else:
        if issued_filter_date is not None:
            query = query.filter(Task.planned_date == issued_filter_date)
        order_by = (Task.is_done.asc(), Task.planned_date.asc().nullslast(), Task.id.asc())

    tasks = (
        query.order_by(*order_by)
        .limit(1000)
        .all()
    )
    issue_dates = _assignment_issue_date_map(tasks)

    wb = Workbook()
    ws = wb.active
    ws.title = "Задачи"

    employee_name = _display_user_name(employee)
    role_label = ROLE_LABELS.get(employee.role, employee.role)
    filter_label = _assignment_issued_filter_label(issued_filter, issued_filter_date)

    ws.append(["Сотрудник", employee_name, "Роль", role_label])
    ws.append(["Объект", project.name, "Период", filter_label])
    ws.append(["Всего задач", len(tasks), "Дата выгрузки", datetime.now().strftime("%d.%m.%Y %H:%M")])
    ws.append([])
    ws.append(["Помещение", "Задача", "Дата выполнения", "Статус", "Отделка", "Дата выдачи"])

    for task in tasks:
        apartment = task.apartment
        issued_at = issue_dates.get(task.id)
        employee_status = _issued_status_payload(task)["label"]
        ws.append([
            apartment.label() if apartment else "—",
            task.description or task.source_cell_value or "",
            task.planned_date.strftime("%d.%m.%Y") if task.planned_date else "—",
            employee_status,
            apartment.finishing_type if apartment else "",
            issued_at.strftime("%d.%m.%Y %H:%M") if issued_at else "",
        ])
        if task.is_done:
            for cell in ws[ws.max_row]:
                cell.font = Font(strike=True, color="667085")

    for cell in ws[1]:
        cell.font = Font(bold=True, color="111827")
    for cell in ws[2]:
        cell.font = Font(bold=True, color="111827")
    for cell in ws[3]:
        cell.font = Font(bold=True, color="111827")

    header_fill = PatternFill("solid", fgColor="EAF0F7")
    for cell in ws[5]:
        cell.font = Font(bold=True, color="111827")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    widths = [16, 90, 18, 18, 22, 20]
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width

    for row in ws.iter_rows(min_row=6):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for row_idx in range(6, ws.max_row + 1):
        ws.row_dimensions[row_idx].height = 42

    ws.freeze_panes = "A6"
    if ws.max_row >= 5:
        ws.auto_filter.ref = f"A5:F{ws.max_row}"

    safe_project = _assignment_export_filename_part(project.name)
    safe_employee = _assignment_export_filename_part(employee_name)
    safe_period = _assignment_export_filename_part(filter_label.replace(',', ''))
    filename = f"{safe_project}_{safe_employee}_задачи_{safe_period}_{date.today().strftime('%Y-%m-%d')}.xlsx"
    return _make_excel_response(wb, filename)


def _manual_assignment_work_point() -> WorkPoint:
    point = WorkPoint.query.filter_by(point_number="ручная", source_sheet_name="assignment_manual").first()
    if point is None:
        point = WorkPoint(
            point_number="ручная",
            source_sheet_name="assignment_manual",
            original_column_name="Ручная задача",
            short_name="Ручная задача",
            is_active=True,
        )
        db.session.add(point)
        db.session.flush()
    return point


@bp.route("/assignments/manual/new", methods=["GET", "POST"])
@login_required
def assignment_manual_task_new():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    users = _executor_users(project.id)
    apartments = _project_apartment_options(project.id)

    if request.method == "POST":
        apartment_id = request.form.get("apartment_id", type=int)
        responsible_id = request.form.get("responsible_id", type=int)
        planned_date = parse_date(request.form.get("planned_date"))
        text = (request.form.get("description") or "").strip()
        apartment = db.session.get(Apartment, apartment_id) if apartment_id else None
        work_point = _manual_assignment_work_point()
        responsible = db.session.get(User, responsible_id) if responsible_id else None

        if not apartment or apartment.project_id != project.id:
            flash("Выберите квартиру", "warning")
        elif not text:
            flash("Введите ручную задачу", "warning")
        elif responsible_id and not _user_can_work_in_project(responsible, project):
            flash("Выберите корректного исполнителя", "warning")
        else:
            source_uid = build_task_uid(
                project.name,
                apartment.construction_number or "",
                apartment.apartment_number or "",
                work_point.point_number,
                work_point.display_name,
                text,
            )
            if Task.query.filter_by(source_uid=source_uid).first():
                source_uid = stable_hash([source_uid, "assignment-manual", datetime.utcnow().isoformat()])
            task = Task(
                source_uid=source_uid,
                project_id=project.id,
                apartment_id=apartment.id,
                work_point_id=work_point.id,
                title=work_point.display_name,
                description=text,
                source_cell_value=text,
                source_sheet_name="assignment_manual",
                status=STATUS_NOT_STARTED,
                is_done=False,
                responsible_id=responsible.id if responsible else None,
                planned_date=planned_date,
                manually_edited=True,
                last_seen_at=datetime.utcnow(),
                source_hash=stable_hash([text]),
            )
            db.session.add(task)
            db.session.flush()
            log_change(task, "manual_assignment_created", None, None, text, user_id=current_user.id)
            db.session.commit()
            flash("Ручная задача добавлена", "success")
            return redirect(url_for("main.assignments"))

    return render_template(
        "assignment_task_form.html",
        project=project,
        apartments=apartments,
        users=users,
    )


@bp.route("/assignments/report")
@login_required
def assignments_report():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    report_date = parse_date(request.args.get("date")) or date.today()
    users = _executor_users(project.id)
    user_id = request.args.get("user_id", type=int)
    if user_id and not any(user.id == user_id for user in users):
        abort(404)
    query = (
        Task.query.options(selectinload(Task.apartment), selectinload(Task.work_point), selectinload(Task.responsible))
        .join(User, Task.responsible_id == User.id)
        .join(Apartment)
        .filter(
            Task.project_id == project.id,
            Task.responsible_id.isnot(None),
            Task.status.notin_([STATUS_FINISHERS, STATUS_CONTRACTOR]),
        )
        .filter(
            or_(
                Task.planned_date == report_date,
                func.date(Task.completed_date) == report_date.isoformat(),
            )
        )
    )
    if user_id:
        query = query.filter(Task.responsible_id == user_id)
    tasks = query.order_by(User.full_name.asc(), Task.is_done.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc()).all()
    grouped = []
    for user in users:
        user_tasks = [task for task in tasks if task.responsible_id == user.id]
        if user_tasks or not user_id or user.id == user_id:
            grouped.append({
                "user": user,
                "tasks": user_tasks,
                "done": sum(1 for task in user_tasks if task.status == STATUS_DONE),
                "left": sum(1 for task in user_tasks if task.status != STATUS_DONE),
            })
    report_totals = {
        "workers": len([group for group in grouped if group["tasks"]]),
        "tasks": sum(len(group["tasks"]) for group in grouped),
        "done": sum(group["done"] for group in grouped),
        "left": sum(group["left"] for group in grouped),
    }
    return render_template(
        "assignment_report.html",
        project=project,
        grouped=grouped,
        users=users,
        report_date=report_date,
        selected_user_id=user_id,
        report_totals=report_totals,
    )


@bp.route("/assignments/report/<int:user_id>/pdf")
@bp.route("/assignments/report/<int:user_id>/excel")
@login_required
def assignments_report_worker_pdf(user_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    report_date = parse_date(request.args.get("date")) or date.today()
    user = db.session.get(User, user_id) or abort(404)
    if not _user_can_work_in_project(user, project):
        abort(404)
    tasks = (
        Task.query.options(selectinload(Task.apartment), selectinload(Task.work_point), selectinload(Task.responsible))
        .filter(
            Task.project_id == project.id,
            Task.responsible_id == user.id,
            Task.status.notin_([STATUS_FINISHERS, STATUS_CONTRACTOR]),
        )
        .filter(
            or_(
                Task.planned_date == report_date,
                func.date(Task.completed_date) == report_date.isoformat(),
            )
        )
        .join(Apartment)
        .order_by(Task.is_done.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc(), Task.id.asc())
        .all()
    )
    worker_name = user.full_name or user.username or f"worker_{user.id}"
    title = f"Ежедневный отчет - {worker_name} - {report_date.strftime('%d.%m.%Y')}"
    filename_prefix = f"{project.name}_{worker_name}_{report_date.strftime('%d.%m.%Y')}"
    path = export_simple_tasks_excel(tasks, filename_prefix=filename_prefix, title=title)
    return send_file(path, as_attachment=True, download_name=Path(path).name)


@bp.route("/my-tasks")
@login_required
def my_tasks():
    if current_user.role in {ROLE_ADMIN, ROLE_MANAGER}:
        return redirect(url_for("main.dashboard"))
    project = selected_project()
    today_value = date.today()
    query = Task.query.options(selectinload(Task.apartment), selectinload(Task.work_point)).filter(Task.responsible_id == current_user.id)
    if project:
        query = query.filter(Task.project_id == project.id)
    query = query.filter(Task.is_archived.is_(False), Task.is_missing_in_latest_sync.is_(False))
    query = query.filter(
        or_(
            Task.planned_date == today_value,
            and_(Task.planned_date.is_(None), Task.status != STATUS_DONE),
            and_(Task.status == STATUS_DONE, func.date(Task.completed_date) == today_value.isoformat()),
        )
    )
    tasks = query.outerjoin(Apartment).order_by(Task.is_done.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc(), Task.updated_at.desc()).all()
    counters = {
        "done": sum(1 for task in tasks if task.status == STATUS_DONE),
        "left": sum(1 for task in tasks if task.status != STATUS_DONE),
        "all": len(tasks),
    }
    role_label = ROLE_LABELS.get(current_user.role, "Исполнитель")
    return render_template("my_tasks.html", project=project, tasks=tasks, counters=counters, today=today_value, role_label=role_label)


def _worker_status_payload(task: Task):
    return {
        "ok": True,
        "task_id": task.id,
        "status": task.status,
        "status_label": task.status_label(),
        "status_class": task.status_class(),
        "is_done": task.status == STATUS_DONE,
    }


@bp.route("/my-tasks/<int:task_id>/done", methods=["POST"])
@login_required
def my_task_done(task_id: int):
    task = db.session.get(Task, task_id) or abort(404)
    project = selected_project()
    if current_user.role in {ROLE_ADMIN, ROLE_MANAGER}:
        if project is None or task.project_id != project.id:
            abort(404)
    elif task.responsible_id != current_user.id:
        abort(403)
    change_task_status(task, STATUS_DONE, user_id=current_user.id)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json":
        return jsonify(_worker_status_payload(task))
    flash("Задача отмечена выполненной", "success")
    return redirect(url_for("main.my_tasks"))


@bp.route("/my-tasks/<int:task_id>/return", methods=["POST"])
@login_required
def my_task_return(task_id: int):
    task = db.session.get(Task, task_id) or abort(404)
    project = selected_project()
    if current_user.role in {ROLE_ADMIN, ROLE_MANAGER}:
        if project is None or task.project_id != project.id:
            abort(404)
    elif task.responsible_id != current_user.id:
        abort(403)
    change_task_status(task, STATUS_NOT_STARTED, user_id=current_user.id)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json":
        return jsonify(_worker_status_payload(task))
    flash("Задача возвращена в работу", "success")
    return redirect(url_for("main.my_tasks"))



GLASS_STATUS_NONE = "none"
GLASS_STATUS_MEASURE_NEEDED = "measure_needed"
GLASS_STATUS_MEASURED = "measured"
GLASS_STATUS_ORDERED = "ordered"
GLASS_STATUS_REPLACED = "replaced"

GLASS_STATUS_LABELS = {
    GLASS_STATUS_NONE: "Без замера",
    "not_ordered": "Сделать замер",
    GLASS_STATUS_MEASURE_NEEDED: "Сделать замер",
    GLASS_STATUS_MEASURED: "Замер внесён",
    GLASS_STATUS_ORDERED: "Заказано",
    GLASS_STATUS_REPLACED: "Поменяно",
}

GLASS_ITEM_TYPES = ["Стеклопакет", "Стекло", "Рама", "Подоконник"]


def _glass_item_rows(measurement: GlassMeasurement | None) -> list[dict[str, object]]:
    if measurement is None:
        return []
    rows = []
    for item in getattr(measurement, "items", []) or []:
        rows.append({
            "id": item.id,
            "item_type": item.item_type or "Стеклопакет",
            "width": item.width,
            "height": item.height,
            "quantity": item.quantity or 1,
            "size_label": item.size_label(),
            "title_label": item.title_label(),
        })
    if rows:
        return rows
    if (measurement.width and measurement.height) or (measurement.size or "").strip():
        item_type = measurement.glass_type or "Стеклопакет"
        rows.append({
            "id": None,
            "item_type": item_type,
            "width": measurement.width,
            "height": measurement.height,
            "quantity": measurement.quantity or 1,
            "size_label": measurement.size_label(),
            "title_label": f"{item_type} {measurement.size_label()}".strip(),
        })
    return rows


def _task_search_blob(task: Task) -> str:
    apartment = task.apartment
    categories = []
    if task.work_point:
        categories = [category.name for category in task.work_point.categories]
    parts = [
        apartment.label() if apartment else "",
        apartment.apartment_number if apartment else "",
        apartment.construction_number if apartment else "",
        apartment.building if apartment else "",
        "коммерция" if apartment and apartment.premise_type == "commercial" else "квартира",
        task.description or "",
        task.source_cell_value or "",
        task.title or "",
        task.comment or "",
        task.status_label(),
        task.work_point.point_number if task.work_point else "",
        task.work_point.display_name if task.work_point else "",
        " ".join(categories),
    ]
    return " ".join(str(part or "") for part in parts).lower().replace("ё", "е")


def _all_project_tasks(project_id: int) -> list[Task]:
    return (
        Task.query.options(
            selectinload(Task.apartment),
            selectinload(Task.work_point).selectinload(WorkPoint.categories),
            selectinload(Task.glass_measurement).selectinload(GlassMeasurement.items),
        )
        .join(Apartment)
        .join(WorkPoint)
        .filter(Task.project_id == project_id)
        .order_by(Task.is_done.asc(), Apartment.premise_type.asc(), Apartment.building.asc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc(), WorkPoint.point_number.asc(), Task.id.asc())
        .limit(3000)
        .all()
    )


def _glass_tasks(project_id: int) -> list[Task]:
    # В разделе «Замеры» показываем все замечания CRM,
    # включая выполненные/вычеркнутые. Статус замера живет отдельно.
    return _all_project_tasks(project_id)


def _glass_point_options(project_id: int) -> list[dict[str, str]]:
    points = (
        WorkPoint.query.join(Task)
        .filter(Task.project_id == project_id)
        .distinct()
        .order_by(WorkPoint.point_number.asc(), WorkPoint.original_column_name.asc())
        .all()
    )
    return [
        {"number": str(point.point_number or ""), "label": f"{point.point_number} — {point.display_name}"}
        for point in points
        if str(point.point_number or "").strip()
    ]


def _get_or_create_glass_measurement(task: Task, status: str = GLASS_STATUS_MEASURE_NEEDED) -> GlassMeasurement:
    measurement = task.glass_measurement
    if measurement is None:
        measurement = GlassMeasurement(
            project_id=task.project_id,
            apartment_id=task.apartment_id,
            task_id=task.id,
            status=status,
            quantity=1,
        )
        db.session.add(measurement)
        db.session.flush()
    elif status and (measurement.status in (None, "", GLASS_STATUS_NONE, "not_ordered")):
        measurement.status = status
    if not measurement.apartment_id:
        measurement.apartment_id = task.apartment_id
    return measurement


def _measurement_status(measurement: GlassMeasurement | None) -> str:
    if measurement is None:
        return GLASS_STATUS_NONE
    return GLASS_STATUS_MEASURE_NEEDED if measurement.status == "not_ordered" else (measurement.status or GLASS_STATUS_NONE)


def _filter_glass_rows(tasks: list[Task], q: str = "", status: str = "", point: str = "") -> list[dict[str, object]]:
    search_mode, search_value = detect_search_mode(q)
    needle = search_value.strip().lower().replace("ё", "е")
    rows = []
    for task in tasks:
        measurement = task.glass_measurement
        current_status = _measurement_status(measurement)
        if status and current_status != status:
            continue
        if point and (not task.work_point or str(task.work_point.point_number).strip() != point):
            continue
        if needle:
            if search_mode in {"premise_number", "premise_number_or_building", "commercial_pair", "construction_number"}:
                if not premise_matches_search(task.apartment, search_mode, search_value):
                    continue
            elif needle not in _task_search_blob(task):
                continue
        rows.append({
            "task": task,
            "measurement": measurement,
            "items": _glass_item_rows(measurement),
            "status": current_status,
            "status_label": GLASS_STATUS_LABELS.get(current_status, current_status),
        })
    return sorted(rows, key=lambda row: _task_apartment_sort_value(row["task"]))


@bp.route("/glass")
@bp.route("/glass-measurements")
@login_required
def glass_measurements():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    tab = (request.args.get("tab") or "all").strip()
    if tab not in {"all", "order", "ordered"}:
        tab = "all"
    q = (request.args.get("q") or "").strip()
    point = (request.args.get("point") or "").strip()
    tasks = _glass_tasks(project.id)
    rows = _filter_glass_rows(tasks, q=q, point=point)
    order_rows = _filter_glass_rows(tasks, status=GLASS_STATUS_MEASURE_NEEDED)
    ordered_rows = [
        row for row in _filter_glass_rows(tasks)
        if row["status"] in {GLASS_STATUS_ORDERED, GLASS_STATUS_REPLACED}
    ]
    order_rows.sort(key=lambda row: _task_apartment_sort_value(row["task"]))
    ordered_rows.sort(key=lambda row: _task_apartment_sort_value(row["task"]))
    return render_template(
        "glass_measurements.html",
        project=project,
        rows=rows,
        order_rows=order_rows,
        ordered_rows=ordered_rows,
        tab=tab,
        q=q,
        status_labels=GLASS_STATUS_LABELS,
        glass_item_types=GLASS_ITEM_TYPES,
        glass_point_options=_glass_point_options(project.id),
        selected_point=point,
        today=date.today(),
    )


@bp.route("/glass/<int:task_id>/need-measure", methods=["POST"])
@login_required
def glass_need_measure(task_id: int):
    if current_user.role == "viewer":
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    measurement = _get_or_create_glass_measurement(task, status=GLASS_STATUS_MEASURE_NEEDED)
    measurement.status = GLASS_STATUS_MEASURE_NEEDED
    if not measurement.apartment_id:
        measurement.apartment_id = task.apartment_id
    db.session.commit()
    flash("Замечание перенесено во вкладку «Заказать»", "success")
    return redirect(url_for("main.glass_measurements", tab="order"))


@bp.route("/glass/<int:task_id>/save", methods=["POST"])
@login_required
def glass_measurement_save(task_id: int):
    if current_user.role == "viewer":
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    measurement = _get_or_create_glass_measurement(task, status=GLASS_STATUS_MEASURE_NEEDED)

    item_types = request.form.getlist("item_type[]") or request.form.getlist("item_type")
    sizes = request.form.getlist("size[]") or request.form.getlist("size")
    comments = request.form.getlist("item_comment[]") or request.form.getlist("item_comment")
    quantities = request.form.getlist("quantity[]") or request.form.getlist("quantity")
    max_len = max(len(item_types), len(sizes), len(comments), len(quantities), 1)

    def _size_dimensions(size_text: str) -> tuple[float, float]:
        import re
        numbers = re.findall(r"\d+(?:[,.]\d+)?", size_text or "")
        if len(numbers) >= 2:
            return float(numbers[0].replace(",", ".")), float(numbers[1].replace(",", "."))
        return 0.0, 0.0

    parsed_items: list[dict[str, object]] = []
    for index in range(max_len):
        item_type = (item_types[index] if index < len(item_types) else "Стеклопакет").strip() or "Стеклопакет"
        if item_type not in GLASS_ITEM_TYPES:
            item_type = "Стеклопакет"
        size_text = (sizes[index] if index < len(sizes) else "").strip()
        item_comment = (comments[index] if index < len(comments) else "").strip()
        quantity = _parse_quantity(quantities[index] if index < len(quantities) else None) or 1
        if not size_text and not item_comment:
            continue
        if not size_text:
            flash("В каждой добавленной позиции укажите размер", "warning")
            return redirect(url_for("main.glass_measurements", tab="order"))
        width, height = _size_dimensions(size_text)
        display_size = size_text
        if item_comment:
            display_size = f"{size_text} — {item_comment}"
        parsed_items.append({
            "item_type": item_type,
            "width": width,
            "height": height,
            "quantity": int(quantity) if float(quantity).is_integer() else int(round(quantity)),
            "size": display_size,
        })

    if not parsed_items:
        flash("Добавьте хотя бы один размер", "warning")
        return redirect(url_for("main.glass_measurements", tab="order"))

    measurement.items.clear()
    for item_data in parsed_items:
        measurement.items.append(GlassMeasurementItem(**item_data))

    first_item = parsed_items[0]
    measurement.width = first_item["width"]
    measurement.height = first_item["height"]
    measurement.quantity = first_item["quantity"]
    measurement.glass_type = first_item["item_type"]
    measurement.comment = (request.form.get("comment") or "").strip() or None
    measurement.measured_at = parse_date(request.form.get("measured_at")) or date.today()
    measurement.size = first_item["size"]
    measurement.status = GLASS_STATUS_ORDERED
    measurement.ordered_at = parse_date(request.form.get("ordered_at")) or date.today()
    if not measurement.apartment_id:
        measurement.apartment_id = task.apartment_id
    db.session.commit()
    flash("Размеры внесены. Позиция перемещена во вкладку «Заказано»", "success")
    return redirect(url_for("main.glass_measurements", tab="ordered"))


@bp.route("/glass/<int:measurement_id>/status", methods=["POST"])
@login_required
def glass_status_update(measurement_id: int):
    if current_user.role == "viewer":
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    measurement = (
        GlassMeasurement.query.options(selectinload(GlassMeasurement.task))
        .filter(GlassMeasurement.id == measurement_id, GlassMeasurement.project_id == project.id)
        .first()
        or abort(404)
    )
    next_status = (request.form.get("status") or "").strip()
    status_date = parse_date(request.form.get("status_date")) or date.today()
    if next_status not in {GLASS_STATUS_ORDERED, GLASS_STATUS_REPLACED}:
        flash("Некорректный статус стеклопакета", "warning")
        return redirect(url_for("main.glass_measurements", tab="ordered"))
    measurement.status = next_status
    if next_status == GLASS_STATUS_ORDERED:
        if not measurement.ordered_at:
            measurement.ordered_at = status_date
        measurement.replaced_at = None
    else:
        measurement.replaced_at = status_date
    db.session.commit()
    flash("Статус стеклопакета обновлён", "success")
    return redirect(url_for("main.glass_measurements", tab="ordered"))


@bp.route("/glass/order/export")
@login_required
def glass_order_export():
    if not can_export(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))

    rows = [
        row for row in _filter_glass_rows(_glass_tasks(project.id))
        if row["status"] in {GLASS_STATUS_ORDERED, GLASS_STATUS_REPLACED}
    ]
    rows.sort(key=lambda row: _task_apartment_sort_value(row["task"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "Заказано"
    ws.append([
        "Помещение",
        "Замечание",
        "Тип",
        "Размер / комментарий",
        "Количество",
        "Дата заказа",
        "Статус",
        "Заявка материалов",
    ])

    for row in rows:
        task = row["task"]
        measurement = row["measurement"]
        linked_request = None
        if measurement and measurement.material_request_item and measurement.material_request_item.request:
            linked_request = measurement.material_request_item.request
        items = row.get("items") or []
        if not items:
            items = [{
                "item_type": getattr(measurement, "glass_type", "") or "",
                "size_label": measurement.size_label() if measurement else "",
                "quantity": getattr(measurement, "quantity", "") or "",
            }]
        for item in items:
            ws.append([
                task.apartment.label() if task.apartment else "",
                task.description or task.source_cell_value or "",
                item.get("item_type") or "",
                item.get("size_label") or item.get("title_label") or "",
                item.get("quantity") or "",
                measurement.ordered_at.strftime("%d.%m.%Y") if measurement and measurement.ordered_at else "",
                GLASS_STATUS_LABELS.get(measurement.status, measurement.status) if measurement else "",
                (linked_request.title or f"Заявка №{linked_request.id}") if linked_request else "",
            ])

    _style_excel_header(ws)
    filename = f"{project.name}_замеры_заказано_{date.today().strftime('%Y-%m-%d')}.xlsx".replace("/", "-")
    return _make_excel_response(wb, filename)


@bp.route("/glass/ordered/create-material-request", methods=["POST"])
@login_required
def glass_create_material_request():
    if current_user.role == "viewer":
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    selected_ids = []
    for raw_id in request.form.getlist("measurement_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            pass
    if not selected_ids:
        flash("Выберите хотя бы один стеклопакет", "warning")
        return redirect(url_for("main.glass_measurements", tab="ordered"))
    measurements = (
        GlassMeasurement.query.options(
            selectinload(GlassMeasurement.task).selectinload(Task.apartment),
            selectinload(GlassMeasurement.items),
            selectinload(GlassMeasurement.material_request_item).selectinload(MaterialRequestItem.request),
        )
        .filter(GlassMeasurement.project_id == project.id, GlassMeasurement.id.in_(selected_ids))
        .all()
    )
    if len(measurements) != len(set(selected_ids)):
        flash("Часть выбранных стеклопакетов не найдена", "warning")
        return redirect(url_for("main.glass_measurements", tab="ordered"))
    already_requested = [m for m in measurements if m.material_request_item_id]
    if already_requested:
        flash("Выбранные стеклопакеты уже внесены в заявку. Повторную заявку создать нельзя", "warning")
        return redirect(url_for("main.glass_measurements", tab="ordered"))
    without_size = [m for m in measurements if not _glass_item_rows(m)]
    if without_size:
        flash("У выбранных позиций должен быть указан хотя бы один размер", "warning")
        return redirect(url_for("main.glass_measurements", tab="ordered"))
    title_parts = []
    material_request = MaterialRequest(
        project_id=project.id,
        author_id=current_user.id,
        request_date=date.today(),
        title="",
        comment="Заявка создана из раздела «Замеры»",
    )
    for measurement in measurements:
        task = measurement.task
        apt = task.apartment.label() if task and task.apartment else ""
        first_item_for_measurement = None
        for item_row in _glass_item_rows(measurement):
            title = str(item_row.get("title_label") or "").strip()
            if title:
                title_parts.append(title)
            request_item = MaterialRequestItem(
                name=f"{title} {apt}".strip(),
                quantity=item_row.get("quantity") or 1,
                unit="шт",
            )
            material_request.items.append(request_item)
            if first_item_for_measurement is None:
                first_item_for_measurement = request_item
        if first_item_for_measurement is not None:
            measurement.material_request_item = first_item_for_measurement
    title_sizes = ", ".join(title_parts[:4])
    if len(title_parts) > 4:
        title_sizes += f" и ещё {len(title_parts) - 4}"
    material_request.title = f"Заявка: {title_sizes}".strip() or "Заявка из замеров"
    db.session.add(material_request)
    db.session.commit()
    flash("Заявка на стеклопакеты создана", "success")
    return redirect(url_for("main.material_request_detail", request_id=material_request.id))


@bp.route("/glass/delete", methods=["POST"])
@login_required
def glass_measurements_delete():
    if current_user.role == "viewer":
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    scope = (request.form.get("scope") or "ordered").strip()
    if scope == "order":
        statuses = [GLASS_STATUS_MEASURE_NEEDED]
        redirect_tab = "order"
    else:
        statuses = [GLASS_STATUS_ORDERED, GLASS_STATUS_REPLACED]
        redirect_tab = "ordered"

    selected_ids = []
    for raw_id in request.form.getlist("measurement_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            pass

    query = GlassMeasurement.query.filter(
        GlassMeasurement.project_id == project.id,
        GlassMeasurement.status.in_(statuses),
    )
    if request.form.get("delete_all") != "1":
        if not selected_ids:
            flash("Выберите хотя бы одну позицию для удаления", "warning")
            return redirect(url_for("main.glass_measurements", tab=redirect_tab))
        query = query.filter(GlassMeasurement.id.in_(selected_ids))

    measurements = query.all()
    for measurement in measurements:
        _record_simple_deletion(
            "glass_measurement_delete",
            "glass_measurement",
            measurement,
            f"Стеклопакет #{measurement.id}",
            f"Удалена позиция стеклопакета: {measurement.size_label() or 'без размера'}.",
            project_id=project.id,
            extra={
                "task_id": measurement.task_id,
                "apartment_id": measurement.apartment_id,
                "items": [_snapshot_model(item) for item in measurement.items],
            },
        )
        db.session.delete(measurement)
    db.session.commit()
    flash(f"Удалено позиций: {len(measurements)}", "success")
    return redirect(url_for("main.glass_measurements", tab=redirect_tab))


# Старые ссылки на отдельную страницу заказа оставлены как безопасный редирект.
@bp.route("/glass/order", methods=["GET", "POST"])
@login_required
def glass_order():
    return redirect(url_for("main.glass_measurements", tab="ordered"))


@bp.route("/materials")
@login_required
def materials():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))

    active_tab = request.args.get("tab", "balance")
    allowed_tabs = {"balance", "requests", "writeoff", "history", "task"}
    if active_tab not in allowed_tabs:
        active_tab = "balance"

    material_requests = (
        MaterialRequest.query.options(selectinload(MaterialRequest.items), selectinload(MaterialRequest.author))
        .filter(MaterialRequest.project_id == project.id)
        .order_by(MaterialRequest.request_date.desc(), MaterialRequest.id.desc())
        .all()
    )
    balance_rows = _material_balance_rows(project.id)
    balance_options = _balance_options(project.id)
    writeoffs = (
        MaterialWriteOff.query.options(
            selectinload(MaterialWriteOff.items),
            selectinload(MaterialWriteOff.tasks).selectinload(Task.apartment),
            selectinload(MaterialWriteOff.tasks).selectinload(Task.work_point),
        )
        .filter(MaterialWriteOff.project_id == project.id)
        .order_by(MaterialWriteOff.writeoff_date.desc(), MaterialWriteOff.id.desc())
        .all()
    )
    writeoffs.sort(key=_writeoff_sort_value)
    writeoff_tasks = _material_task_options(project.id, request.args) if active_tab == "writeoff" else []
    low_stock_count = sum(1 for row in balance_rows if 0 < float(row.get("balance") or 0) <= 5)
    return render_template(
        "materials.html",
        project=project,
        active_tab=active_tab,
        material_requests=material_requests,
        balance_rows=balance_rows,
        balance_options=balance_options,
        writeoffs=writeoffs,
        writeoff_tasks=writeoff_tasks,
        low_stock_count=low_stock_count,
        can_edit_materials=_can_edit_materials(),
        args=request.args,
        today=date.today(),
    )


@bp.route("/materials/balance/delete", methods=["POST"])
@login_required
def material_balance_delete():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)

    selected_keys = []
    if request.form.get("delete_all") == "1":
        selected_keys = [str(row.get("key") or "") for row in _material_balance_rows(project.id)]
    else:
        selected_keys = [str(value or "").strip() for value in request.form.getlist("material_keys") if str(value or "").strip()]

    selected_pairs = {_normalize_material_identity(*parsed) for parsed in (_split_material_key(value) for value in selected_keys) if parsed}
    if not selected_pairs:
        flash("Выберите хотя бы одну позицию баланса", "warning")
        return redirect(url_for("main.materials", tab="balance"))

    request_items = (
        MaterialRequestItem.query.join(MaterialRequest)
        .filter(MaterialRequest.project_id == project.id)
        .all()
    )
    writeoff_items = (
        MaterialWriteOffItem.query.join(MaterialWriteOff)
        .filter(MaterialWriteOff.project_id == project.id)
        .all()
    )

    removed_items = 0
    touched_requests: set[MaterialRequest] = set()
    touched_writeoffs: set[MaterialWriteOff] = set()

    for item in request_items:
        if _normalize_material_identity(item.name, item.unit) not in selected_pairs:
            continue
        GlassMeasurement.query.filter(GlassMeasurement.material_request_item_id == item.id).update(
            {"material_request_item_id": None},
            synchronize_session=False,
        )
        touched_requests.add(item.request)
        db.session.delete(item)
        removed_items += 1

    for item in writeoff_items:
        if _normalize_material_identity(item.name, item.unit) not in selected_pairs:
            continue
        touched_writeoffs.add(item.writeoff)
        db.session.delete(item)
        removed_items += 1

    db.session.flush()
    for material_request in list(touched_requests):
        if material_request is not None and not material_request.items:
            _record_simple_deletion(
                "material_request_delete_empty_after_balance",
                "material_request",
                material_request,
                material_request.title or f"Заявка #{material_request.id}",
                "Заявка удалена автоматически после удаления всех строк баланса.",
                project_id=project.id,
                extra={"items": [_snapshot_model(item) for item in material_request.items]},
            )
            db.session.delete(material_request)
    for writeoff in list(touched_writeoffs):
        if writeoff is not None and not writeoff.items:
            _record_simple_deletion(
                "material_writeoff_delete_empty_after_balance",
                "material_writeoff",
                writeoff,
                f"Списание #{writeoff.id}",
                "Списание удалено автоматически после удаления всех строк баланса.",
                project_id=project.id,
                extra={"items": [_snapshot_model(item) for item in writeoff.items]},
            )
            writeoff.tasks.clear()
            db.session.delete(writeoff)

    _record_deletion_action(
        "material_balance_delete",
        "material_balance",
        None,
        "Удаление материалов из баланса",
        f"Удалены материалы из баланса: {len(selected_pairs)} поз.; затронуто строк: {removed_items}.",
        {
            "selected_pairs": sorted([{"name": name, "unit": unit} for name, unit in selected_pairs], key=lambda row: (row["name"], row["unit"])),
            "removed_items": removed_items,
        },
        project_id=project.id,
    )
    db.session.commit()
    flash(f"Удалено позиций баланса: {len(selected_pairs)}. Затронуто строк материалов: {removed_items}", "success")
    return redirect(url_for("main.materials", tab="balance"))


@bp.route("/materials/request/<int:request_id>")
@login_required
def material_request_detail(request_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    material_request = (
        MaterialRequest.query.options(selectinload(MaterialRequest.items), selectinload(MaterialRequest.author))
        .filter(MaterialRequest.id == request_id, MaterialRequest.project_id == project.id)
        .first()
    ) or abort(404)
    max_rows = len(material_request.items) + 1
    return render_template(
        "material_request_detail.html",
        project=project,
        material_request=material_request,
        can_edit_materials=_can_edit_materials(),
        max_rows=max_rows,
        today=date.today(),
    )


@bp.route("/materials/request/<int:request_id>/rename", methods=["POST"])
@login_required
def material_request_rename(request_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)
    material_request = (
        MaterialRequest.query.filter(MaterialRequest.id == request_id, MaterialRequest.project_id == project.id).first()
        or abort(404)
    )
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Название заявки не может быть пустым", "warning")
        return redirect(request.referrer or url_for("main.materials", tab="requests"))
    material_request.title = title
    db.session.commit()
    flash("Название заявки обновлено", "success")
    return redirect(request.referrer or url_for("main.materials", tab="requests"))


@bp.route("/materials/request/<int:request_id>/update", methods=["POST"])
@login_required
def material_request_update(request_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)
    material_request = (
        MaterialRequest.query.filter(MaterialRequest.id == request_id, MaterialRequest.project_id == project.id).first()
        or abort(404)
    )
    title = (request.form.get("title") or "").strip()
    request_date = parse_date(request.form.get("request_date"))
    if not title:
        flash("Название заявки не может быть пустым", "warning")
        return redirect(url_for("main.material_request_detail", request_id=request_id))
    if request_date is None:
        flash("Введите корректную дату заявки", "warning")
        return redirect(url_for("main.material_request_detail", request_id=request_id))
    try:
        rows = _read_material_rows_from_form(limit=50)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.material_request_detail", request_id=request_id))
    if not rows:
        flash("Добавьте хотя бы одну позицию материала", "warning")
        return redirect(url_for("main.material_request_detail", request_id=request_id))
    old_items = list(material_request.items)
    old_item_ids = [item.id for item in old_items if item.id]
    linked_measurements = (
        GlassMeasurement.query.filter(GlassMeasurement.material_request_item_id.in_(old_item_ids)).all()
        if old_item_ids
        else []
    )
    linked_by_old_item_id = {measurement.material_request_item_id: measurement for measurement in linked_measurements}
    for measurement in linked_measurements:
        measurement.material_request_item = None
    material_request.title = title
    material_request.request_date = request_date
    material_request.comment = (request.form.get("comment") or material_request.comment or "").strip() or None
    material_request.items.clear()
    for index, row in enumerate(rows):
        new_item = MaterialRequestItem(name=str(row["name"]), quantity=float(row["quantity"]), unit=str(row["unit"]))
        material_request.items.append(new_item)
        if index < len(old_items):
            linked_measurement = linked_by_old_item_id.get(old_items[index].id)
            if linked_measurement is not None:
                linked_measurement.material_request_item = new_item
    db.session.commit()
    flash("Заявка обновлена", "success")
    return redirect(url_for("main.material_request_detail", request_id=request_id))


@bp.route("/materials/request/<int:request_id>/delete", methods=["POST"])
@login_required
def material_request_delete(request_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)
    material_request = (
        MaterialRequest.query.filter(MaterialRequest.id == request_id, MaterialRequest.project_id == project.id).first()
        or abort(404)
    )
    item_ids = [item.id for item in material_request.items]
    if item_ids:
        GlassMeasurement.query.filter(GlassMeasurement.material_request_item_id.in_(item_ids)).update(
            {"material_request_item_id": None},
            synchronize_session=False,
        )
    _record_simple_deletion(
        "material_request_delete",
        "material_request",
        material_request,
        material_request.title or f"Заявка #{material_request.id}",
        f"Удалена заявка на материалы: {material_request.title or material_request.id}.",
        project_id=project.id,
        extra={"items": [_snapshot_model(item) for item in material_request.items]},
    )
    db.session.delete(material_request)
    db.session.commit()
    flash("Заявка удалена", "success")
    return redirect(url_for("main.materials", tab="requests"))


@bp.route("/materials/requests/delete", methods=["POST"])
@login_required
def material_requests_bulk_delete():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)

    selected_ids = []
    for raw_id in request.form.getlist("request_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            pass

    query = MaterialRequest.query.options(selectinload(MaterialRequest.items)).filter(MaterialRequest.project_id == project.id)
    if request.form.get("delete_all") != "1":
        if not selected_ids:
            flash("Выберите хотя бы одну заявку", "warning")
            return redirect(url_for("main.materials", tab="requests"))
        query = query.filter(MaterialRequest.id.in_(selected_ids))

    requests_to_delete = query.all()
    item_ids = [item.id for material_request in requests_to_delete for item in material_request.items if item.id]
    if item_ids:
        GlassMeasurement.query.filter(GlassMeasurement.material_request_item_id.in_(item_ids)).update(
            {"material_request_item_id": None},
            synchronize_session=False,
        )
    for material_request in requests_to_delete:
        _record_simple_deletion(
            "material_request_delete",
            "material_request",
            material_request,
            material_request.title or f"Заявка #{material_request.id}",
            f"Удалена заявка на материалы: {material_request.title or material_request.id}.",
            project_id=project.id,
            extra={"items": [_snapshot_model(item) for item in material_request.items]},
        )
        db.session.delete(material_request)
    db.session.commit()
    flash(f"Удалено заявок: {len(requests_to_delete)}", "success")
    return redirect(url_for("main.materials", tab="requests"))


@bp.route("/materials/request/<int:request_id>/export")
@login_required
def material_request_export(request_id: int):
    if not can_export(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    material_request = (
        MaterialRequest.query.options(selectinload(MaterialRequest.items))
        .filter(MaterialRequest.id == request_id, MaterialRequest.project_id == project.id)
        .first()
        or abort(404)
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Заявка"
    ws.append(["Дата", "Название заявки", "Наименование", "Количество", "Ед. измерения"])
    request_title = material_request.title or material_request.comment or f"Заявка №{material_request.id}"
    for item in material_request.items:
        ws.append([
            material_request.request_date.strftime("%d.%m.%Y") if material_request.request_date else "",
            request_title,
            item.name,
            fmt_quantity(item.quantity),
            item.unit,
        ])
    if not material_request.items:
        ws.append([material_request.request_date.strftime("%d.%m.%Y") if material_request.request_date else "", request_title, "", "", ""])
    _style_excel_header(ws)
    filename = f"{project.name}_{request_title}_{date.today().strftime('%Y-%m-%d')}.xlsx".replace("/", "-")
    return _make_excel_response(wb, filename)


@bp.route("/materials/write-off/<int:writeoff_id>/edit", methods=["GET", "POST"])
@login_required
def material_writeoff_edit(writeoff_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)
    writeoff = (
        MaterialWriteOff.query.options(selectinload(MaterialWriteOff.items), selectinload(MaterialWriteOff.tasks).selectinload(Task.apartment))
        .filter(MaterialWriteOff.id == writeoff_id, MaterialWriteOff.project_id == project.id)
        .first()
        or abort(404)
    )
    if request.method == "POST":
        writeoff_date = parse_date(request.form.get("writeoff_date"))
        if writeoff_date is None:
            flash("Введите корректную дату списания", "warning")
            return redirect(url_for("main.material_writeoff_edit", writeoff_id=writeoff.id))
        try:
            rows = _read_material_rows_from_form(limit=20)
        except ValueError as exc:
            flash(str(exc), "danger")
            rows = []
        if not rows:
            flash("Добавьте хотя бы одну позицию материала", "warning")
            return redirect(url_for("main.material_writeoff_edit", writeoff_id=writeoff.id))
        writeoff.writeoff_date = writeoff_date
        writeoff.comment = None
        writeoff.items.clear()
        for row in rows:
            writeoff.items.append(MaterialWriteOffItem(name=str(row["name"]), quantity=float(row["quantity"]), unit=str(row["unit"])))
        db.session.commit()
        flash("Списание обновлено", "success")
        return redirect(url_for("main.materials", tab="history"))
    return render_template("material_writeoff_edit.html", project=project, writeoff=writeoff, max_rows=max(10, len(writeoff.items) + 3))


@bp.route("/materials/write-off/<int:writeoff_id>/delete", methods=["POST"])
@login_required
def material_writeoff_delete(writeoff_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)
    writeoff = MaterialWriteOff.query.filter(MaterialWriteOff.id == writeoff_id, MaterialWriteOff.project_id == project.id).first() or abort(404)
    _record_simple_deletion(
        "material_writeoff_delete",
        "material_writeoff",
        writeoff,
        f"Списание #{writeoff.id}",
        f"Удалено списание материалов от {writeoff.writeoff_date.strftime('%d.%m.%Y') if writeoff.writeoff_date else 'без даты'}.",
        project_id=project.id,
        extra={
            "items": [_snapshot_model(item) for item in writeoff.items],
            "task_ids": [task.id for task in writeoff.tasks],
        },
    )
    writeoff.tasks.clear()
    db.session.delete(writeoff)
    db.session.commit()
    flash("Списание удалено", "success")
    return redirect(url_for("main.materials", tab="history"))


@bp.route("/materials/write-offs/delete", methods=["POST"])
@login_required
def material_writeoffs_bulk_delete():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)

    selected_ids = []
    for raw_id in request.form.getlist("writeoff_ids"):
        try:
            selected_ids.append(int(raw_id))
        except (TypeError, ValueError):
            pass

    query = MaterialWriteOff.query.filter(MaterialWriteOff.project_id == project.id)
    if request.form.get("delete_all") != "1":
        if not selected_ids:
            flash("Выберите хотя бы одно списание", "warning")
            return redirect(url_for("main.materials", tab="history"))
        query = query.filter(MaterialWriteOff.id.in_(selected_ids))

    writeoffs_to_delete = query.all()
    for writeoff in writeoffs_to_delete:
        _record_simple_deletion(
            "material_writeoff_delete",
            "material_writeoff",
            writeoff,
            f"Списание #{writeoff.id}",
            f"Удалено списание материалов от {writeoff.writeoff_date.strftime('%d.%m.%Y') if writeoff.writeoff_date else 'без даты'}.",
            project_id=project.id,
            extra={
                "items": [_snapshot_model(item) for item in writeoff.items],
                "task_ids": [task.id for task in writeoff.tasks],
            },
        )
        writeoff.tasks.clear()
        db.session.delete(writeoff)
    db.session.commit()
    flash(f"Удалено списаний: {len(writeoffs_to_delete)}", "success")
    return redirect(url_for("main.materials", tab="history"))


def _make_excel_response(workbook: Workbook, download_name: str):
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _style_excel_header(ws):
    fill = PatternFill("solid", fgColor="EAF0F7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"
    for column_cells in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in column_cells)
        ws.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(max_len + 3, 14), 60)


@bp.route("/materials/expense/export")
@login_required
def material_expense_export():
    if not can_export(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    writeoffs = (
        MaterialWriteOff.query.options(
            selectinload(MaterialWriteOff.items),
            selectinload(MaterialWriteOff.tasks).selectinload(Task.apartment),
            selectinload(MaterialWriteOff.tasks).selectinload(Task.work_point),
        )
        .filter(MaterialWriteOff.project_id == project.id)
        .order_by(MaterialWriteOff.writeoff_date.desc(), MaterialWriteOff.id.desc())
        .all()
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "Расход материала"
    ws.append(["Дата", "№", "Перечень замечаний", "Потраченный материал"])
    for writeoff in writeoffs:
        material_lines = [f"{item.name} — {fmt_quantity(item.quantity)} {item.unit}" for item in writeoff.items]
        tasks = list(writeoff.tasks)
        if not tasks:
            tasks = [None]
        start_row = ws.max_row + 1
        for task in tasks:
            premise = task.apartment.label() if task and task.apartment else ""
            remark = (task.description or task.source_cell_value or "").strip() if task else ""
            ws.append([
                writeoff.writeoff_date.strftime("%d.%m.%Y") if writeoff.writeoff_date else "",
                premise or "—",
                remark,
                "\n".join(material_lines),
            ])
        end_row = ws.max_row
        if end_row > start_row:
            ws.merge_cells(start_row=start_row, start_column=4, end_row=end_row, end_column=4)
    _style_excel_header(ws)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell, MergedCell):
                continue
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    filename = f"{project.name}_расход_материала_{date.today().strftime('%Y-%m-%d')}.xlsx"
    return _make_excel_response(wb, filename)


@bp.route("/materials/request/new", methods=["GET", "POST"])
@login_required
def material_request_new():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)

    if request.method == "POST":
        try:
            rows = _read_material_rows_from_form(limit=10)
        except ValueError as exc:
            flash(str(exc), "danger")
            rows = []
        if not rows:
            flash("Добавьте хотя бы одну позицию материала", "warning")
        else:
            request_date = parse_date(request.form.get("request_date")) or date.today()
            material_request = MaterialRequest(project_id=project.id, author_id=current_user.id, request_date=request_date, title=(request.form.get("title") or "").strip() or None)
            for row in rows:
                material_request.items.append(
                    MaterialRequestItem(
                        name=str(row["name"]),
                        quantity=float(row["quantity"]),
                        unit=str(row["unit"]),
                    )
                )
            db.session.add(material_request)
            db.session.commit()
            flash("Заявка на материал добавлена", "success")
            return redirect(url_for("main.materials", tab="requests"))

    return render_template("material_request_form.html", project=project, max_rows=10, today=date.today())


@bp.route("/materials/write-off", methods=["GET", "POST"])
@login_required
def material_writeoff_new():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)

    tasks = _material_task_options(project.id, request.args)
    finishing_types = [
        x[0]
        for x in db.session.query(distinct(Apartment.finishing_type))
        .filter(Apartment.project_id == project.id, Apartment.finishing_type.isnot(None))
        .all()
    ]
    balance_rows = _material_balance_rows(project.id)
    balance_options = _balance_options(project.id)

    if request.method == "POST":
        selected_task_ids = []
        for raw_id in request.form.getlist("task_ids"):
            try:
                selected_task_ids.append(int(raw_id))
            except (TypeError, ValueError):
                pass
        selected_tasks = (
            Task.query.options(selectinload(Task.apartment), selectinload(Task.work_point))
            .filter(Task.project_id == project.id, Task.id.in_(selected_task_ids or [-1]))
            .all()
        )
        order_map = {task_id: index for index, task_id in enumerate(selected_task_ids)}
        selected_tasks.sort(key=lambda task: order_map.get(task.id, 10**9))
        try:
            row = _read_balance_writeoff_row(project.id)
        except ValueError as exc:
            flash(str(exc), "danger")
            row = None
        if not selected_tasks:
            flash("Выберите одно или несколько замечаний", "warning")
        elif row is None:
            pass
        else:
            writeoff_date = parse_date(request.form.get("writeoff_date")) or date.today()
            if request.form.get("action") == "distribute":
                allocations = _distribute_material_quantity(selected_tasks, float(row["quantity"]))
                for task in selected_tasks:
                    quantity = allocations.get(task.id)
                    if not quantity:
                        continue
                    writeoff = MaterialWriteOff(project_id=project.id, author_id=current_user.id, writeoff_date=writeoff_date, comment="auto_distributed")
                    writeoff.tasks = [task]
                    writeoff.items.append(
                        MaterialWriteOffItem(
                            name=str(row["name"]),
                            quantity=float(quantity),
                            unit=str(row["unit"]),
                        )
                    )
                    db.session.add(writeoff)
                db.session.commit()
                flash(f"Материал распределён между замечаниями: {len(selected_tasks)}", "success")
                return redirect(url_for("main.materials", tab="history"))
            writeoff = MaterialWriteOff(project_id=project.id, author_id=current_user.id, writeoff_date=writeoff_date, comment=None)
            writeoff.tasks = selected_tasks
            writeoff.items.append(
                MaterialWriteOffItem(
                    name=str(row["name"]),
                    quantity=float(row["quantity"]),
                    unit=str(row["unit"]),
                )
            )
            db.session.add(writeoff)
            db.session.commit()
            flash("Материал списан на выбранные замечания", "success")
            return redirect(url_for("main.materials", tab="history"))

    return render_template(
        "material_writeoff_form.html",
        project=project,
        tasks=tasks,
        balance_rows=balance_rows,
        balance_options=balance_options,
        max_rows=1,
        points=_contractor_point_options(),
        finishing_types=finishing_types,
        args=request.args,
        today=date.today(),
    )


def _project_apartment_options(project_id: int) -> list[Apartment]:
    grouped: dict[str, list[Apartment]] = {}
    for apartment in Apartment.query.filter(Apartment.project_id == project_id).all():
        if _is_visible_apartment_row(apartment):
            grouped.setdefault(_apartment_group_key(apartment), []).append(apartment)
    apartments = [_pick_apartment_representative(group) for group in grouped.values()]
    return sorted(
        apartments,
        key=lambda apartment: (apartment.premise_type == "commercial", _apartment_number_sort_value(apartment.apartment_number or apartment.construction_number), apartment.building or ""),
    )


def _project_work_point_options() -> list[WorkPoint]:
    return (
        WorkPoint.query.filter(WorkPoint.point_number.in_(CONTRACTOR_POINT_LABELS.keys()))
        .order_by(WorkPoint.point_number.asc())
        .all()
    )


@bp.route("/tasks/new", methods=["GET", "POST"])
@login_required
def task_new():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if current_user.role == "viewer":
        abort(403)

    apartments = _project_apartment_options(project.id)
    default_point = WorkPoint.query.filter_by(point_number="22").order_by(WorkPoint.id.asc()).first()
    if default_point is None:
        default_point = WorkPoint(point_number="22", short_name="Прочее", original_column_name="Прочее", source_sheet_name="manual", is_active=True)
        db.session.add(default_point)
        db.session.flush()
    points = [default_point]

    if request.method == "POST":
        apartment_id = request.form.get("apartment_id", type=int)
        text = (request.form.get("description") or "").strip()
        apartment = db.session.get(Apartment, apartment_id) if apartment_id else None
        work_point = default_point

        if not apartment or apartment.project_id != project.id:
            flash("Выберите квартиру / коммерцию", "warning")
        elif not text:
            flash("Введите перечень работ", "warning")
        else:
            source_uid = build_task_uid(
                project.name,
                apartment.construction_number or "",
                apartment.apartment_number or "",
                work_point.point_number,
                work_point.display_name,
                text,
            )
            if Task.query.filter_by(source_uid=source_uid).first():
                source_uid = stable_hash([source_uid, "manual", datetime.utcnow().isoformat()])
            task = Task(
                source_uid=source_uid,
                project_id=project.id,
                apartment_id=apartment.id,
                work_point_id=work_point.id,
                title=work_point.display_name,
                description=text,
                source_cell_value=text,
                source_sheet_name="manual",
                status=STATUS_DONE,
                is_done=True,
                completed_date=datetime.utcnow(),
                manually_edited=True,
                last_seen_at=datetime.utcnow(),
                source_hash=stable_hash([text]),
            )
            db.session.add(task)
            db.session.commit()
            flash("Замечание добавлено со статусом выполнено", "success")
            return redirect(url_for("main.task_list", status="done"))

    return render_template("task_form.html", project=project, apartments=apartments, points=points)


@bp.route("/materials/task/new", methods=["GET", "POST"])
@login_required
def material_manual_task_new():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if not _can_edit_materials():
        abort(403)

    balance_options = _balance_options(project.id)
    if request.method == "POST":
        task_name = (request.form.get("task_name") or "").strip()
        try:
            row = _read_balance_writeoff_row(project.id)
        except ValueError as exc:
            flash(str(exc), "danger")
            row = None
        if not task_name:
            flash("Введите перечень работ", "warning")
        elif row is None:
            pass
        else:
            writeoff = MaterialWriteOff(
                project_id=project.id,
                author_id=current_user.id,
                writeoff_date=parse_date(request.form.get("writeoff_date")) or date.today(),
                comment=task_name,
            )
            writeoff.items.append(MaterialWriteOffItem(name=str(row["name"]), quantity=float(row["quantity"]), unit=str(row["unit"])))
            db.session.add(writeoff)
            db.session.commit()
            flash("Задача добавлена в расход материалов", "success")
            return redirect(url_for("main.materials", tab="history"))

    return render_template("material_task_form.html", project=project, balance_options=balance_options, today=date.today())


def _task_list_response(contractor_page: bool = False):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    ensure_default_categories()
    category_id = request.args.get("category_id", type=int)
    categories = WorkCategory.query.filter_by(is_active=True).order_by(WorkCategory.sort_order.asc()).all()
    all_cat = next((category for category in categories if (category.name or "").strip().lower() == "все"), None)
    if contractor_page:
        category_id = all_cat.id if all_cat else None
    elif not category_id and categories:
        category_id = all_cat.id if all_cat else categories[0].id
    section_id = request.args.get("section_id", type=int)
    if section_id and not contractor_page:
        category_id = section_id

    query_args = request.args.to_dict()
    if contractor_page:
        # В разделе "Подрядчики" показываем ту же таблицу замечаний, но группируем/фильтруем по пунктам 10-22.
        # Не принудительно фильтруем по статусу "Подрядчик", иначе вкладка пустая до ручной разметки задач.
        query_args["sort"] = "point"
    query = build_task_query(query_args, category_id=category_id, project_id=project.id)
    acceptance_status = request.args.get("acceptance_status")
    if acceptance_status == "accepted":
        query = query.filter(Apartment.is_app_mode.is_(True))
    elif acceptance_status == "waiting":
        query = query.filter(Apartment.is_app_mode.is_(False))
    if current_user.role in WORKER_ROLES:
        query = query.filter(Task.responsible_id == current_user.id)
    page = request.args.get("page", 1, type=int)
    pagination = query.options(selectinload(Task.glass_measurement)).paginate(page=page, per_page=50, error_out=False)
    active_category = next((category for category in categories if category.id == category_id), None)

    prev_args = request.args.to_dict()
    next_args = request.args.to_dict()
    if pagination.has_prev:
        prev_args["page"] = pagination.prev_num
    if pagination.has_next:
        next_args["page"] = pagination.next_num
    users = (
        User.query.filter(User.is_active.is_(True), (User.project_id == project.id) | (User.project_id.is_(None)))
        .order_by(User.full_name.asc())
        .all()
    )
    points = WorkPoint.query.filter_by(is_active=True).order_by(WorkPoint.point_number.asc()).all()
    finishing_types = [
        x[0]
        for x in db.session.query(distinct(Apartment.finishing_type))
        .filter(Apartment.project_id == project.id, Apartment.finishing_type.isnot(None))
        .all()
    ]
    premise_options = []
    seen_premise_ids = set()
    for task in pagination.items:
        apartment = task.apartment
        if not apartment or apartment.id in seen_premise_ids:
            continue
        seen_premise_ids.add(apartment.id)
        premise_options.append({"id": apartment.id, "label": apartment.label(), "finish": apartment.finishing_type or ""})
    return render_template(
        "task_list.html",
        tasks=pagination.items,
        pagination=pagination,
        categories=categories,
        active_category_id=category_id,
        users=users,
        points=points,
        finishing_types=finishing_types,
        args=request.args,
        active_category=active_category,
        contractor_page=contractor_page,
        list_endpoint="main.contractors_list" if contractor_page else "main.task_list",
        contractor_points=_contractor_point_options() if contractor_page else [],
        premise_options=premise_options,
        page_title="Подрядчики" if contractor_page else "Замечания",
        page_subtitle="Раздел для работы с подрядчиками объекта" if contractor_page else "Работа с замечаниями по выбранному объекту.",
        today=date.today(),
        prev_args=prev_args,
        next_args=next_args,
    )


def _apartment_number_sort_value(value: str | None):
    text = str(value or "").strip()
    if not text:
        return (1, 0, "")
    if text.isdigit():
        return (0, int(text), text)
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return (0, int(digits), text)
    return (1, 0, text.lower())


def _task_apartment_sort_value(task: Task):
    apartment = getattr(task, "apartment", None)
    done_rank = 1 if getattr(task, "is_done", False) else 0
    if not apartment:
        return (done_rank, 1, 1, (1, 0, ""), "", "", 0)
    return (
        done_rank,
        0,
        0 if (apartment.premise_type or "apartment") != "commercial" else 1,
        _apartment_number_sort_value(apartment.apartment_number or apartment.construction_number),
        str(apartment.building or "").strip().lower(),
        str(task.work_point.point_number if task.work_point else "").strip(),
        int(task.id or 0),
    )


def _writeoff_sort_value(writeoff: MaterialWriteOff):
    tasks = list(writeoff.tasks or [])
    if not tasks:
        return (1, (1, 0, ""), 0, 0)
    best_task = min(tasks, key=_task_apartment_sort_value)
    return (
        0,
        _task_apartment_sort_value(best_task),
        -int(writeoff.writeoff_date.toordinal() if writeoff.writeoff_date else 0),
        -int(writeoff.id or 0),
    )


def _apartment_identity_text(apartment: Apartment) -> str:
    return str(apartment.apartment_number or apartment.construction_number or "").strip()


def _clean_apartment_key(text: str) -> str:
    return " ".join(str(text or "").strip().lower().replace("ё", "е").split())


def _is_service_apartment_row(apartment: Apartment) -> bool:
    """Отсекает строки Excel вроде '1 корпус' и '1 подъезд', чтобы они не выглядели как квартиры."""
    text = _clean_apartment_key(_apartment_identity_text(apartment))
    if not text:
        return False
    service_words = ("корпус", "подъезд", "очеред", "секц", "итог", "дом")
    return any(word in text for word in service_words)


def _is_visible_apartment_row(apartment: Apartment) -> bool:
    text = _apartment_identity_text(apartment)
    return bool(text) and not _is_service_apartment_row(apartment)


def _apartment_group_key(apartment: Apartment) -> str:
    text = _clean_apartment_key(_apartment_identity_text(apartment))
    premise_type = apartment.premise_type or "apartment"
    if premise_type == "commercial":
        building = str(apartment.building or "").strip()
        source = str(apartment.source_row_id or "").strip()
        number = text or str(apartment.id)
        return f"{premise_type}:building:{building}:num:{number}:src:{source}"
    if not text:
        return f"{premise_type}:id:{apartment.id}"
    if text.isdigit():
        return f"{premise_type}:num:{int(text)}"
    return f"{premise_type}:num:{text}"


def _pick_apartment_representative(apartments: list[Apartment]) -> Apartment:
    def score(apartment: Apartment):
        return (
            1 if apartment.finishing_type else 0,
            1 if apartment.app_deadline_date else 0,
            1 if apartment.deadline_date else 0,
            len(apartment.tasks or []),
            -(apartment.id or 0),
        )

    return sorted(apartments, key=score, reverse=True)[0]


def _apartment_group_mode(apartments: list[Apartment]) -> str:
    if apartments and any(_is_unsold_apartment(apartment) for apartment in apartments):
        return "не продана"
    if any(apartment.is_app_mode for apartment in apartments):
        return "АПП"
    return "не принята"


def _is_unsold_apartment(apartment: Apartment) -> bool:
    return is_apartment_unsold(apartment)


def _apartment_mode(apartment: Apartment) -> str:
    if _is_unsold_apartment(apartment):
        return "не продана"
    return "АПП" if apartment.is_app_mode else "не принята"


def _task_point_number(task: Task) -> str:
    return str(task.work_point.point_number if task.work_point else "").strip()


def _task_point_name(task: Task) -> str:
    if not task.work_point:
        return ""
    return (task.work_point.display_name or "").lower()


def _is_wall_task(task: Task) -> bool:
    return _task_point_number(task) in WALL_POINT_NUMBERS or "стен" in _task_point_name(task)


def _auto_po_status(tasks: list[Task]) -> str:
    main_tasks = [
        task
        for task in tasks
        if not task.is_archived
        and not task.is_missing_in_latest_sync
        and _task_point_number(task) in MAIN_WORK_POINT_NUMBERS
    ]
    wall_tasks = [task for task in main_tasks if _is_wall_task(task)]
    walls_done = bool(wall_tasks) and all(task.is_done for task in wall_tasks)
    more_than_half_done = bool(main_tasks) and sum(1 for task in main_tasks if task.is_done) > len(main_tasks) / 2
    return PO_STATUS_TO_THROW if walls_done or more_than_half_done else PO_STATUS_NOT_READY


def _po_status_for_group(apartments: list[Apartment], tasks: list[Task]) -> str | None:
    if _apartment_group_mode(apartments) == "АПП":
        return None
    manual = next((apartment.po_status for apartment in apartments if apartment.po_status_manual and apartment.po_status in PO_STATUS_LABELS), None)
    return manual or _auto_po_status(tasks)


def _apartment_inspection_comment(apartments: list[Apartment]) -> str | None:
    for apartment in apartments:
        if apartment.inspection_note:
            return apartment.inspection_note
    return None


def _apartment_manual_comment(apartments: list[Apartment]) -> str | None:
    for apartment in apartments:
        if apartment.comment:
            return apartment.comment
    return None


def _apartment_inspection_status(apartments: list[Apartment]) -> str | None:
    # Непроданные квартиры считаем уже осмотренными автоматически.
    # В интерфейсе для них нельзя переключить «Был / Не был».
    if apartments and any(_is_unsold_apartment(apartment) for apartment in apartments):
        return "Был"
    if any(apartment.first_inspection_present for apartment in apartments):
        return "Был"
    return "Не был"


def _group_remark_deadline(apartments: list[Apartment]) -> date | None:
    deadlines = [apartment.app_deadline_date for apartment in apartments if apartment.app_deadline_date]
    return min(deadlines) if deadlines else None


def _deadline_status(deadline: date | None, stored_status: str | None = None) -> dict | None:
    # «Без замечаний» и пустой срок показываем как «Нет срока», без тревожной плашки.
    if not deadline:
        return None
    days_left = (deadline - date.today()).days
    if days_left < 0:
        return {"label": "Срок истёк", "class": "expired", "days_left": days_left}
    if days_left <= 15:
        return {"label": "Истекает", "class": "expiring", "days_left": days_left}
    return None


def _remark_deadline_status_for_group(apartments: list[Apartment], deadline: date | None, stored_status: str | None = None) -> dict | None:
    status = _deadline_status(deadline, stored_status)
    if status and _group_avr_status(apartments) == AVR_STATUS_SIGNED:
        return {"label": "Устранили", "class": "resolved", "days_left": status.get("days_left")}
    return status


def _app_deadline_display(apartment: Apartment) -> str:
    return apartment.app_deadline_label()


def _group_app_deadline_display(apartments: list[Apartment]) -> str:
    deadline = _group_remark_deadline(apartments)
    if deadline:
        return deadline.strftime("%d.%m.%Y")
    for apartment in apartments:
        raw = str(getattr(apartment, "app_deadline_raw", None) or "").strip()
        if raw and not Apartment._is_no_deadline_text(raw):
            return raw
    return "Нет срока"


def _group_avr_status(apartments: list[Apartment]) -> str:
    if any(apartment.avr_status == AVR_STATUS_SIGNED for apartment in apartments):
        return AVR_STATUS_SIGNED
    return AVR_STATUS_NEEDED


def _group_avr_signed_date(apartments: list[Apartment]) -> date | None:
    dates = [apartment.avr_signed_date for apartment in apartments if apartment.avr_signed_date]
    return min(dates) if dates else None


def _group_app_deadline_status(apartments: list[Apartment]) -> str | None:
    deadline = _group_remark_deadline(apartments)
    if not deadline:
        return None
    days_left = (deadline - date.today()).days
    if days_left < 0:
        return APP_DEADLINE_EXPIRED
    if days_left <= 15:
        return APP_DEADLINE_EXPIRING
    return None


def _premise_label(apartment: Apartment) -> str:
    return "Комм" if (apartment.premise_type or "apartment") == "commercial" else "кв"


def _floor_from_construction_number(value: str | None) -> str:
    parts = [part.strip() for part in str(value or "").split("-")]
    return parts[1] if len(parts) >= 2 and parts[1] else ""


def _avr_floor(apartment: Apartment | None) -> str:
    if apartment is None:
        return ""
    return _floor_from_construction_number(apartment.construction_number) or (apartment.floor or "")


def _avr_owner_options(owner_name: str | None) -> list[str]:
    text = str(owner_name or "").strip()
    if not text:
        return []
    parts = [part.strip(" \t\r\n") for part in re.split(r"[\r\n;]+|\s+/\s+", text) if part.strip()]
    seen = set()
    options = []
    for part in parts:
        key = " ".join(part.lower().split())
        if key and key not in seen:
            seen.add(key)
            options.append(part)
    return options or [text]


def _contractor_point_options() -> list[dict[str, str]]:
    points = (
        WorkPoint.query.filter(WorkPoint.point_number.in_(CONTRACTOR_POINT_LABELS.keys()))
        .order_by(WorkPoint.point_number.asc())
        .all()
    )
    existing_numbers = {str(point.point_number).strip() for point in points}
    options = []
    for number, label in CONTRACTOR_POINT_LABELS.items():
        if number in existing_numbers:
            options.append({"number": number, "label": label})
    return options


def _group_project_apartments(project_id: int) -> list[list[Apartment]]:
    apartments = (
        Apartment.query.options(selectinload(Apartment.tasks).selectinload(Task.work_point), selectinload(Apartment.tasks).selectinload(Task.glass_measurement))
        .filter(Apartment.project_id == project_id)
        .all()
    )
    groups: dict[str, list[Apartment]] = {}
    for apartment in apartments:
        if not _is_visible_apartment_row(apartment):
            continue
        groups.setdefault(_apartment_group_key(apartment), []).append(apartment)
    return list(groups.values())


def _build_apartment_overview(apartment_or_group) -> dict:
    apartments = apartment_or_group if isinstance(apartment_or_group, list) else [apartment_or_group]
    apartment = _pick_apartment_representative(apartments)
    tasks = sorted(
        [task for item in apartments for task in list(item.tasks or [])],
        key=lambda task: (
            1 if task.is_done else 0,
            int(task.work_point.point_number) if task.work_point and str(task.work_point.point_number).isdigit() else 9999,
            task.created_at or datetime.min,
            task.id,
        ),
    )
    active_tasks = [task for task in tasks if not task.is_archived and not task.is_missing_in_latest_sync]
    done_tasks = [task for task in active_tasks if task.is_done]
    left_tasks = [task for task in active_tasks if not task.is_done]
    problem_tasks = [task for task in active_tasks if task.status == "problem"]
    comments = []
    changes = []
    for task in tasks:
        for comment in task.comments:
            comments.append({"task": task, "comment": comment})
        for change in task.changes:
            if change.action == "created_from_sync":
                continue
            changes.append({"task": task, "change": change})
    comments.sort(key=lambda row: row["comment"].created_at, reverse=True)
    changes.sort(key=lambda row: row["change"].created_at, reverse=True)
    total = len(active_tasks)
    done = len(done_tasks)
    left = len(left_tasks)
    mode = _apartment_group_mode(apartments)
    percent = round((done / total * 100), 1) if total else (100 if mode == "АПП" else 0)
    remark_deadline = _group_remark_deadline(apartments)
    app_deadline_status = _group_app_deadline_status(apartments)
    return {
        "apartment": apartment,
        "premise_label": _premise_label(apartment),
        "apartments": apartments,
        "group_count": len(apartments),
        "mode": mode,
        "inspection_comment": _apartment_inspection_comment(apartments),
        "manual_comment": _apartment_manual_comment(apartments),
        "inspection_status": _apartment_inspection_status(apartments),
        "tasks": tasks,
        "active_tasks": active_tasks,
        "done_tasks": done_tasks,
        "left_tasks": left_tasks,
        "problem_tasks": problem_tasks,
        "comments": comments,
        "changes": changes,
        "total": total,
        "done": done,
        "left": left,
        "problem": len(problem_tasks),
        "percent": percent,
        "remark_deadline": remark_deadline,
        "remark_deadline_display": _group_app_deadline_display(apartments),
        "remark_deadline_status": _remark_deadline_status_for_group(apartments, remark_deadline, app_deadline_status),
        "avr_status": _group_avr_status(apartments),
        "avr_signed_date": _group_avr_signed_date(apartments),
        "show_avr": mode == "АПП" and (apartment.premise_type or "apartment") == "apartment",
        "po_status": _po_status_for_group(apartments, active_tasks),
        "has_ordered_glass": any(task.glass_measurement and task.glass_measurement.status == GLASS_STATUS_ORDERED for task in tasks),
        "has_replaced_glass": any(task.glass_measurement and task.glass_measurement.status == GLASS_STATUS_REPLACED for task in tasks),
    }


@bp.route("/apartments")
@login_required
def apartments():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    q = "".join(ch for ch in (request.args.get("q") or "") if ch.isdigit())
    po_only = request.args.get("po") == "1"
    inspection_filter = (request.args.get("inspection_status") or "").strip()
    app_status_filter = (request.args.get("app_status") or "").strip()
    po_status_filter = (request.args.get("po_status") or "").strip()

    rows = []
    for group in _group_project_apartments(project.id):
        row = _build_apartment_overview(group)
        apartment = row["apartment"]
        if q:
            search_mode, search_value = detect_search_mode(q)
            if search_mode in {"premise_number", "premise_number_or_building", "commercial_pair", "construction_number"}:
                if not any(premise_matches_search(item, search_mode, search_value) for item in row["apartments"]):
                    continue
            else:
                needle = search_value.lower().replace("ё", "е")
                haystack = " ".join([
                    apartment.label(),
                    apartment.apartment_number or "",
                    apartment.construction_number or "",
                    apartment.owner_name or "",
                    apartment.finishing_type or "",
                    apartment.comment or "",
                    apartment.inspection_note or "",
                ]).lower().replace("ё", "е")
                if needle not in haystack:
                    continue
        if po_only and row.get("po_status") != PO_STATUS_TO_THROW:
            continue
        if app_status_filter == "accepted" and row.get("mode") != "АПП":
            continue
        if app_status_filter == "not_accepted" and row.get("mode") != "не принята":
            continue
        if po_status_filter and row.get("po_status") != po_status_filter:
            continue
        if inspection_filter == "was" and row.get("inspection_status") != "Был":
            continue
        if inspection_filter == "not_was" and row.get("inspection_status") != "Не был":
            continue
        rows.append(row)

    all_rows = [_build_apartment_overview(group) for group in _group_project_apartments(project.id)]
    po_alert_count = sum(1 for row in all_rows if row.get("po_status") == PO_STATUS_TO_THROW)
    rows.sort(key=lambda row: _apartment_number_sort_value(row["apartment"].apartment_number or row["apartment"].construction_number))
    finishing_types = [
        x[0]
        for x in db.session.query(distinct(Apartment.finishing_type))
        .filter(Apartment.project_id == project.id, Apartment.finishing_type.isnot(None), Apartment.finishing_type != "")
        .order_by(Apartment.finishing_type.asc())
        .all()
    ]
    return render_template(
        "apartments.html",
        rows=rows,
        args=request.args,
        finishing_types=finishing_types,
        total_count=len(rows),
        po_only=po_only,
        po_alert_count=po_alert_count,
        po_status_labels=PO_STATUS_LABELS,
        po_status_classes=PO_STATUS_CLASSES,
        avr_status_needed=AVR_STATUS_NEEDED,
        avr_status_signed=AVR_STATUS_SIGNED,
    )


@bp.route("/avr", methods=["GET", "POST"])
@login_required
def avr():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if request.method == "POST" and current_user.role == "viewer":
        abort(403)

    apartments = _project_apartment_options(project.id)
    apartment_rows = []
    for apartment in apartments:
        number = apartment.apartment_number or apartment.construction_number or ""
        floor = _avr_floor(apartment)
        owner_options = _avr_owner_options(apartment.owner_name)
        inspection_date = format_input_date(apartment.first_inspection_date)
        apartment_rows.append(
            {
                "id": apartment.id,
                "label": apartment.label(),
                "premise_type": apartment.premise_type or "apartment",
                "number": number,
                "floor": floor,
                "owner": owner_options[0] if owner_options else (apartment.owner_name or ""),
                "owner_options": owner_options,
                "owner_selected": owner_options[:1] if owner_options else ([apartment.owner_name] if apartment.owner_name else []),
                "inspection_date": inspection_date,
                "address": project.address or "",
                "phrase": default_avr_phrase(apartment.first_inspection_date),
            }
        )

    selected_apartment = None
    selected_id = request.form.get("apartment_id") or request.args.get("apartment_id")
    if selected_id:
        try:
            selected_apartment = next((item for item in apartments if item.id == int(selected_id)), None)
        except ValueError:
            selected_apartment = None
    today_input = date.today().strftime("%Y-%m-%d")
    selected_floor = _avr_floor(selected_apartment) if selected_apartment else ""
    selected_owner_options = _avr_owner_options(selected_apartment.owner_name if selected_apartment else "")
    defaults = {
        "apartment_id": str(selected_apartment.id) if selected_apartment else "",
        "apartment_number": (selected_apartment.apartment_number or selected_apartment.construction_number or "") if selected_apartment else "",
        "floor": selected_floor,
        "premise_type": (selected_apartment.premise_type or "apartment") if selected_apartment else "apartment",
        "owner_name": (selected_owner_options[0] if selected_owner_options else (selected_apartment.owner_name or "")) if selected_apartment else "",
        "owner_options": selected_owner_options,
        "owner_selected": selected_owner_options[:1] if selected_owner_options else ([selected_apartment.owner_name] if selected_apartment and selected_apartment.owner_name else []),
        "developer_representative": "Худовердиев В.С.",
        "act_date": today_input,
        "inspection_date": format_input_date(selected_apartment.first_inspection_date) if selected_apartment else "",
        "address": project.address or "",
        "completion_phrase": default_avr_phrase(selected_apartment.first_inspection_date) if selected_apartment else default_avr_phrase(None),
    }

    if request.method == "POST":
        if selected_apartment is None:
            flash("Выберите квартиру для формирования АВР.", "warning")
            return render_template("avr.html", apartments=apartment_rows, defaults=defaults, today=today_input)

        selected_owners = [owner.strip() for owner in request.form.getlist("owner_names") if owner.strip()]
        owner_name = "\n".join(selected_owners) if selected_owners else (request.form.get("owner_name") or "").strip()
        values = defaults | {
            "apartment_number": (request.form.get("apartment_number") or defaults["apartment_number"]).strip(),
            "floor": (request.form.get("floor") or defaults["floor"]).strip(),
            "premise_type": selected_apartment.premise_type or "apartment",
            "owner_name": owner_name,
            "owner_selected": selected_owners or ([owner_name] if owner_name else []),
            "developer_representative": (request.form.get("developer_representative") or "Худовердиев В.С.").strip(),
            "act_date": format_doc_date(request.form.get("act_date") or today_input),
            "inspection_date": format_doc_date(request.form.get("inspection_date") or defaults["inspection_date"]),
            "address": (request.form.get("address") or project.address or "").strip(),
            "completion_phrase": (request.form.get("completion_phrase") or default_avr_phrase(request.form.get("inspection_date") or defaults["inspection_date"])).strip(),
        }

        if (values["premise_type"] != "commercial" and not values["floor"]) or not values["owner_name"]:
            flash("Заполните этаж и ФИО собственника.", "warning")
            form_defaults = defaults | values
            return render_template("avr.html", apartments=apartment_rows, defaults=form_defaults, today=today_input)

        exports_dir = Path(current_app.config["EXPORT_FOLDER"]) / "avr"
        filename = safe_avr_filename(project.name, values["apartment_number"], selected_apartment.premise_type)
        output_path = exports_dir / filename
        try:
            build_avr_docx(output_path, values)
        except Exception as exc:
            current_app.logger.exception("AVR document generation failed")
            flash(f"Не удалось сформировать АВР: {exc}", "danger")
            return render_template("avr.html", apartments=apartment_rows, defaults=defaults, today=today_input)

        return send_file(output_path, as_attachment=True, download_name=filename)

    return render_template("avr.html", apartments=apartment_rows, defaults=defaults, today=today_input)


@bp.route("/documents")
@login_required
def documents():
    if _setting_bool("hide_documents_section"):
        return _documents_under_development_response()

    # Показываем фирменную загрузку при переходе во вкладку «Документы»,
    # но не включаем её при внутренних переходах внутри раздела документов.
    referrer_path = urlparse(request.referrer or "").path
    if not referrer_path.startswith("/documents"):
        session["show_success_loader"] = True

    return render_template("documents.html", document_type=None)


@bp.route("/documents/addendum", methods=["GET", "POST"])
@login_required
def documents_addendum():
    if _setting_bool("hide_documents_section"):
        return _documents_under_development_response()
    if current_user.role == "viewer":
        abort(403)

    result = None
    fields = addendum_fields_for_template()
    field_keys = addendum_field_keys()
    options = addendum_options_for_template()

    if request.method == "POST":
        uploads_dir = Path(current_app.config["UPLOAD_FOLDER"]) / "documents"
        exports_dir = Path(current_app.config["EXPORT_FOLDER"]) / "documents"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.mkdir(parents=True, exist_ok=True)

        upload = request.files.get("document")
        template_variant = "materials"
        source_path = None
        prepared_source_path = None
        source_label = f"vstroenny_shablon_{template_variant}.docx"

        if upload and upload.filename:
            filename_lower = upload.filename.lower()
            try:
                validate_upload(upload, ["docx", "doc"], max_size=current_app.config.get("MAX_UPLOAD_FILE_BYTES"))
            except ValueError as exc:
                flash(str(exc), "warning")
                return render_template("documents.html", document_type="addendum", fields=fields, options=options, result=result)
            if not filename_lower.endswith((".docx", ".doc")):
                flash("Поддерживаются файлы Word .docx и .doc. .doc будет автоматически сконвертирован в .docx, если на сервере есть LibreOffice или Microsoft Word.", "warning")
                return render_template("documents.html", document_type="addendum", fields=fields, options=options, result=result)

            source_name = safe_docx_filename(upload.filename, "source")
            if filename_lower.endswith(".doc"):
                source_name = source_name.replace(".docx", ".doc")
            source_path = uploads_dir / source_name
            upload.save(source_path)
            source_label = upload.filename

            try:
                prepared_source_path = prepare_uploaded_word_file(source_path, uploads_dir, template_variant)
                is_addendum, validation_message = validate_addendum_template(prepared_source_path)
                if not is_addendum:
                    flash(validation_message, "danger")
                    return render_template("documents.html", document_type="addendum", fields=fields, options=options, result=result)
                if filename_lower.endswith(".doc"):
                    flash("Файл .doc загружен. Система автоматически подготовила его к генерации доп. соглашения.", "info")
            except Exception as exc:
                current_app.logger.exception("Document flow addendum source preparation failed")
                if filename_lower.endswith(".doc"):
                    flash(f"Не удалось подготовить .doc: {exc}", "danger")
                else:
                    flash(f"Не удалось подготовить шаблон Word: {exc}", "danger")
                return render_template("documents.html", document_type="addendum", fields=fields, options=options, result=result)
        else:
            flash("Загрузите файл Word .docx или .doc — без файла доп. соглашение не формируется и скачать его нельзя.", "warning")
            return render_template("documents.html", document_type="addendum", fields=fields, options=options, result=result)

        output_name = safe_docx_filename(source_label, "dop-soglashenie")
        output_path = exports_dir / output_name

        field_values = {key: (request.form.get(key) or "").strip() for key in field_keys}
        field_values["owner_count"] = (request.form.get("owner_count") or "1").strip()
        selected_options = request.form.getlist("options")
        try:
            changes = build_addendum_docx(prepared_source_path, output_path, field_values, selected_options)
        except Exception as exc:
            current_app.logger.exception("Document flow addendum failed")
            flash(f"Не удалось подготовить документ: {exc}", "danger")
            return render_template("documents.html", document_type="addendum", fields=fields, options=options, result=result)

        result = {
            "filename": output_name,
            "changes": changes,
            "selected_count": len(selected_options),
            "replace_count": sum(1 for item in changes if item.kind == "replace"),
            "append_count": sum(1 for item in changes if item.kind == "append"),
        }
        flash("Доп. соглашение подготовлено.", "success")

    return render_template("documents.html", document_type="addendum", fields=fields, options=options, result=result)


@bp.route("/documents/download/<path:filename>")
@login_required
def documents_download(filename: str):
    if _setting_bool("hide_documents_section"):
        return redirect(url_for("main.documents"))
    exports_dir = (Path(current_app.config["EXPORT_FOLDER"]) / "documents").resolve()
    file_path = (exports_dir / filename).resolve()
    if exports_dir not in file_path.parents or not file_path.exists():
        abort(404)
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


@bp.route("/apartments/<int:apartment_id>/po-status", methods=["POST"])
@login_required
def update_apartment_po_status(apartment_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if current_user.role == "viewer":
        abort(403)
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if apartment.project_id != project.id:
        abort(404)
    status = (request.form.get("po_status") or "").strip()
    if status not in PO_STATUS_LABELS:
        abort(400)
    group_key = _apartment_group_key(apartment)
    group = [
        item
        for item in Apartment.query.filter(Apartment.project_id == project.id).all()
        if _is_visible_apartment_row(item) and _apartment_group_key(item) == group_key
    ]
    for item in group or [apartment]:
        item.po_status = status
        item.po_status_manual = True
    db.session.commit()
    flash("Статус ПО обновлен", "success")
    return redirect(request.referrer or url_for("main.apartments"))


@bp.route("/apartments/<int:apartment_id>/inspection-status", methods=["POST"])
@login_required
def update_apartment_inspection_status(apartment_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if current_user.role == "viewer":
        abort(403)
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if apartment.project_id != project.id:
        abort(404)
    status = (request.form.get("inspection_status") or "").strip()
    if status not in {"was", "not_was"}:
        abort(400)
    group_key = _apartment_group_key(apartment)
    group = [
        item
        for item in Apartment.query.filter(Apartment.project_id == project.id).all()
        if _is_visible_apartment_row(item) and _apartment_group_key(item) == group_key
    ]
    if any(_is_unsold_apartment(item) for item in group or [apartment]):
        for item in group or [apartment]:
            item.first_inspection_present = True
            item.first_inspection_date = item.first_inspection_date or date.today()
        db.session.commit()
        flash("У непроданной квартиры осмотр фиксируется автоматически: Был", "info")
        return redirect(request.referrer or url_for("main.apartment_detail", apartment_id=apartment.id))

    was_present = status == "was"
    for item in group or [apartment]:
        item.first_inspection_present = was_present
        item.first_inspection_date = (item.first_inspection_date or date.today()) if was_present else None
    db.session.commit()
    flash("Статус осмотра обновлён", "success")
    return redirect(request.referrer or url_for("main.apartment_detail", apartment_id=apartment.id))


@bp.route("/apartments/<int:apartment_id>/inspection-note", methods=["POST"])
@login_required
def update_apartment_inspection_note(apartment_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if current_user.role == "viewer":
        abort(403)
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if apartment.project_id != project.id:
        abort(404)
    note = (request.form.get("inspection_note") or "").strip()
    is_app_mode = _is_app_mode(note)
    accepted_date = _parse_app_date(note)
    group_key = _apartment_group_key(apartment)
    group = [
        item
        for item in Apartment.query.filter(Apartment.project_id == project.id).all()
        if _is_visible_apartment_row(item) and _apartment_group_key(item) == group_key
    ]
    for item in group or [apartment]:
        item.inspection_note = note or None
        item.is_app_mode = is_app_mode
        item.inspection_date = accepted_date
        item.deadline_date = accepted_date
        if is_app_mode and item.avr_status not in {AVR_STATUS_NEEDED, AVR_STATUS_SIGNED}:
            item.avr_status = AVR_STATUS_NEEDED
    db.session.commit()
    flash("Дата осмотра обновлена", "success")
    return redirect(request.referrer or url_for("main.apartment_detail", apartment_id=apartment.id))


@bp.route("/apartments/<int:apartment_id>/comment", methods=["POST"])
@login_required
def update_apartment_comment(apartment_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if current_user.role == "viewer":
        abort(403)
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if apartment.project_id != project.id:
        abort(404)
    comment = (request.form.get("apartment_comment") or "").strip()
    group_key = _apartment_group_key(apartment)
    group = [
        item
        for item in Apartment.query.filter(Apartment.project_id == project.id).all()
        if _is_visible_apartment_row(item) and _apartment_group_key(item) == group_key
    ]
    for item in group or [apartment]:
        item.comment = comment or None
    db.session.commit()
    flash("Комментарий сохранен", "success")
    return redirect(request.referrer or url_for("main.apartment_detail", apartment_id=apartment.id))


@bp.route("/apartments/<int:apartment_id>/avr-status", methods=["POST"])
@login_required
def update_apartment_avr_status(apartment_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if current_user.role == "viewer":
        abort(403)
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if apartment.project_id != project.id:
        abort(404)
    status = (request.form.get("avr_status") or "").strip()
    if status not in {AVR_STATUS_NEEDED, AVR_STATUS_SIGNED}:
        abort(400)
    signed_date = parse_date(request.form.get("avr_signed_date"))
    if status == AVR_STATUS_SIGNED and signed_date is None:
        signed_date = date.today()

    group_key = _apartment_group_key(apartment)
    group = [
        item
        for item in Apartment.query.filter(Apartment.project_id == project.id).all()
        if _is_visible_apartment_row(item) and _apartment_group_key(item) == group_key
    ]
    for item in group or [apartment]:
        item.avr_status = status
        item.avr_signed_date = signed_date if status == AVR_STATUS_SIGNED else None
    db.session.commit()
    flash("Статус АВР обновлен", "success")
    return redirect(request.referrer or url_for("main.apartment_detail", apartment_id=apartment.id))


@bp.route("/apartments/<int:apartment_id>")
@login_required
def apartment_detail(apartment_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if apartment.project_id != project.id:
        abort(404)
    group_key = _apartment_group_key(apartment)
    group = [
        item
        for item in (
            Apartment.query.options(
                selectinload(Apartment.tasks).selectinload(Task.work_point),
                selectinload(Apartment.tasks).selectinload(Task.glass_measurement),
                selectinload(Apartment.tasks).selectinload(Task.responsible),
                selectinload(Apartment.tasks).selectinload(Task.comments).selectinload(TaskComment.user),
                selectinload(Apartment.tasks).selectinload(Task.changes),
            )
            .filter(Apartment.project_id == project.id)
            .all()
        )
        if _is_visible_apartment_row(item) and _apartment_group_key(item) == group_key
    ]
    if not group:
        group = [apartment]
    overview = _build_apartment_overview(group)
    return render_template(
        "apartment_detail.html",
        row=overview,
        apartment=overview["apartment"],
        today=date.today(),
        po_status_labels=PO_STATUS_LABELS,
        po_status_classes=PO_STATUS_CLASSES,
        avr_status_needed=AVR_STATUS_NEEDED,
        avr_status_signed=AVR_STATUS_SIGNED,
    )


@bp.route("/report")
@login_required
def work_report():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    today = date.today()
    start = today - timedelta(days=55)
    tasks = (
        Task.query.join(Apartment)
        .join(WorkPoint)
        .filter(
            Task.project_id == project.id,
            Task.is_done.is_(True),
            Task.status == STATUS_DONE,
            Task.completed_date.isnot(None),
            Task.completed_date >= start,
        )
        .order_by(Task.completed_date.desc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc())
        .all()
    )
    buckets = []
    bucket_index = 1
    cursor = today
    while cursor >= start:
        period_start = cursor - timedelta(days=6)
        period_tasks = [task for task in tasks if period_start <= task.completed_date.date() <= cursor]
        buckets.append({"index": bucket_index, "start": period_start, "end": cursor, "tasks": period_tasks})
        bucket_index += 1
        cursor = period_start - timedelta(days=1)
    return render_template("work_report.html", buckets=buckets, project=project)


@bp.route("/report/export")
@login_required
def work_report_export():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER, ROLE_VERIFIER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    today = date.today()
    week = request.args.get("week", type=int)
    if week and week > 0:
        end = today - timedelta(days=(week - 1) * 7)
        start = end - timedelta(days=6)
        filename_prefix = f"{project.name}_отчет_{start.strftime('%d.%m.%Y')}-{end.strftime('%d.%m.%Y')}"
    else:
        start = today - timedelta(days=55)
        end = today
        filename_prefix = f"{project.name}_отчет_весь период"
    tasks = (
        Task.query.join(Apartment)
        .join(WorkPoint)
        .filter(
            Task.project_id == project.id,
            Task.is_done.is_(True),
            Task.status == STATUS_DONE,
            Task.completed_date.isnot(None),
            Task.completed_date >= start,
            Task.completed_date <= end + timedelta(days=1),
        )
        .order_by(Task.completed_date.desc(), cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc())
        .all()
    )
    path = export_report_tasks_excel(tasks, filename_prefix)
    return send_file(path, as_attachment=True, download_name=Path(path).name)


def _apartment_task_groups(query):
    rows = []
    for apartment in query.order_by(cast(Apartment.apartment_number, Integer).asc(), Apartment.apartment_number.asc()).all():
        tasks = [task for task in apartment.tasks if not task.is_archived]
        visible = [task for task in tasks if task.work_point and task.work_point.point_number in VISIBLE_WORK_POINT_NUMBERS]
        done = [task for task in visible if task.is_done]
        left = [task for task in visible if not task.is_done]
        painter_tasks = [task for task in visible if task.work_point and task.work_point.point_number in {"10", "11", "12"}]
        painter_done = bool(painter_tasks) and all(task.is_done for task in painter_tasks)
        rows.append({"apartment": apartment, "done": done, "left": left, "total": len(visible), "painter_done": painter_done})
    return rows


@bp.route("/notifications")
@login_required
def notifications():
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    tab = request.args.get("tab", "po")
    today = date.today()
    base = Apartment.query.filter(Apartment.project_id == project.id)
    if tab == "archive":
        apartments = base.filter(Apartment.avr_archived_at.isnot(None))
        rows = _apartment_task_groups(apartments)
    elif tab == "60":
        apartments = base.filter(
            Apartment.app_deadline_date.isnot(None),
            Apartment.app_deadline_date <= today + timedelta(days=15),
            Apartment.avr_archived_at.is_(None),
        )
        rows = _apartment_task_groups(apartments)
    else:
        apartments = base.filter(Apartment.deadline_date.is_(None), Apartment.finishing_type.ilike("%бел%"), Apartment.avr_archived_at.is_(None))
        rows = [
            row
            for row in _apartment_task_groups(apartments)
            if row["total"] > 0 and (len(row["done"]) > row["total"] / 2 or row["painter_done"])
        ]
    return render_template("notifications.html", rows=rows, tab=tab, today=today)


@bp.route("/notifications/<int:apartment_id>/avr", methods=["POST"])
@login_required
def archive_apartment_avr(apartment_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if apartment.project_id != project.id:
        abort(404)
    apartment.avr_archived_at = datetime.utcnow()
    for task in apartment.tasks:
        task.is_archived = True
    db.session.commit()
    flash("Квартира перенесена в архив АВР.", "success")
    return redirect(url_for("main.notifications", tab="60"))



def _is_crm_created_task(task: Task) -> bool:
    """Удалять разрешаем только замечания, созданные вручную внутри CRM."""
    return (task.source_sheet_name or "").strip().lower() in {"manual", "assignment_manual"}


@bp.route("/tasks/<int:task_id>")
@login_required
def task_detail(task_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    if current_user.role in WORKER_ROLES and task.responsible_id != current_user.id:
        abort(403)
    edit_form = TaskEditForm(obj=task)
    edit_form.responsible_id.choices = [("", "Не назначен")] + [
        (str(u.id), u.full_name or u.username)
        for u in User.query.filter(User.is_active.is_(True), (User.project_id == project.id) | (User.project_id.is_(None))).order_by(User.full_name.asc()).all()
    ]
    edit_form.responsible_id.data = str(task.responsible_id or "")
    edit_form.planned_date.data = task.planned_date.isoformat() if task.planned_date else ""
    comment_form = CommentForm()
    visible_changes = [change for change in task.changes if change.action != "created_from_sync"]
    other_open_tasks = (
        Task.query.join(WorkPoint)
        .options(selectinload(Task.work_point), selectinload(Task.glass_measurement))
        .filter(
            Task.project_id == project.id,
            Task.apartment_id == task.apartment_id,
            Task.id != task.id,
            Task.is_done.is_(False),
            Task.is_archived.is_(False),
        )
        .order_by(WorkPoint.point_number.asc(), Task.updated_at.desc())
        .limit(30)
        .all()
    )
    return render_template(
        "task_detail.html",
        task=task,
        edit_form=edit_form,
        comment_form=comment_form,
        visible_changes=visible_changes,
        other_open_tasks=other_open_tasks,
        can_delete_task=_is_crm_created_task(task) and current_user.role != "viewer",
    )


@bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def task_delete(task_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    if current_user.role == "viewer":
        abort(403)
    task = (
        Task.query.filter(Task.id == task_id, Task.project_id == project.id)
        .first()
        or abort(404)
    )
    if not _is_crm_created_task(task):
        flash("Удалять можно только замечания, добавленные вручную внутри CRM", "warning")
        return redirect(url_for("main.task_detail", task_id=task.id))
    _record_simple_deletion(
        "task_delete",
        "task",
        task,
        f"Замечание #{task.id}",
        f"Удалено ручное замечание: {(task.description or task.source_cell_value or '')[:180]}",
        project_id=project.id,
        extra={
            "apartment_label": task.apartment.label() if task.apartment else None,
            "work_point": task.work_point.display_name if task.work_point else None,
            "comment_count": len(task.comments),
            "change_count": len(task.changes),
        },
    )
    for writeoff in list(task.material_writeoffs):
        writeoff.tasks.remove(task)
    db.session.delete(task)
    db.session.commit()
    flash("Замечание удалено", "success")
    return redirect(url_for("main.task_list"))


@bp.route("/tasks/<int:task_id>/update", methods=["POST"])
@login_required
def update_task(task_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    if not can_change_task(current_user, task):
        abort(403)
    form = TaskEditForm()
    form.responsible_id.choices = [("", "Не назначен")] + [
        (str(u.id), u.full_name or u.username)
        for u in User.query.filter(User.is_active.is_(True), (User.project_id == project.id) | (User.project_id.is_(None))).order_by(User.full_name.asc()).all()
    ]
    if form.validate_on_submit():
        fields = {
            "status": form.status.data,
            "priority": form.priority.data,
            "responsible_id": int(form.responsible_id.data) if form.responsible_id.data else None,
            "planned_date": parse_date(form.planned_date.data),
            "comment": form.comment.data,
        }
        if fields["responsible_id"]:
            responsible = db.session.get(User, fields["responsible_id"])
            if not _user_can_work_in_project(responsible, project):
                flash("Выберите корректного исполнителя", "danger")
                return redirect(url_for("main.task_detail", task_id=task.id))
        for field, new_value in fields.items():
            old_value = getattr(task, field)
            if old_value != new_value:
                setattr(task, field, new_value)
                log_change(task, "field_update", field, old_value, new_value)
        if is_problem_details_required(task.status, task.comment):
            flash("Для статуса 'Проблема' нужно заполнить описание проблемы", "danger")
            return redirect(url_for("main.task_detail", task_id=task.id))
        task.is_done = task.status in DONE_STATUSES
        if task.is_done and not task.completed_date:
            task.completed_date = datetime.utcnow()
        if not task.is_done and task.completed_date:
            task.completed_date = None
        task.manually_edited = True
        db.session.commit()
        flash("Карточка задачи обновлена", "success")
    else:
        flash("Проверьте поля формы", "danger")
    return redirect(url_for("main.task_detail", task_id=task.id))


@bp.route("/tasks/<int:task_id>/comment", methods=["POST"])
@login_required
def add_task_comment(task_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    if not can_change_task(current_user, task):
        abort(403)
    form = CommentForm()
    if form.validate_on_submit():
        comment = TaskComment(task_id=task.id, user_id=current_user.id, body=form.body.data)
        db.session.add(comment)
        log_change(task, "comment_added", "comment", "", form.body.data)
        db.session.commit()
        flash("Комментарий добавлен", "success")
    return redirect(url_for("main.task_detail", task_id=task.id))


@bp.route("/tasks/<int:task_id>/status/<status>", methods=["POST"])
@login_required
def quick_status(task_id: int, status: str):
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    if not can_change_task(current_user, task):
        abort(403)
    if status not in TASK_STATUSES:
        abort(400)
    if is_problem_details_required(status, request.form.get("problem_comment") or task.comment):
        if wants_json:
            return jsonify({"ok": False, "message": "Для статуса 'Проблема' нужно заполнить описание проблемы"}), 400
        flash("Для статуса 'Проблема' нужно заполнить описание проблемы", "danger")
        return redirect(request.referrer or url_for("main.task_list"))
    if status == "problem":
        problem_comment = (request.form.get("problem_comment") or "").strip()
        if problem_comment:
            old_comment = task.comment
            task.comment = problem_comment
            if old_comment != problem_comment:
                log_change(task, "field_update", "comment", old_comment, problem_comment)
    change_task_status(task, status, user_id=current_user.id)
    if request.form.get("sync_google_format") == "1":
        try:
            update_task_strike_in_google_sheet(task)
        except Exception as exc:
            if wants_json:
                return jsonify({"ok": False, "message": f"Статус сохранён, но зачёркивание в Google Sheets не применилось: {exc}"}), 500
            flash(f"Статус сохранён, но зачёркивание в Google Sheets не применилось: {exc}", "warning")
            return redirect(request.referrer or url_for("main.task_list"))
    if wants_json:
        return jsonify(
            {
                "ok": True,
                "task_id": task.id,
                "status": task.status,
                "status_label": task.status_label(),
                "status_class": task.status_class(),
                "is_done": task.is_done,
                "message": f"Статус изменён: {TASK_STATUSES[status]['label']}",
            }
        )
    flash(f"Статус изменён: {TASK_STATUSES[status]['label']}", "success")
    return redirect(request.referrer or url_for("main.task_list"))


@bp.route("/upload-excel", methods=["GET", "POST"])
@login_required
def upload_excel():
    if not can_manage_sync(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    form = UploadExcelForm()
    transfer_form = UploadExcelForm(prefix="transfer")
    preview = None
    upload_kind = request.form.get("upload_kind")
    if upload_kind == "remarks" and form.validate_on_submit():
        try:
            validate_upload(form.file.data, ["xlsx"], max_size=current_app.config.get("MAX_UPLOAD_FILE_BYTES"))
            path = save_upload(form.file.data)
            result = sync_excel_file(path, project_name=project.name)
            set_setting(f"latest_excel_path_project_{project.id}", str(path))
            pending_conflicts = (
                SyncConflict.query.join(Task, SyncConflict.task_id == Task.id)
                .filter(SyncConflict.status == "pending", Task.project_id == project.id)
                .count()
            )
            latest_log = SyncLog.query.filter(SyncLog.project_id == project.id).order_by(SyncLog.started_at.desc()).first()
            if latest_log:
                latest_log.missing_count = pending_conflicts
                db.session.commit()
            if pending_conflicts:
                flash(
                    f"Добавлено новых - {result.get('created_count', 0)} , несостыковок - {pending_conflicts}",
                    "warning",
                )
                return redirect(url_for("main.sync_conflicts"))
            flash(
                f"Добавлено новых - {result.get('created_count', 0)} , несостыковок - {pending_conflicts}",
                "success",
            )
        except Exception as exc:
            current_app.logger.exception("Excel import failed")
            flash(f"Ошибка загрузки Excel: {exc}", "danger")
    elif upload_kind == "transfers" and transfer_form.validate_on_submit():
        try:
            validate_upload(transfer_form.file.data, ["xlsx"], max_size=current_app.config.get("MAX_UPLOAD_FILE_BYTES"))
            path = save_upload(transfer_form.file.data)
            result = sync_transfer_statistics(path, project_name=project.name)
            flash(
                "Статистика передач обновлена: "
                f"принято - {result.get('accepted_count', 0)}, "
                f"ждёт - {result.get('waiting_count', 0)}, "
                f"не продано - {result.get('unsold_count', 0)}",
                "success",
            )
        except Exception as exc:
            current_app.logger.exception("Transfer statistics import failed")
            flash(f"Ошибка загрузки статистики передач: {exc}", "danger")
    return render_template("upload_excel.html", form=form, transfer_form=transfer_form, preview=preview)


@bp.route("/export/tasks")
@login_required
def export_tasks():
    if not can_export(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    category_id = request.args.get("category_id", type=int)
    tasks = _export_tasks_from_request(request.args.to_dict(), project.id, category_id=category_id).all()
    path = export_tasks_to_excel(tasks, filename_prefix=project.name)
    return send_file(path, as_attachment=True, download_name=Path(path).name)


@bp.route("/export/category/<int:category_id>")
@login_required
def export_category_tasks(category_id: int):
    if not can_export(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    category = db.session.get(WorkCategory, category_id) or abort(404)
    tasks = _export_tasks_from_request(request.args.to_dict(), project.id, category_id=category_id).all()
    path = export_remark_tasks_excel(tasks, f"{project.name}_{category.name}", title=category.name)
    return send_file(path, as_attachment=True, download_name=Path(path).name)


@bp.route("/export/category/<int:category_id>/pdf")
@login_required
def export_category_tasks_pdf(category_id: int):
    if not can_export(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    category = db.session.get(WorkCategory, category_id) or abort(404)
    tasks = build_task_query({}, category_id=category_id, project_id=project.id).all()
    path = export_tasks_pdf(tasks, f"{project.name}_{category.name}", title=f"Замечания - {category.name}")
    return send_file(path, as_attachment=True, download_name=Path(path).name, mimetype="application/pdf")


@bp.route("/export/source-with-strikes")
@login_required
def export_source_with_strikes():
    if not can_export(current_user):
        abort(403)
    try:
        project = selected_project()
        if project is None:
            return redirect(url_for("main.objects"))
        source_path = get_setting(f"latest_excel_path_project_{project.id}")
        if not source_path:
            flash("Для этого объекта ещё не загружали Excel с замечаниями.", "warning")
            return redirect(url_for("main.upload_excel"))
        path = export_source_excel_with_strikes(source_path=source_path, project_name=project.name)
        return send_file(path, as_attachment=True, download_name=Path(path).name)
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.dashboard"))


@bp.route("/mappings", methods=["GET", "POST"])
@login_required
def mapping_settings():
    if not can_manage_mapping(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    ensure_default_categories()
    hidden_point_numbers = {"7", "9", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33"}
    categories_to_show = [
        category
        for category in WorkCategory.query.filter(WorkCategory.is_active.is_(True)).order_by(WorkCategory.sort_order.asc()).all()
        if (category.name or "").strip().lower() not in {"все", "доп.соглашение"}
    ]
    point_ids_for_project = [
        point_id for (point_id,) in db.session.query(Task.work_point_id).filter(Task.project_id == project.id).distinct().all()
    ]
    points = (
        WorkPoint.query.filter(WorkPoint.id.in_(point_ids_for_project or [-1]), WorkPoint.is_active.is_(True))
        .order_by(WorkPoint.point_number.asc())
        .all()
    )
    if request.method == "POST":
        allowed_point_ids = {point.id for point in points}
        for category in categories_to_show:
            selected = request.form.getlist(f"category_{category.id}")
            point_ids = [int(x) for x in selected if x.isdigit() and int(x) in allowed_point_ids]
            update_category_points(category.id, point_ids)
        flash(f"Распределение сохранено для объекта: {project.name}", "success")
        return redirect(url_for("main.mapping_settings"))
    return render_template(
        "mapping_settings.html",
        categories=categories_to_show,
        points=points,
        hidden_point_numbers=hidden_point_numbers,
        project=project,
    )




@bp.route("/settings", methods=["GET", "POST"])
@login_required
def site_settings():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    if request.method == "POST":
        _set_setting_bool("hide_documents_section", request.form.get("hide_documents_section") == "1")
        _set_setting_bool("mobile_version_under_development", request.form.get("mobile_version_under_development") == "1")
        _set_setting_bool("site_maintenance_mode", request.form.get("site_maintenance_mode") == "1")
        allowed_section_keys = {choice["key"] for choice in SECTION_LOCK_CHOICES}
        _set_setting_csv("blocked_site_sections", [key for key in request.form.getlist("blocked_site_sections") if key in allowed_section_keys])
        db.session.commit()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=True)
        flash("Настройки сохранены", "success")
        return redirect(url_for("main.site_settings"))
    return render_template(
        "settings.html",
        hide_documents_section=_setting_bool("hide_documents_section"),
        mobile_version_under_development=_setting_bool("mobile_version_under_development"),
        site_maintenance_mode=_setting_bool("site_maintenance_mode"),
        blocked_site_sections=_setting_csv("blocked_site_sections"),
        section_lock_choices=SECTION_LOCK_CHOICES,
    )


@bp.route("/users", methods=["GET", "POST"])
@login_required
@role_required(ROLE_ADMIN)
def users():
    form = UserForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user:
            flash("Пользователь с таким логином уже есть", "danger")
        else:
            project = selected_project()
            user = User(
                username=form.username.data.strip(),
                full_name=form.full_name.data.strip() if form.full_name.data else None,
                role=form.role.data,
                is_active=True,
                project_id=project.id if project and form.role.data != ROLE_ADMIN else None,
            )
            password = form.password.data or "ChangeMe123!"
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Пользователь создан. Если пароль не вводили, временный пароль: ChangeMe123!", "success")
            return redirect(url_for("main.users"))
    project = selected_project()
    query = User.query
    if project:
        query = query.filter((User.project_id == project.id) | (User.project_id.is_(None)))
    users = query.order_by(User.created_at.desc()).all()
    return render_template("users.html", users=users, form=form, project=project)


@bp.route("/users/<int:user_id>/password", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN)
def user_set_password(user_id: int):
    user = db.session.get(User, user_id) or abort(404)
    _abort_if_user_outside_current_project(user)
    if user.id == current_user.id:
        flash("Нельзя изменить пароль текущего пользователя здесь", "danger")
        return redirect(url_for("main.users"))
    password = (request.form.get("password") or "").strip()
    if len(password) < 8:
        flash("Пароль должен быть минимум 8 символов", "danger")
        return redirect(url_for("main.users"))
    user.set_password(password)
    db.session.commit()
    flash("Пароль обновлён", "success")
    return redirect(url_for("main.users"))


@bp.route("/users/<int:user_id>/password", methods=["GET"])
@login_required
@role_required(ROLE_ADMIN)
def user_set_password_page(user_id: int):
    user = db.session.get(User, user_id) or abort(404)
    _abort_if_user_outside_current_project(user)
    if user.id == current_user.id:
        flash("Нельзя изменить пароль текущего пользователя здесь", "danger")
        return redirect(url_for("main.users"))
    form = UserPasswordForm()
    return render_template("user_password.html", user=user, form=form)


@bp.route("/users/<int:user_id>/delete/confirm", methods=["GET"])
@login_required
@role_required(ROLE_ADMIN)
def user_delete_confirm(user_id: int):
    user = db.session.get(User, user_id) or abort(404)
    _abort_if_user_outside_current_project(user)
    if user.id == current_user.id:
        flash("Нельзя удалить текущего пользователя", "danger")
        return redirect(url_for("main.users"))
    return render_template("user_delete_confirm.html", user=user)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN)
def user_delete(user_id: int):
    user = db.session.get(User, user_id) or abort(404)
    _abort_if_user_outside_current_project(user)
    if user.id == current_user.id:
        flash("Нельзя удалить текущего пользователя", "danger")
        return redirect(url_for("main.users"))
    project = selected_project()
    _record_simple_deletion(
        "user_delete",
        "user",
        user,
        user.full_name or user.username,
        f"Удалён аккаунт пользователя: {user.full_name or user.username}.",
        project_id=project.id if project else None,
        extra={"project_ids": [project.id for project in user.projects]},
    )
    db.session.delete(user)
    db.session.commit()
    flash("Аккаунт удалён", "success")
    return redirect(url_for("main.users"))


@bp.route("/sync-logs")
@login_required
def sync_logs():
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    logs = SyncLog.query.filter(SyncLog.project_id == project.id).order_by(SyncLog.started_at.desc()).limit(100).all()
    return render_template("sync_logs.html", logs=logs, project=project)


@bp.route("/sync-logs/<int:log_id>/delete", methods=["POST"])
@login_required
def delete_sync_log(log_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    log = db.session.get(SyncLog, log_id) or abort(404)
    if not log.project_id or log.project_id != project.id:
        abort(404)
    delete_from = log.started_at
    if not log.rolled_back_at:
        ok, message = apply_sync_rollback(log)
        if not ok:
            flash(message, "warning")
            return redirect(url_for("main.sync_logs"))
        affected_logs = SyncLog.query.filter(
            SyncLog.project_id == project.id,
            SyncLog.started_at >= delete_from,
        ).all()
    else:
        affected_logs = [log]
    deleted_logs = len(affected_logs)
    for affected_log in affected_logs:
        _record_simple_deletion(
            "sync_log_delete",
            "sync_log",
            affected_log,
            f"Синхронизация #{affected_log.id}",
            f"Удалена запись журнала синхронизации: {affected_log.source_type} {affected_log.source_name or ''}.",
            project_id=project.id,
        )
        db.session.delete(affected_log)
    _refresh_sync_dashboard_settings(project.id)
    db.session.commit()
    flash(f"Синхронизация откатана, данные загрузки удалены, записей журнала удалено: {deleted_logs}", "success")
    return redirect(url_for("main.sync_logs"))


@bp.route("/sync-logs/<int:log_id>/rollback", methods=["POST"])
@login_required
def rollback_sync_log(log_id: int):
    if current_user.role not in {ROLE_ADMIN, ROLE_MANAGER}:
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    log = db.session.get(SyncLog, log_id) or abort(404)
    if not log.project_id or log.project_id != project.id:
        abort(404)
    ok, message = apply_sync_rollback(log)
    if ok:
        _refresh_sync_dashboard_settings(project.id)
        db.session.commit()
    flash(message, "success" if ok else "warning")
    return redirect(url_for("main.sync_logs"))


def _parse_conflict_value_for_field(field_name: str | None, value: str | None):
    text = (value or "").strip()
    if field_name in {"inspection_date", "reinspection_date", "deadline_date", "remark_deadline_date", "app_deadline_date", "avr_signed_date"}:
        return parse_date(text)
    if field_name == "is_app_mode":
        return text.lower() in {"1", "true", "yes", "да", "апп"}
    if field_name in {"owner_name", "phone", "finishing_type", "entrance", "floor", "app_deadline_raw", "app_deadline_status", "avr_status", "comment", "inspection_note"}:
        return text or None
    return text or None


def _apply_sync_conflict_new_value(conflict: SyncConflict) -> None:
    if (conflict.target_type or "task") == "apartment":
        apartment = conflict.apartment or (conflict.task.apartment if conflict.task else None)
        if apartment is None or not conflict.field_name:
            return
        setattr(apartment, conflict.field_name, _parse_conflict_value_for_field(conflict.field_name, conflict.new_value))
        return

    task = conflict.task
    if not task:
        return
    task.source_cell_value = conflict.new_value
    task.source_hash = conflict.new_hash
    # Пользователь нажал «Принять новое» — значит новый текст из Excel должен стать видимым текстом замечания.
    if conflict.field_name in {None, "source_cell_value", "description"}:
        task.description = conflict.new_value


@bp.route("/conflicts")
@login_required
def sync_conflicts():
    if not can_manage_sync(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    conflicts = (
        SyncConflict.query.join(Task, SyncConflict.task_id == Task.id)
        .filter(SyncConflict.status == "pending", Task.project_id == project.id)
        .order_by(SyncConflict.created_at.desc())
        .limit(500)
        .all()
    )
    return render_template("sync_conflicts.html", conflicts=conflicts)


@bp.route("/conflicts/<int:conflict_id>/<action>", methods=["POST"])
@login_required
def resolve_conflict(conflict_id: int, action: str):
    if not can_manage_sync(current_user):
        abort(403)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    conflict = db.session.get(SyncConflict, conflict_id) or abort(404)
    conflict_project_id = None
    if conflict.task:
        conflict_project_id = conflict.task.project_id
    elif conflict.apartment:
        conflict_project_id = conflict.apartment.project_id
    if conflict_project_id != project.id:
        abort(404)
    if conflict.status != "pending":
        return redirect(url_for("main.sync_conflicts"))
    if action not in {"keep_old", "apply_new"}:
        abort(400)
    if action == "apply_new":
        _apply_sync_conflict_new_value(conflict)
    conflict.status = action
    conflict.resolved_at = datetime.utcnow()
    conflict.resolved_by_user_id = current_user.id
    db.session.commit()
    flash("Конфликт синхронизации решён", "success")
    return redirect(url_for("main.sync_conflicts"))


@bp.route("/conflicts/bulk/<action>", methods=["POST"])
@login_required
def resolve_conflicts_bulk(action: str):
    if not can_manage_sync(current_user):
        abort(403)
    if action not in {"keep_old", "apply_new"}:
        abort(400)
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    conflicts = (
        SyncConflict.query.join(Task, SyncConflict.task_id == Task.id)
        .filter(SyncConflict.status == "pending", Task.project_id == project.id)
        .all()
    )
    changed = 0
    for conflict in conflicts:
        if action == "apply_new":
            _apply_sync_conflict_new_value(conflict)
        conflict.status = action
        conflict.resolved_at = datetime.utcnow()
        conflict.resolved_by_user_id = current_user.id
        changed += 1
    db.session.commit()
    flash(f"Готово: обработано несостыковок {changed}", "success")
    return redirect(url_for("main.sync_conflicts"))


@bp.route("/tasks/<int:task_id>/inline-text", methods=["POST"])
@login_required
def inline_update_text(task_id: int):
    project = selected_project()
    if project is None:
        return redirect(url_for("main.objects"))
    task = db.session.get(Task, task_id) or abort(404)
    if task.project_id != project.id:
        abort(404)
    if not can_change_task(current_user, task):
        abort(403)
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()
    task.description = text or None
    task.manually_edited = True
    db.session.commit()
    return jsonify({"ok": True, "text": task.description or ""})
