from flask_login import current_user
from app import db
from app.models import ChangeLog


def log_change(task, action: str, field_name: str | None = None, old_value=None, new_value=None, user_id: int | None = None):
    uid = user_id
    if uid is None:
        try:
            if current_user and current_user.is_authenticated:
                uid = current_user.id
        except RuntimeError:
            uid = None
    entry = ChangeLog(
        user_id=uid,
        task_id=task.id,
        action=action,
        field_name=field_name,
        old_value="" if old_value is None else str(old_value),
        new_value="" if new_value is None else str(new_value),
    )
    db.session.add(entry)
    return entry
