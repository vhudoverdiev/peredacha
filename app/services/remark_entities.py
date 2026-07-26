from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_

from app import db
from app.models import AppSetting, ChangeLog, Task
from app.services.uid_service import (
    build_source_fragment_uid,
    cell_hash,
    split_cell_remarks,
    stable_hash,
)


MIGRATION_SETTING_KEY = "remark_sentence_entities_v2"
EXCLUDED_SOURCE_SHEETS = {"apartment_history", "manual_glass_repeat"}


def _effective_text(task: Task) -> str:
    return str(task.description or task.source_cell_value or "").strip()


def _fragment_uid(
    task: Task,
    original_uid: str,
    fragment_index: int,
    *,
    preserve_source_identity: bool,
) -> str:
    if (
        preserve_source_identity
        and
        task.project
        and task.source_sheet_name
        and task.source_row_index is not None
        and task.source_column_index is not None
        and task.source_sheet_name not in EXCLUDED_SOURCE_SHEETS
        and not task.source_sheet_name.startswith("manual")
    ):
        return build_source_fragment_uid(
            task.project.name,
            task.source_sheet_name,
            task.source_row_index,
            task.source_column_index,
            fragment_index,
        )
    if fragment_index == 0:
        return original_uid
    return stable_hash(["task-fragment-v1", original_uid, str(fragment_index)])


def _copy_task_fragment(
    task: Task,
    *,
    source_uid: str,
    text: str,
    source_cell_value: str | None = None,
    source_hash: str | None = None,
    preserve_source_identity: bool,
) -> Task:
    return Task(
        source_uid=source_uid,
        project_id=task.project_id,
        apartment_id=task.apartment_id,
        work_point_id=task.work_point_id,
        title=task.title,
        description=text,
        source_cell_value=source_cell_value if source_cell_value is not None else text,
        responsible_id=task.responsible_id,
        status=task.status,
        priority=task.priority,
        planned_date=task.planned_date,
        completed_date=task.completed_date,
        comment=task.comment,
        source_sheet_name=task.source_sheet_name if preserve_source_identity else "manual_split",
        source_row_index=task.source_row_index if preserve_source_identity else None,
        source_column_index=task.source_column_index if preserve_source_identity else None,
        source_cell_address=task.source_cell_address if preserve_source_identity else None,
        source_hash=source_hash or cell_hash(text),
        is_done=task.is_done,
        is_archived=False,
        is_missing_in_latest_sync=task.is_missing_in_latest_sync,
        manually_edited=task.manually_edited or not preserve_source_identity,
        last_seen_at=task.last_seen_at,
    )


def split_task_into_entities(
    task: Task,
    *,
    action: str = "automatic_sentence_split",
    preserve_source_identity: bool = True,
) -> list[Task]:
    """Turn one compound task into independent task rows.

    The original row is retained for the first fragment so comments, history,
    measurements and material links remain attached to an existing task.
    """
    if task.is_archived or (task.source_sheet_name or "") in EXCLUDED_SOURCE_SHEETS:
        return [task]

    original_text = _effective_text(task)
    original_source_cell_value = str(task.source_cell_value or original_text).strip()
    original_source_hash = task.source_hash or cell_hash(original_source_cell_value)
    fragments = split_cell_remarks(original_text)
    if len(fragments) <= 1:
        return [task]

    original_uid = task.source_uid
    created: list[Task] = [task]
    first_uid = _fragment_uid(
        task,
        original_uid,
        0,
        preserve_source_identity=preserve_source_identity,
    )
    uid_owner = Task.query.filter(Task.source_uid == first_uid, Task.id != task.id).first()
    if uid_owner is None:
        task.source_uid = first_uid
    task.description = fragments[0]
    if preserve_source_identity:
        task.source_cell_value = original_source_cell_value
        task.source_hash = original_source_hash
    else:
        task.source_cell_value = fragments[0]
        task.source_hash = cell_hash(fragments[0])
    task.manually_edited = bool(task.manually_edited)

    db.session.add(
        ChangeLog(
            task_id=task.id,
            action=action,
            field_name="description",
            old_value=original_text,
            new_value=fragments[0],
        )
    )

    for fragment_index, fragment in enumerate(fragments[1:], start=1):
        source_uid = _fragment_uid(
            task,
            original_uid,
            fragment_index,
            preserve_source_identity=preserve_source_identity,
        )
        existing = Task.query.filter_by(source_uid=source_uid).first()
        if existing is not None:
            existing.description = fragment
            existing.source_cell_value = fragment
            existing.source_hash = cell_hash(fragment)
            created.append(existing)
            continue
        sibling = _copy_task_fragment(
            task,
            source_uid=source_uid,
            text=fragment,
            source_cell_value=original_source_cell_value if preserve_source_identity else None,
            source_hash=original_source_hash if preserve_source_identity else None,
            preserve_source_identity=preserve_source_identity,
        )
        db.session.add(sibling)
        db.session.flush()
        db.session.add(
            ChangeLog(
                task_id=sibling.id,
                action=f"{action}_created",
                field_name="description",
                old_value="",
                new_value=fragment,
            )
        )
        created.append(sibling)
    db.session.flush()
    return created


def migrate_existing_compound_tasks(*, force: bool = False) -> dict[str, int]:
    """Idempotently split legacy compound tasks once for an existing database."""
    setting = AppSetting.query.filter_by(key=MIGRATION_SETTING_KEY).first()
    if setting is not None and not force:
        return {"split_tasks": 0, "created_tasks": 0, "skipped_conflicts": 0}

    split_tasks = 0
    created_tasks = 0
    skipped_conflicts = 0
    tasks = (
        Task.query.filter(Task.is_archived.is_(False))
        .filter(
            or_(
                Task.source_sheet_name.is_(None),
                ~Task.source_sheet_name.in_(EXCLUDED_SOURCE_SHEETS),
            )
        )
        .order_by(Task.id.asc())
        .all()
    )
    for task in tasks:
        fragments = split_cell_remarks(_effective_text(task))
        if len(fragments) <= 1:
            continue
        split_rows = split_task_into_entities(task)
        split_tasks += 1
        created_tasks += max(0, len(split_rows) - 1)

    if setting is None:
        setting = AppSetting(key=MIGRATION_SETTING_KEY)
        db.session.add(setting)
    setting.value = (
        f"{datetime.now(timezone.utc).isoformat()}|split={split_tasks}|"
        f"created={created_tasks}|skipped_conflicts={skipped_conflicts}"
    )
    db.session.commit()
    return {
        "split_tasks": split_tasks,
        "created_tasks": created_tasks,
        "skipped_conflicts": skipped_conflicts,
    }
