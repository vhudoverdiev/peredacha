from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import request, session
from flask_login import current_user, login_user, logout_user

from app import create_app, db, login_manager
from app.models import Project, ROLE_ADMIN, ROLE_HANDYMAN, ROLE_VERIFIER, User
from config import Config


preview_dir = Path.cwd() / "temp_preview" / "mobile_role_shell"
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
    db.create_all()
    project = Project.query.first()
    if project is None:
        project = Project(name="Квартал 100 - 7")
        db.session.add(project)
        db.session.flush()
    for username, full_name, role in (
        ("preview-admin", "Администратор", ROLE_ADMIN),
        ("preview-handyman", "Ширяев Степан", ROLE_HANDYMAN),
        ("preview-verifier", "Сверщик", ROLE_VERIFIER),
    ):
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(
                username=username,
                password_hash="preview",
                full_name=full_name,
                role=role,
                project_id=project.id,
            )
            db.session.add(user)
    db.session.commit()


@app.before_request
def preview_login():
    requested_role = request.args.get("preview_role")
    if requested_role in {ROLE_ADMIN, ROLE_HANDYMAN, ROLE_VERIFIER}:
        session["preview_role"] = requested_role
        if current_user.is_authenticated and current_user.role != requested_role:
            logout_user()
    role = session.get("preview_role", ROLE_HANDYMAN)
    user = User.query.filter_by(role=role).first()
    project = Project.query.first()
    if user and (not current_user.is_authenticated or current_user.id != user.id):
        login_user(user)
        session["session_version"] = int(user.session_version or 0)
    if project:
        session["current_project_id"] = project.id


@app.after_request
def preview_mobile_profile(response):
    """Force the local browser preview through the real mobile CSS branch."""
    if response.mimetype != "text/html":
        return response
    html = response.get_data(as_text=True)
    marker = """<script>
(() => {
  const forcePreviewMobileProfile = () => {
    const mobileClasses = ['mobile-viewport', 'touch-app-device', 'real-phone-device', 'standalone-app'];
    document.documentElement.classList.remove('desktop-like-pointer');
    document.documentElement.classList.add(...mobileClasses);
    document.body?.classList.remove('desktop-like-pointer');
    document.body?.classList.add(...mobileClasses);
    document.documentElement.style.setProperty('--app-height', `${window.innerHeight}px`);
  };
  forcePreviewMobileProfile();
  window.addEventListener('load', forcePreviewMobileProfile, { once: true });
  window.setTimeout(forcePreviewMobileProfile, 150);
})();
</script>"""
    html = html.replace("</body>", f"{marker}</body>")
    response.set_data(html)
    response.headers["Content-Length"] = len(response.get_data())
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5064, debug=False, use_reloader=False)
