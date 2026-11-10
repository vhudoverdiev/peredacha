"""Record committed CRM data changes without copying field values."""
from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models import CrmAuditLog
from app.time_utils import utc_now


EXCLUDED_TABLES = {
    "crm_audit_logs", "change_logs", "deletion_action_logs", "security_events",
    "site_visits", "sync_logs", "worker_offline_operations",
}
IGNORED_FIELDS = {"updated_at", "first_seen_at", "expires_at", "login_notified_at", "read_at"}


def _request_metadata():
    if not has_request_context() or request.method in {"GET", "HEAD", "OPTIONS"} or not current_user.is_authenticated:
        return None
    return {
        "user_id": current_user.id,
        "actor": (current_user.full_name or current_user.username)[:255],
        "endpoint": request.endpoint or "",
        "path": request.path[:512],
        "created_at": utc_now(),
    }


@event.listens_for(Session, "after_flush")
def record_changes(session, _flush_context):
    metadata = _request_metadata()
    if metadata is None:
        return
    records = []
    for action, objects in (("create", session.new), ("update", session.dirty), ("delete", session.deleted)):
        for obj in objects:
            state = inspect(obj)
            table = state.mapper.local_table.name
            if table in EXCLUDED_TABLES:
                continue
            fields = []
            if action == "update":
                fields = [attr.key for attr in state.mapper.column_attrs
                          if attr.key not in IGNORED_FIELDS and state.attrs[attr.key].history.has_changes()]
                if not fields:
                    continue
            records.append({
                **metadata, "action": action, "entity": table,
                "entity_id": getattr(obj, "id", None),
                "project_id": getattr(obj, "id", None) if table == "projects" else getattr(obj, "project_id", None),
                "fields": ", ".join(fields) or None,
            })
    if records:
        session.connection().execute(CrmAuditLog.__table__.insert(), records)


@event.listens_for(Session, "do_orm_execute")
def record_bulk_changes(state):
    if not (state.is_update or state.is_delete or state.is_insert):
        return None
    metadata = _request_metadata()
    table = getattr(state.statement, "table", None)
    if metadata is None or table is None or table.name in EXCLUDED_TABLES:
        return None
    result = state.invoke_statement()
    count = getattr(result, "rowcount", None)
    if count != 0:
        state.session.connection().execute(CrmAuditLog.__table__.insert(), {
            **metadata, "action": "delete" if state.is_delete else "update" if state.is_update else "create",
            "entity": table.name, "affected_count": count if count is not None and count >= 0 else None,
        })
    return result
