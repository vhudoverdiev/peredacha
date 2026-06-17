from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import or_

from app import db
from app.models import Apartment, ChangeLog, SyncConflict, SyncLog, Task, WorkPoint


APARTMENT_FIELDS = [
    "id",
    "project_id",
    "apartment_number",
    "construction_number",
    "owner_name",
    "is_unsold",
    "phone",
    "finishing_type",
    "premise_type",
    "building",
    "entrance",
    "floor",
    "inspection_date",
    "first_inspection_date",
    "first_inspection_present",
    "reinspection_date",
    "deadline_date",
    "remark_deadline_date",
    "inspection_note",
    "is_app_mode",
    "po_status",
    "po_status_manual",
    "avr_archived_at",
    "avr_status",
    "avr_signed_date",
    "app_deadline_date",
    "app_deadline_raw",
    "app_deadline_status",
    "comment",
    "source_row_id",
]

TASK_FIELDS = [
    "id",
    "source_uid",
    "project_id",
    "apartment_id",
    "work_point_id",
    "title",
    "description",
    "source_cell_value",
    "responsible_id",
    "status",
    "priority",
    "planned_date",
    "completed_date",
    "comment",
    "source_sheet_name",
    "source_row_index",
    "source_column_index",
    "source_cell_address",
    "source_hash",
    "is_done",
    "is_archived",
    "is_missing_in_latest_sync",
    "manually_edited",
    "last_seen_at",
]

DATE_FIELDS = {
    "inspection_date",
    "first_inspection_date",
    "reinspection_date",
    "deadline_date",
    "remark_deadline_date",
    "avr_signed_date",
    "app_deadline_date",
    "planned_date",
}
DATETIME_FIELDS = {"completed_date", "last_seen_at", "avr_archived_at"}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _deserialize_value(field_name: str, value: Any) -> Any:
    if value in (None, ""):
        return None if field_name in DATE_FIELDS or field_name in DATETIME_FIELDS else value
    if field_name in DATE_FIELDS:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    if field_name in DATETIME_FIELDS:
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return value


def _snapshot_row(obj: Any, fields: list[str]) -> dict[str, Any]:
    return {field: _serialize_value(getattr(obj, field)) for field in fields}


