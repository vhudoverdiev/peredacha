from functools import wraps
from flask import abort, flash, g, redirect, url_for
from flask_login import current_user
from app.models import ROLE_ADMIN, ROLE_MANAGER, ROLE_OFFICE, ROLE_OFFICE_MANAGER, ROLE_SUPERVISOR, ROLE_VIEWER, WORKER_ROLES


OFFICE_MANAGER_ROLES = {ROLE_MANAGER, ROLE_OFFICE, ROLE_OFFICE_MANAGER, ROLE_SUPERVISOR}


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
            g.http_error_reason = "role_not_permitted"
            abort(403)
        return wrapped
    return decorator


def can_manage_sync(user) -> bool:
    return user.role == ROLE_ADMIN


def can_manage_mapping(user) -> bool:
    return user.role == ROLE_ADMIN


def can_change_task(user, task) -> bool:
    from app.role_settings import definitions, allowed
    if user.role in definitions():
        return allowed(user, 'main.update_task', mutation=True)
    if user.role == ROLE_ADMIN or user.role in OFFICE_MANAGER_ROLES:
        return True
    if user.role in WORKER_ROLES and task.responsible_id == user.id:
        return True
    return False


def can_export(user) -> bool:
    if getattr(g, "role_access_granted", False):
        return True
    return user.role == ROLE_ADMIN or user.role in OFFICE_MANAGER_ROLES


def readonly(user) -> bool:
    return user.role == ROLE_VIEWER


def can_view_task_comments(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    from app.role_settings import definitions, effective
    if user.role != ROLE_ADMIN and user.role in definitions():
        policy=effective(user.role)
        return 'remarks' in policy['sections'] and 'remark_view_comments' in policy['actions']
    return getattr(user, "role", None) in {ROLE_ADMIN, ROLE_MANAGER}


def can_use_project_workflows(user) -> bool:
    return getattr(user, 'role', None) in {ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_OFFICE, ROLE_OFFICE_MANAGER, ROLE_VIEWER} or getattr(user, 'role', '').startswith('custom_')


def can_create_appeal(user) -> bool:
    if getattr(g, "role_access_granted", False):
        return True
    return getattr(user, 'role', None) in {ROLE_ADMIN, ROLE_OFFICE, ROLE_OFFICE_MANAGER}
