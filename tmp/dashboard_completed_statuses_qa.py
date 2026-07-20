import sys
from pathlib import Path

from flask import session
from flask_login import current_user, login_user

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config
from app import create_app, db
from app.models import (
    Apartment,
    Project,
    ROLE_ADMIN,
    STATUS_CONCESSION,
    STATUS_CONTRACTOR,
    STATUS_DONE,
    STATUS_FINISHERS,
    STATUS_GUARANTEE,
    STATUS_NOT_STARTED,
    STATUS_PROBLEM,
    Task,
    User,
    WorkCategory,
    WorkPoint,
)


class QAConfig(Config):
    SECRET_KEY = "dashboard-completed-statuses-visual-qa"
    SQLALCHEMY_DATABASE_URI = "sqlite:///dashboard_completed_statuses_qa.sqlite"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


app = create_app(QAConfig)

with app.app_context():
    db.drop_all()
    db.create_all()
    project = Project(name="Проверка учёта статусов")
    user = User(username="dashboard-qa", password_hash="unused", role=ROLE_ADMIN)
    apartment = Apartment(project=project, apartment_number="100")
    work_point = WorkPoint(point_number="10", source_sheet_name="dashboard-visual-qa")
    category = WorkCategory(name="Маляры", color="#76c51d")
    category.work_points.append(work_point)
    db.session.add_all([project, user, apartment, work_point, category])
    db.session.flush()
    for index, status in enumerate((
        STATUS_DONE,
        STATUS_FINISHERS,
        STATUS_CONTRACTOR,
        STATUS_GUARANTEE,
        STATUS_CONCESSION,
        STATUS_NOT_STARTED,
        STATUS_PROBLEM,
    ), start=1):
        db.session.add(Task(
            source_uid=f"dashboard-visual-{index}",
            project=project,
            apartment=apartment,
            work_point=work_point,
            status=status,
            is_done=status not in {STATUS_NOT_STARTED, STATUS_PROBLEM},
        ))
    db.session.commit()
    qa_user_id = user.id
    qa_project_id = project.id


@app.before_request
def authenticate_visual_qa():
    if not current_user.is_authenticated:
        login_user(db.session.get(User, qa_user_id))
    session["current_project_id"] = qa_project_id


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5016, debug=False, use_reloader=False)
