from __future__ import annotations

import json
import hashlib
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

TASK_FIELDS_WITHOUT_SOURCE_UID = [field for field in TASK_FIELDS if field != "source_uid"]
SOURCE_UID_MAX_LENGTH = 64
SOURCE_UID_QUERY_BATCH_SIZE = 500

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


def _snapshot_payload(log: SyncLog | None) -> dict[str, Any]:
    if log is None or not log.rollback_data:
        return {}
    try:
        payload = json.loads(log.rollback_data)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _next_snapshot_log(log: SyncLog, project_id: int) -> SyncLog | None:
    if not log.started_at:
        return None
    return (
        SyncLog.query.filter(
            SyncLog.project_id == project_id,
            SyncLog.id != log.id,
            SyncLog.started_at > log.started_at,
            SyncLog.rollback_data.isnot(None),
        )
        .order_by(SyncLog.started_at.asc(), SyncLog.id.asc())
        .first()
    )


def _hash_token(*parts: Any, length: int = 16) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:length]


def _temporary_source_uid(project_id: int, task_id: int) -> str:
    return f"rbtmp-{project_id}-{task_id}-{_hash_token(project_id, task_id)}"[:SOURCE_UID_MAX_LENGTH]


def _fallback_source_uid(project_id: int, task_id: int, original_uid: str | None) -> str:
    return f"rbuid-{project_id}-{task_id}-{_hash_token(original_uid, project_id, task_id)}"[:SOURCE_UID_MAX_LENGTH]


def _source_uid_variant(base: str, attempt: int) -> str:
    base = str(base or "").strip()[:SOURCE_UID_MAX_LENGTH]
    if not base:
        base = _hash_token("empty-source-uid", attempt, length=SOURCE_UID_MAX_LENGTH)
    if attempt <= 0:
        return base
    suffix = f"-{attempt}-{_hash_token(base, attempt, length=8)}"
    return f"{base[:SOURCE_UID_MAX_LENGTH - len(suffix)]}{suffix}"


def _source_uid_exists(source_uid: str, *, owner_task_id: int | None = None) -> bool:
    query = Task.query.filter(Task.source_uid == source_uid)
    if owner_task_id is not None:
        query = query.filter(Task.id != owner_task_id)
    with db.session.no_autoflush:
        return query.first() is not None


def _reserve_snapshot_source_uid(
    candidate: str,
    reserved: set[str],
    *,
    project_id: int,
    task_id: int,
) -> str:
    base = str(candidate or "").strip()[:SOURCE_UID_MAX_LENGTH]
    if not base:
        base = _fallback_source_uid(project_id, task_id, candidate)
    for attempt in range(1000):
        source_uid = _source_uid_variant(base, attempt)
        if source_uid not in reserved:
            reserved.add(source_uid)
            return source_uid
    source_uid = _fallback_source_uid(project_id, task_id, base)
    reserved.add(source_uid)
    return source_uid


def _reserve_database_source_uid(
    candidate: str,
    reserved: set[str] | None = None,
    *,
    owner_task_id: int | None = None,
) -> str:
    base = str(candidate or "").strip()[:SOURCE_UID_MAX_LENGTH]
    if not base:
        base = _hash_token("restored-source-uid", owner_task_id, length=SOURCE_UID_MAX_LENGTH)
    reserved = reserved if reserved is not None else set()
    for attempt in range(1000):
        source_uid = _source_uid_variant(base, attempt)
        if source_uid in reserved:
            continue
        if not _source_uid_exists(source_uid, owner_task_id=owner_task_id):
            reserved.add(source_uid)
            return source_uid
    fallback = _source_uid_variant(_hash_token("restored-source-uid", base, owner_task_id, length=SOURCE_UID_MAX_LENGTH), 0)
    reserved.add(fallback)
    return fallback


def _iter_batches(values: list[str], batch_size: int = SOURCE_UID_QUERY_BATCH_SIZE):
    for index in range(0, len(values), batch_size):
        yield values[index : index + batch_size]


def _snapshot_task_source_uids(project_id: int, task_snapshots: dict[int, dict[str, Any]]) -> dict[int, str]:
    reserved: set[str] = set()
    source_uids: dict[int, str] = {}
    for task_id, snapshot in task_snapshots.items():
        source_uid = str(snapshot.get("source_uid") or "").strip()
        if not source_uid:
            source_uid = _fallback_source_uid(project_id, task_id, source_uid)
        source_uids[task_id] = _reserve_snapshot_source_uid(
            source_uid,
            reserved,
            project_id=project_id,
            task_id=task_id,
        )
    return source_uids


