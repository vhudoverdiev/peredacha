from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_OFFICE, ROLE_SUPERVISOR, ROLE_VIEWER, WORKER_ROLES


OFFICE_MANAGER_ROLES = {ROLE_MANAGER, ROLE_OFFICE, ROLE_SUPERVISOR}


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if (
                current_user.role == ROLE_ADMIN
                or current_user.role in roles
                or (ROLE_MANAGER in roles and current_user.role in OFFICE_MANAGER_ROLES)
            ):
                return view(*args, **kwargs)
            abort(403)
        return wrapped
    return decorator


def can_manage_sync(user) -> bool:
    return user.role == ROLE_ADMIN


def can_manage_mapping(user) -> bool:
    return user.role == ROLE_ADMIN


def can_change_task(user, task) -> bool:
    if user.role == ROLE_ADMIN or user.role in OFFICE_MANAGER_ROLES:
        return True
    if user.role in WORKER_ROLES and task.responsible_id == user.id:
        return True
    return False


def can_export(user) -> bool:
    return user.role == ROLE_ADMIN or user.role in OFFICE_MANAGER_ROLES


def readonly(user) -> bool:
    return user.role == ROLE_VIEWER
