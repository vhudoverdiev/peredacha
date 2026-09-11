from __future__ import annotations

from datetime import date
from typing import Any

from app import db
from app.models import Apartment, Task, WorkPoint
from app.services.task_service import is_apartment_unsold

MAIN_POINT_NUMBERS = {str(n) for n in range(10, 23)}
WALL_POINT_NUMBERS = {"11"}
PRIMARY_STATUS_NOT_READY = "not_ready"
PRIMARY_STATUS_THROWN = "thrown"
PRIMARY_STATUS_LABELS = {
    PRIMARY_STATUS_NOT_READY: "не готова",
    PRIMARY_STATUS_THROWN: "кинута",
}
PRIMARY_STATUS_CLASSES = {
    PRIMARY_STATUS_NOT_READY: "warning",
    PRIMARY_STATUS_THROWN: "danger",
}


def task_text(task: Task) -> str:
    return (task.description or task.source_cell_value or "").strip()


def point_number(task: Task) -> str:
    return str(task.work_point.point_number if task.work_point else "").strip()


def point_name(task: Task) -> str:
    if not task.work_point:
        return "Без пункта"
    return task.work_point.display_name


def is_main_task(task: Task) -> bool:
    return point_number(task) in MAIN_POINT_NUMBERS and bool(task_text(task))


def is_wall_task(task: Task) -> bool:
    name = point_name(task).lower()
    return point_number(task) in WALL_POINT_NUMBERS or "стен" in name


def is_waiting(apartment: Apartment) -> bool:
    # В текущей CRM режим "ждет" определяется отсутствием срока/даты передачи.
    return apartment.deadline_date is None


def is_unsold(apartment: Apartment) -> bool:
    """Непроданное помещение определяется явным флагом/текстом «не продано», а не пустым ФИО."""
    return is_apartment_unsold(apartment)


def primary_status(apartment: Apartment) -> str:
    status = (getattr(apartment, "primary_status", None) or "").strip()
    return status if status in PRIMARY_STATUS_LABELS else PRIMARY_STATUS_NOT_READY


def primary_status_label(apartment: Apartment) -> str:
    return PRIMARY_STATUS_LABELS.get(primary_status(apartment), PRIMARY_STATUS_LABELS[PRIMARY_STATUS_NOT_READY])


def primary_status_class(apartment: Apartment) -> str:
    return PRIMARY_STATUS_CLASSES.get(primary_status(apartment), "secondary")


def apartment_sort_key(apartment: Apartment) -> tuple[int, int, str]:
    number = (apartment.apartment_number or apartment.construction_number or "").strip()
    digits = "".join(ch for ch in number if ch.isdigit())
    if digits:
        return (0, int(digits), number)
    return (1, 0, number.lower())


def task_sort_key(task: Task) -> tuple[int, int, int, str]:
    point = point_number(task)
    done_rank = 1 if task.is_done else 0
    if point.isdigit():
        return (done_rank, 0, int(point), task_text(task).lower())
    return (done_rank, 1, 0, task_text(task).lower())


def deadline_marker(apartment: Apartment, today: date | None = None) -> dict[str, Any] | None:
    if not apartment.deadline_date:
        return None
    today = today or date.today()
    days_left = (apartment.deadline_date - today).days
    if days_left < 5:
        return {"code": "expired", "label": "истёк", "days_left": days_left, "class": "danger"}
    if days_left <= 15:
        return {"code": "expiring", "label": "истекает", "days_left": days_left, "class": "warning"}
    return None


def apartment_task_rows(project_id: int) -> list[Apartment]:
    apartments = Apartment.query.filter(Apartment.project_id == project_id).all()
    return sorted(apartments, key=apartment_sort_key)


def apartment_main_tasks(apartment: Apartment) -> list[Task]:
    tasks = [task for task in apartment.tasks if is_main_task(task) and not task.is_archived]
    return sorted(tasks, key=task_sort_key)


def apartment_all_tasks(apartment: Apartment) -> list[Task]:
    tasks = [task for task in apartment.tasks if task_text(task) and not task.is_archived]
    return sorted(tasks, key=task_sort_key)


