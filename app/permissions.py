from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER, WORKER_ROLES


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role == ROLE_ADMIN or current_user.role in roles:
                return view(*args, **kwargs)
            abort(403)
        return wrapped
    return decorator


def can_manage_sync(user) -> bool:
    return user.role in {ROLE_ADMIN, ROLE_MANAGER}


def can_manage_mapping(user) -> bool:
    return user.role in {ROLE_ADMIN, ROLE_MANAGER}


def can_change_task(user, task) -> bool:
    if user.role in {ROLE_ADMIN, ROLE_MANAGER}:
        return True
    if user.role in WORKER_ROLES and task.responsible_id == user.id:
        return True
    return False


def can_export(user) -> bool:
    return user.role in {ROLE_ADMIN, ROLE_MANAGER}


def readonly(user) -> bool:
    return user.role == ROLE_VIEWER
