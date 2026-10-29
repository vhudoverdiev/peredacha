"""Versioned, idempotent worker status operations. No offline credentials are stored."""
import hashlib
import json
from uuid import UUID
from flask import jsonify, request
from flask_login import current_user
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import Task, ChangeLog, WorkerOfflineOperation
from app.time_utils import utc_now
from app.services.task_service import change_task_status

ROLES = {'painter', 'glazier', 'handyman'}
STATUSES = ['not_started', 'in_progress', 'done']
_UNSET = object()


def version(task, history=_UNSET):
    if history is _UNSET:
        history = db.session.query(func.max(ChangeLog.id)).filter(ChangeLog.task_id == task.id).scalar()
    values = [task.id, task.source_uid, task.status, task.is_done, task.responsible_id,
              task.updated_at.isoformat() if task.updated_at else '', task.planned_date,
              task.priority, task.description, task.title, task.comment, task.project_id, task.apartment_id, task.work_point_id, task.is_archived, task.is_missing_in_latest_sync, history]
    return hashlib.sha256(json.dumps(values, default=str, ensure_ascii=False).encode()).hexdigest()


def serialize(task, history=_UNSET):
    return dict(id=task.id, title=task.title or '', description=task.description or task.source_cell_value or '',
                status=task.status, allowed_statuses=STATUSES if task.status in STATUSES else [],
                version=version(task, history), priority=task.priority, deadline=str(task.planned_date or ''),
                project_id=task.project_id, project=task.project.name, address=task.project.address or '',
                apartment=task.apartment.label() if task.apartment else 'Без помещения')


def error(code, message, status, **extra):
    return jsonify(ok=False, code=code, message=message, **extra), status


def apply_operation():
    if not current_user.is_authenticated:
        return error('auth_required', 'Войдите в тот же аккаунт для отправки сохранённых изменений.', 401)
    if current_user.role not in ROLES:
        return error('access_revoked', 'Право изменения задачи отозвано.', 403)
    payload = request.get_json(silent=True) or {}
    try:
        operation_id = str(UUID(str(payload['operation_id'])))
        task_id = int(payload['task_id'])
        account_id = int(payload['account_id'])
    except (ValueError, KeyError, TypeError):
        return error('invalid_operation', 'Некорректная операция.', 400)
    if account_id != current_user.id:
        return error('wrong_account', 'Войдите в аккаунт, в котором сохранены изменения.', 403)
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    existing = db.session.get(WorkerOfflineOperation, operation_id)
    if existing:
        if existing.user_id != current_user.id or existing.request_hash != fingerprint:
            return error('operation_reused', 'Идентификатор операции уже использован.', 409)
        return jsonify(json.loads(existing.response_json))
    task = Task.query.filter_by(id=task_id).with_for_update().first()
    if task is None or task.is_archived or task.is_missing_in_latest_sync:
        return error('task_removed', 'Задача удалена или больше недоступна.', 410)
    if task.responsible_id != current_user.id or not current_user.can_access_project(task.project):
        return error('task_reassigned', 'Задача переназначена или доступ к объекту отозван.', 403)
    status = payload.get('new_status')
    if status not in STATUSES or task.status not in STATUSES:
        return error('transition_forbidden', 'Этот переход требует проверки в CRM.', 422)
    if payload.get('version') != version(task) or payload.get('previous_status') != task.status:
        return error('conflict', 'Задача изменена на сервере. Проверьте актуальные данные.', 409, task=serialize(task))
    # Reserve the row using a compare-and-swap as well as FOR UPDATE (SQLite has no row locks).
    old_updated = task.updated_at
    reserved = db.session.execute(update(Task).where(Task.id == task.id, Task.updated_at == old_updated,
                                 Task.status == task.status, Task.responsible_id == current_user.id)
                                 .values(updated_at=utc_now()).execution_options(synchronize_session=False))
    if reserved.rowcount != 1:
        db.session.rollback()
        return error('conflict', 'Задача изменилась во время отправки. Обновите её.', 409)
    db.session.expire(task)
    change_task_status(task, status, user_id=current_user.id, commit=False)
    db.session.flush()
    # Read database precision back (MySQL may store DATETIME without microseconds).
    db.session.refresh(task)
    result = dict(ok=True, operation_id=operation_id, task=serialize(task), synchronized_at=utc_now().isoformat()+'Z')
    db.session.add(WorkerOfflineOperation(id=operation_id, user_id=current_user.id, task_id=task.id,
                                        request_hash=fingerprint, response_json=json.dumps(result, ensure_ascii=False)))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = db.session.get(WorkerOfflineOperation, operation_id)
        if existing and existing.user_id == current_user.id and existing.request_hash == fingerprint:
            return jsonify(json.loads(existing.response_json))
        return error('operation_reused', 'Операция уже обработана. Обновите список задач.', 409)
    return jsonify(result)
