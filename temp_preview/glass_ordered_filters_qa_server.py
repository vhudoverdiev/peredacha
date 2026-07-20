from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import session
from flask_login import current_user, login_user
from sqlalchemy import func

from app import create_app, login_manager
from app.models import GlassMeasurement, Project, User
from config import Config


preview_dir = Path.cwd() / "temp_preview"


class PreviewConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SYNC_ON_STARTUP = False
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{(preview_dir / 'glass_ordered_filters_qa.sqlite').as_posix()}"


app = create_app(PreviewConfig)
login_manager.session_protection = None


@app.before_request
def preview_login():
    user = User.query.filter_by(role="admin", is_active=True).first() or User.query.filter_by(is_active=True).first()
    if user and (not current_user.is_authenticated or current_user.id != user.id):
        login_user(user)
        session["session_version"] = int(user.session_version or 0)

    project = (
        Project.query
        .outerjoin(GlassMeasurement, GlassMeasurement.project_id == Project.id)
        .group_by(Project.id)
        .order_by(func.count(GlassMeasurement.id).desc())
        .first()
    )
    if project:
        session["current_project_id"] = project.id


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5059, debug=False, use_reloader=False)
