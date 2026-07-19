import atexit
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import session
from flask_login import current_user, login_user

from app import create_app, db, login_manager
from app.models import STATUS_NOT_STARTED, Project, Task, User
from app.routes import _assignment_task_allowed_for_user, _executor_users
from config import Config


work = Path(tempfile.mkdtemp(prefix="peredacha-assignment-browser-"))
database = work / "crm.sqlite"
shutil.copy2(Path("instance/crm.sqlite").resolve(), database)
atexit.register(lambda: shutil.rmtree(work, ignore_errors=True))


class TestConfig(Config):
    TESTING = False
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{database.as_posix()}"
    UPLOAD_FOLDER = str(work / "uploads")
    EXPORT_FOLDER = str(work / "exports")
    FORCE_HSTS = False
    SESSION_COOKIE_SECURE = False


app = create_app(TestConfig)
login_manager.session_protection = None

with app.app_context():
    project = db.session.get(Project, 1)
    admin = User.query.filter_by(role="admin").order_by(User.id).first()
    users = _executor_users(project.id)
    prepared = None
    for task in Task.query.filter(Task.project_id == project.id).order_by(Task.id):
        eligible = [user for user in users if _assignment_task_allowed_for_user(task, user)]
        if len(eligible) >= 2:
            prepared = (task, eligible[0], eligible[1])
            break
    if prepared is None:
        raise RuntimeError("No task with two eligible assignees")
    task, current_assignee, next_assignee = prepared
    task.responsible_id = current_assignee.id
    task.planned_date = date.today()
    task.status = STATUS_NOT_STARTED
    task.is_done = False
    task.is_archived = False
    task.is_missing_in_latest_sync = False
    db.session.commit()
    app.config["TEST_ADMIN_ID"] = admin.id
    app.config["TEST_ADMIN_SESSION_VERSION"] = int(admin.session_version or 0)
    app.config["TEST_PROJECT_ID"] = project.id
    app.config["TEST_TASK_ID"] = task.id
    app.config["TEST_NEXT_ASSIGNEE"] = next_assignee.full_name or next_assignee.username


@app.before_request
def automatic_test_login():
    if not current_user.is_authenticated:
        user = db.session.get(User, app.config["TEST_ADMIN_ID"])
        login_user(user, fresh=True)
        session["session_version"] = app.config["TEST_ADMIN_SESSION_VERSION"]
    session["current_project_id"] = app.config["TEST_PROJECT_ID"]


# Authentication must run before the application's session-version guard so
# a stale localhost cookie from another test cannot be rejected first.
_automatic_login_handler = app.before_request_funcs[None].pop()
app.before_request_funcs[None].insert(0, _automatic_login_handler)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8768, debug=False, use_reloader=False)
