from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import session
from flask_login import current_user, login_user

from app import create_app, db, login_manager
from app.models import (
    Apartment,
    Contractor,
    Project,
    ROLE_ADMIN,
    STATUS_NOT_STARTED,
    Task,
    User,
    WorkPoint,
)
from config import Config


preview_dir = Path.cwd() / "temp_preview" / "contractor_status_ui"
preview_dir.mkdir(parents=True, exist_ok=True)


class PreviewConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{(preview_dir / 'preview.sqlite').as_posix()}"
    UPLOAD_FOLDER = str(preview_dir / "uploads")
    EXPORT_FOLDER = str(preview_dir / "exports")


app = create_app(PreviewConfig)
login_manager.session_protection = None

with app.app_context():
    project = Project.query.first()
    if project is None:
        project = Project(name="Квартал 100 - 7")
        apartment = Apartment(project=project, apartment_number="18", construction_number="1-18", finishing_type="Белая")
        point = WorkPoint(point_number="12", short_name="Возведение коробки здания")
        alpha = Contractor(project=project, name="ООО ФАСКО")
        beta = Contractor(project=project, name="ООО МОНОЛИТ")
        for contractor in (alpha, beta):
            contractor.apartments.append(apartment)
            contractor.work_points.append(point)
        task = Task(
            source_uid="preview-guarantee-task",
            project=project,
            apartment=apartment,
            work_point=point,
            description="Требуется устранить замечание по гарантии",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        user = User(username="preview-admin", password_hash="preview", full_name="Владимир", role=ROLE_ADMIN, all_projects_access=True)
        db.session.add_all([project, apartment, point, alpha, beta, task, user])
        db.session.commit()


@app.before_request
def preview_login():
    user = User.query.filter_by(username="preview-admin").first()
    project = Project.query.first()
    if user and not current_user.is_authenticated:
        login_user(user)
        session["session_version"] = int(user.session_version or 0)
    if project:
        session["current_project_id"] = project.id


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5058, debug=False, use_reloader=False)
