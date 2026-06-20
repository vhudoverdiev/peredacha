import click
from flask import current_app
from app import db
from app.models import ROLE_ADMIN, User
from app.services.google_sheets_sync import sync_google_sheets
from app.services.mapping_service import ensure_default_categories


def register_cli(app):
    @app.cli.command("sync-sheets")
    def sync_sheets_command():
        """Synchronize tasks from Google Sheets into SQLite."""
        with app.app_context():
            result = sync_google_sheets()
            click.echo(
                f"Google Sheets sync: created={result.get('created_count', 0)}, "
                f"updated={result.get('updated_count', 0)}, missing={result.get('missing_count', 0)}"
            )

    @app.cli.command("seed-defaults")
    def seed_defaults_command():
        """Create default CRM tabs/categories."""
        with app.app_context():
            ensure_default_categories()
            db.session.commit()
            click.echo("Default categories created/updated")


    @app.cli.command("create-developer")
    @click.argument("username")
    @click.argument("password")
    @click.option("--name", "full_name", default=None, help="Имя разработчика в интерфейсе.")
    def create_developer_command(username, password, full_name):
        """Create or update a console-only developer account."""
        username = (username or "").strip()
        password = password or ""
        if not username:
            raise click.ClickException("Укажите логин разработчика.")
        if len(password) < 8:
            raise click.ClickException("Пароль должен быть минимум 8 символов.")
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            if user is None:
                user = User(username=username, full_name=(full_name or username).strip() or username, role=ROLE_ADMIN, is_active=True, project_id=None)
                db.session.add(user)
                action = "created"
            else:
                user.full_name = (full_name or user.full_name or username).strip() or username
                user.role = ROLE_ADMIN
                user.is_active = True
                user.project_id = None
                action = "updated"
            user.set_password(password)
            db.session.commit()
            click.echo(f"Developer account {action}: {username}")