def apartment_stats(apartment: Apartment, tasks: list[Task] | None = None) -> dict[str, Any]:
    tasks = tasks if tasks is not None else apartment_main_tasks(apartment)
    total = len(tasks)
    done = sum(1 for task in tasks if task.is_done)
    left = max(total - done, 0)
    percent = round(done / total * 100, 1) if total else 0
    return {"total": total, "done": done, "left": left, "percent": percent}


def build_po_rows(project_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for apartment in apartment_task_rows(project_id):
        if not is_waiting(apartment):
            continue
        tasks = apartment_main_tasks(apartment)
        if not tasks:
            continue
        stats = apartment_stats(apartment, tasks)
        wall_tasks = [task for task in tasks if is_wall_task(task)]
        wall_done = bool(wall_tasks) and all(task.is_done for task in wall_tasks)
        percent_ready = stats["percent"] > 60
        if not (wall_done or percent_ready):
            continue
        done_tasks = [task for task in tasks if task.is_done]
        left_tasks = [task for task in tasks if not task.is_done]
        rows.append(
            {
                "apartment": apartment,
                "tasks": tasks,
                "done_tasks": done_tasks,
                "left_tasks": left_tasks,
                "stats": stats,
                "reason": "стены выполнены" if wall_done else "готовность более 60%",
            }
        )
    return rows


def build_60kd_rows(project_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for apartment in apartment_task_rows(project_id):
        if not apartment.deadline_date:
            continue
        tasks = apartment_main_tasks(apartment)
        if not tasks:
            continue
        stats = apartment_stats(apartment, tasks)
        rows.append(
            {
                "apartment": apartment,
                "tasks": tasks,
                "done_tasks": [task for task in tasks if task.is_done],
                "left_tasks": [task for task in tasks if not task.is_done],
                "stats": stats,
                "deadline_marker": deadline_marker(apartment),
            }
        )
    return sorted(rows, key=lambda row: (row["apartment"].deadline_date or date.max, apartment_sort_key(row["apartment"])))


def primary_archive_reason(apartment: Apartment, tasks: list[Task]) -> str | None:
    if apartment.deadline_date:
        return "квартира принята"
    if tasks:
        return "появились замечания"
    return None


def build_primary_rows(project_id: int, archived: bool = False) -> list[dict[str, Any]]:
    """
    Первичный раздел:
    - актив: проданные квартиры без замечаний и без принятия;
    - архив: проданные квартиры, которые ушли из актива, потому что появились замечания или квартира принята.
    Непроданные квартиры не показываем вообще.
    """
    rows: list[dict[str, Any]] = []
    for apartment in apartment_task_rows(project_id):
        if is_unsold(apartment):
            continue
        tasks = apartment_all_tasks(apartment)
        reason = primary_archive_reason(apartment, tasks)
        is_archived_primary = reason is not None
        if archived != is_archived_primary:
            continue
        rows.append(
            {
                "apartment": apartment,
                "tasks": tasks,
                "stats": apartment_stats(apartment, apartment_main_tasks(apartment)),
                "primary_status": primary_status(apartment),
                "primary_status_label": primary_status_label(apartment),
                "primary_status_class": primary_status_class(apartment),
                "archive_reason": reason,
            }
        )
    return rows


def update_primary_state(apartment: Apartment, status: str, comment: str) -> None:
    apartment.primary_status = status if status in PRIMARY_STATUS_LABELS else PRIMARY_STATUS_NOT_READY
    apartment.primary_comment = (comment or "").strip() or None
    db.session.commit()


def notification_counts(project_id: int | None) -> dict[str, int]:
    if not project_id:
        return {"kd60": 0, "primary": 0}
    kd60_rows = build_60kd_rows(project_id)
    kd60_alerts = [row for row in kd60_rows if row.get("deadline_marker")]
    primary_rows = build_primary_rows(project_id, archived=False)
    return {"kd60": len(kd60_alerts), "primary": len(primary_rows)}
