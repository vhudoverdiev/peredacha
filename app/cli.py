import click
from flask import current_app
from app import db
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