def _prepare_task_source_uid_restore(
    project_id: int,
    task_snapshots: dict[int, dict[str, Any]],
) -> dict[int, str]:
    """Free snapshot source_uid values before restoring task rows.

    During sync rollback the same source_uid can temporarily belong to another
    row (for example after sentence splitting or a later sync). Updating rows
    directly then violates the global unique constraint on tasks.source_uid.
    The rollback therefore moves existing snapshot rows to temporary UIDs,
    removes same-project blockers that are not in the target snapshot, and only
    then restores the final source_uid values.
    """
    source_uids_by_task = _snapshot_task_source_uids(project_id, task_snapshots)
    if not source_uids_by_task:
        return {}

    task_ids_before = set(task_snapshots)
    temporary_uids: set[str] = set()
    for task_id in task_ids_before:
        task = db.session.get(Task, task_id)
        if task is None:
            continue
        task.source_uid = _reserve_database_source_uid(
            _temporary_source_uid(project_id, task_id),
            temporary_uids,
            owner_task_id=task.id,
        )
    db.session.flush()

    uid_to_task_id = {source_uid: task_id for task_id, source_uid in source_uids_by_task.items()}
    reserved_final_uids = set(source_uids_by_task.values())
    for batch in _iter_batches(list(uid_to_task_id)):
        with db.session.no_autoflush:
            blockers = Task.query.filter(Task.source_uid.in_(batch)).all()
        for blocker in blockers:
            intended_task_id = uid_to_task_id.get(blocker.source_uid)
            if intended_task_id is None or blocker.id == intended_task_id:
                continue
            if blocker.project_id == project_id:
                if blocker.id not in task_ids_before:
                    db.session.delete(blocker)
                else:
                    blocker.source_uid = _reserve_database_source_uid(
                        _temporary_source_uid(project_id, blocker.id),
                        temporary_uids,
                        owner_task_id=blocker.id,
                    )
                continue

            old_source_uid = source_uids_by_task[intended_task_id]
            reserved_final_uids.discard(old_source_uid)
            source_uids_by_task[intended_task_id] = _reserve_database_source_uid(
                _fallback_source_uid(project_id, intended_task_id, old_source_uid),
                reserved_final_uids,
                owner_task_id=intended_task_id,
            )
    db.session.flush()
    return source_uids_by_task


def _project_conflicts_query(project_id: int, started_at: datetime, end_at: datetime | None = None):
    start = started_at - timedelta(seconds=5)
    query = (
        SyncConflict.query.outerjoin(Task, SyncConflict.task_id == Task.id)
        .outerjoin(Apartment, SyncConflict.apartment_id == Apartment.id)
        .filter(SyncConflict.created_at >= start)
        .filter(or_(Task.project_id == project_id, Apartment.project_id == project_id))
    )
    if end_at is not None:
        query = query.filter(SyncConflict.created_at < end_at)
    return query


def apply_sync_rollback(log: SyncLog) -> tuple[bool, str]:
    """Откатывает синхронизацию и возвращает (успешно, сообщение)."""
    if log.rolled_back_at:
        return False, "Эта синхронизация уже была откатана"
    if log.rollback_data:
        return _rollback_from_snapshot(log)
    return _rollback_from_legacy_change_log(log)


def _rollback_from_snapshot(log: SyncLog) -> tuple[bool, str]:
    payload = _snapshot_payload(log)
    if not payload:
        return False, "Откат невозможен: данные восстановления повреждены"

    project_id = int(log.project_id or payload.get("project_id") or 0)
    if not project_id:
        return False, "Откат невозможен: синхронизация не привязана к объекту"

    next_log = _next_snapshot_log(log, project_id)
    next_payload = _snapshot_payload(next_log)
    if next_payload:
        payload = next_payload

    apartment_snapshots = {int(row["id"]): row for row in payload.get("apartments", []) if row.get("id") is not None}
    task_snapshots = {int(row["id"]): row for row in payload.get("tasks", []) if row.get("id") is not None}
    apartment_ids_before = set(apartment_snapshots)
    task_ids_before = set(task_snapshots)

    # Убираем несостыковки, которые появились во время откатываемой загрузки.
    deleted_conflicts = 0
    conflict_end = next_log.started_at if next_payload and next_log is not None else None
    for conflict in _project_conflicts_query(project_id, log.started_at or datetime.utcnow(), end_at=conflict_end).all():
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

    source_uids_by_task = _prepare_task_source_uid_restore(project_id, task_snapshots)
    restored_final_uids: set[str] = set()
    restored_tasks = 0
    for task_id, snapshot in task_snapshots.items():
        task = db.session.get(Task, task_id)
        if task is None:
            # Восстанавливаем удаленную задачу только если ее помещение и пункт существуют.
            apartment = db.session.get(Apartment, int(snapshot.get("apartment_id") or 0))
            work_point = db.session.get(WorkPoint, int(snapshot.get("work_point_id") or 0))
            if apartment is None or work_point is None:
                continue
            task = Task(
                id=task_id,
                source_uid=_reserve_database_source_uid(
                    _temporary_source_uid(project_id, task_id),
                    owner_task_id=task_id,
                ),
                project_id=project_id,
                apartment_id=apartment.id,
                work_point_id=work_point.id,
            )
            db.session.add(task)
        _restore_fields(task, snapshot, TASK_FIELDS_WITHOUT_SOURCE_UID)
        task.source_uid = _reserve_database_source_uid(
            source_uids_by_task.get(task_id) or _fallback_source_uid(project_id, task_id, None),
            restored_final_uids,
            owner_task_id=task.id or task_id,
        )
        restored_tasks += 1

    from app.services.remark_entities import migrate_existing_compound_tasks

    split_result = migrate_existing_compound_tasks(force=True, project_id=project_id, commit=False)

    log.rolled_back_at = datetime.utcnow()
    log.rollback_note = None
    db.session.commit()
    return (
        True,
        f"Синхронизация откатана: восстановлено квартир/помещений {restored_apartments}, замечаний {restored_tasks}, удалено новых замечаний {deleted_tasks}, удалено новых помещений {deleted_apartments}, несостыковок {deleted_conflicts}, заново разделено составных замечаний {split_result.get('split_tasks', 0)}.",
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