def build_project_rollback_data(project_id: int | None) -> str:
    """Сохраняет состояние объекта перед синхронизацией.

    Это нужно, чтобы кнопка «Откатить» не была декоративной: после импорта можно
    вернуть квартиры и замечания к состоянию до загрузки таблицы.
    """
    apartments: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    if project_id:
        apartments = [_snapshot_row(row, APARTMENT_FIELDS) for row in Apartment.query.filter_by(project_id=project_id).all()]
        tasks = [_snapshot_row(row, TASK_FIELDS) for row in Task.query.filter_by(project_id=project_id).all()]
    payload = {
        "version": 1,
        "created_at_utc": datetime.utcnow().isoformat(),
        "project_id": project_id,
        "apartments": apartments,
        "tasks": tasks,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _restore_fields(obj: Any, snapshot: dict[str, Any], fields: list[str]) -> None:
    for field in fields:
        if field == "id":
            continue
        if field in snapshot:
            setattr(obj, field, _deserialize_value(field, snapshot[field]))


def _project_conflicts_query(project_id: int, started_at: datetime):
    start = started_at - timedelta(seconds=5)
    return (
        SyncConflict.query.outerjoin(Task, SyncConflict.task_id == Task.id)
        .outerjoin(Apartment, SyncConflict.apartment_id == Apartment.id)
        .filter(SyncConflict.created_at >= start)
        .filter(or_(Task.project_id == project_id, Apartment.project_id == project_id))
    )


def apply_sync_rollback(log: SyncLog) -> tuple[bool, str]:
    """Откатывает синхронизацию и возвращает (успешно, сообщение)."""
    if log.rolled_back_at:
        return False, "Эта синхронизация уже была откатана"
    if log.rollback_data:
        return _rollback_from_snapshot(log)
    return _rollback_from_legacy_change_log(log)


def _rollback_from_snapshot(log: SyncLog) -> tuple[bool, str]:
    try:
        payload = json.loads(log.rollback_data or "{}")
    except json.JSONDecodeError:
        return False, "Откат невозможен: данные восстановления повреждены"

    project_id = int(log.project_id or payload.get("project_id") or 0)
    if not project_id:
        return False, "Откат невозможен: синхронизация не привязана к объекту"

    apartment_snapshots = {int(row["id"]): row for row in payload.get("apartments", []) if row.get("id") is not None}
    task_snapshots = {int(row["id"]): row for row in payload.get("tasks", []) if row.get("id") is not None}
    apartment_ids_before = set(apartment_snapshots)
    task_ids_before = set(task_snapshots)
    start = (log.started_at or datetime.utcnow()) - timedelta(seconds=5)

    # Убираем несостыковки, которые появились во время откатываемой загрузки.
    deleted_conflicts = 0
    for conflict in _project_conflicts_query(project_id, log.started_at or datetime.utcnow()).all():
        db.session.delete(conflict)
        deleted_conflicts += 1
    db.session.flush()

    # Снимок является источником истины: после отката в объекте должны остаться
    # только те задачи и помещения, которые были до выбранной загрузки.
    # Старое ограничение по created_at могло пропустить строки последней загрузки,
    # из-за чего после отката последней таблицы дашборд не обнулялся.
    new_tasks_query = Task.query.filter(Task.project_id == project_id)
    if task_ids_before:
        new_tasks_query = new_tasks_query.filter(~Task.id.in_(task_ids_before))
    deleted_tasks = 0
    for task in new_tasks_query.all():
        db.session.delete(task)
        deleted_tasks += 1
    db.session.flush()

    new_apartments_query = Apartment.query.filter(Apartment.project_id == project_id)
    if apartment_ids_before:
        new_apartments_query = new_apartments_query.filter(~Apartment.id.in_(apartment_ids_before))
    deleted_apartments = 0
    for apartment in new_apartments_query.all():
        db.session.delete(apartment)
        deleted_apartments += 1
    db.session.flush()

    restored_apartments = 0
    for apartment_id, snapshot in apartment_snapshots.items():
        apartment = db.session.get(Apartment, apartment_id)
        if apartment is None:
            apartment = Apartment(id=apartment_id, project_id=project_id)
            db.session.add(apartment)
        _restore_fields(apartment, snapshot, APARTMENT_FIELDS)
        restored_apartments += 1

    restored_tasks = 0
    for task_id, snapshot in task_snapshots.items():
        task = db.session.get(Task, task_id)
        if task is None:
            # Восстанавливаем удаленную задачу только если ее помещение и пункт существуют.
            apartment = db.session.get(Apartment, int(snapshot.get("apartment_id") or 0))
            work_point = db.session.get(WorkPoint, int(snapshot.get("work_point_id") or 0))
            if apartment is None or work_point is None:
                continue
            task = Task(id=task_id, source_uid=snapshot.get("source_uid") or f"restored-{task_id}", project_id=project_id, apartment_id=apartment.id, work_point_id=work_point.id)
            db.session.add(task)
        _restore_fields(task, snapshot, TASK_FIELDS)
        restored_tasks += 1

    log.rolled_back_at = datetime.utcnow()
    log.rollback_note = None
    db.session.commit()
    return (
        True,
        f"Синхронизация откатана: восстановлено квартир/помещений {restored_apartments}, замечаний {restored_tasks}, удалено новых замечаний {deleted_tasks}, удалено новых помещений {deleted_apartments}, несостыковок {deleted_conflicts}.",
    )


def _rollback_from_legacy_change_log(log: SyncLog) -> tuple[bool, str]:
    """Мягкий откат старых записей, где еще не было полного снимка восстановления."""
    project_id = int(log.project_id or 0)
    if not project_id:
        return False, "Откат невозможен: синхронизация не привязана к объекту"

    start = (log.started_at or datetime.utcnow()) - timedelta(seconds=5)
    finish = (log.finished_at or datetime.utcnow()) + timedelta(seconds=5)
    changes = (
        ChangeLog.query.join(Task, ChangeLog.task_id == Task.id)
        .filter(Task.project_id == project_id, ChangeLog.created_at >= start, ChangeLog.created_at <= finish)
        .order_by(ChangeLog.id.desc())
        .all()
    )
    if not changes:
        return False, "Откат невозможен: для этой старой синхронизации нет данных восстановления"

    restored_missing = 0
    deleted_tasks = 0
    for change in changes:
        task = db.session.get(Task, change.task_id)
        if task is None:
            continue
        if change.action == "created_from_sync" and task.created_at >= start:
            db.session.delete(task)
            deleted_tasks += 1
        elif change.action == "missing_in_latest_sync" and change.field_name == "is_missing_in_latest_sync":
            task.is_missing_in_latest_sync = False
            restored_missing += 1

    log.rolled_back_at = datetime.utcnow()
    log.rollback_note = None
    db.session.commit()
    return True, f"Старая синхронизация частично откатана: удалено новых замечаний {deleted_tasks}, возвращено пропавших {restored_missing}. Для полного отката следующих загрузок теперь сохраняется снимок восстановления."
