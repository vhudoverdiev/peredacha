import time

from flask import Flask, abort, g, redirect, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, logout_user
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from flask_compress import Compress
from config import Config
from sqlalchemy import inspect, text
from datetime import date, datetime, timedelta

from app.time_utils import to_moscow_datetime


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
compress = Compress()

RU_MONTHS_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def _format_ru_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return str(value)
    return f"{value.day} {RU_MONTHS_GENITIVE.get(value.month, '')} {value.year}".strip()


def _format_ru_datetime(value) -> str:
    if not value:
        return "—"
    if not isinstance(value, datetime):
        return str(value)
    value = to_moscow_datetime(value)
    return f"{_format_ru_date(value)} {value.strftime('%H:%M')}"


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    config_class.init_app(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    compress.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Войдите в CRM, чтобы продолжить"
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    @app.before_request
    def enforce_global_security():
        g.request_started_at = time.perf_counter()
        if request.content_length and request.content_length > int(app.config.get("MAX_CONTENT_LENGTH") or 0):
            abort(413)
        if current_user.is_authenticated:
            from app.security import is_session_version_valid, hit_rate_limit, security_event
            if not is_session_version_valid():
                security_event("session_revoked", "Сессия устарела или была отозвана", severity="warning")
                logout_user()
                session.clear()
                abort(401)
            # Мягкий лимит на частые POST-действия, чтобы не сломать обычную работу, но закрыть бесконечный спам.
            if request.method == "POST" and hit_rate_limit(f"post:{request.endpoint or request.path}", 180, 60):
                security_event("rate_limit", "Слишком много POST-запросов", severity="warning")
                abort(429)

    @app.after_request
    def add_security_headers(response):
        from app.security import record_site_visit

        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'",
        )
        if app.config.get("FORCE_HSTS") or request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.endpoint == "static" or request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif current_user.is_authenticated or response.mimetype == "text/html" or request.blueprint == "auth":
            # An installed iOS PWA can restore an old login document from its
            # page cache after the session cookie has changed.  Never cache
            # dynamic HTML or authentication responses with an embedded CSRF
            # token.
            response.headers["Cache-Control"] = "private, no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        record_site_visit(response)
        return response

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        # Do not leave the PWA on Flask's raw 400 page when WebKit restored a
        # stale login form.  A fresh GET creates a matching session/token pair.
        if request.endpoint == "auth.login" or request.path == "/login":
            session.pop("csrf_token", None)
            return redirect(url_for("auth.login"), code=303)
        return error.get_response()

    @app.template_filter("msk_datetime")
    def msk_datetime(value, fmt=None):
        if not value:
            return "—"
        value = to_moscow_datetime(value)
        if fmt:
            return value.strftime(fmt)
        return f"{_format_ru_date(value)} {value.strftime('%H:%M')}"

    @app.template_filter("ru_date")
    def ru_date(value):
        return _format_ru_date(value)

    @app.template_filter("ru_datetime")
    def ru_datetime(value):
        return _format_ru_datetime(value)


    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # Bootstrap DB for fresh installs / new tables (no Alembic migrations yet).
    from app import models  # noqa: F401

    with app.app_context():
        uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
        if uri.startswith("sqlite:"):
            # create_all is idempotent for SQLite and ensures new tables appear.
            db.create_all()
            inspector = inspect(db.engine)
            if "projects" in inspector.get_table_names():
                project_columns = {column["name"] for column in inspector.get_columns("projects")}
                if "google_sheet_id" not in project_columns:
                    db.session.execute(text("ALTER TABLE projects ADD COLUMN google_sheet_id VARCHAR(255)"))
                if "has_apartments" not in project_columns:
                    db.session.execute(text("ALTER TABLE projects ADD COLUMN has_apartments BOOLEAN NOT NULL DEFAULT 1"))
                if "has_commercial" not in project_columns:
                    db.session.execute(text("ALTER TABLE projects ADD COLUMN has_commercial BOOLEAN NOT NULL DEFAULT 1"))
                if "has_storerooms" not in project_columns:
                    db.session.execute(text("ALTER TABLE projects ADD COLUMN has_storerooms BOOLEAN NOT NULL DEFAULT 0"))
                db.session.commit()
            if "users" in inspector.get_table_names():
                user_columns = {column["name"] for column in inspector.get_columns("users")}
                added_project_access_mode = False
                if "password_plain" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN password_plain VARCHAR(255)"))
                if "project_id" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN project_id INTEGER"))
                if "all_projects_access" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN all_projects_access BOOLEAN NOT NULL DEFAULT 0"))
                    added_project_access_mode = True
                if "project_access_ids_json" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN project_access_ids_json TEXT"))
                if "failed_login_count" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0"))
                if "locked_until" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN locked_until DATETIME"))
                if "last_login_at" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
                if "last_login_ip" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN last_login_ip VARCHAR(80)"))
                if "session_version" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"))
                if "captcha_disabled" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN captcha_disabled BOOLEAN NOT NULL DEFAULT 0"))
                if "two_factor_enabled" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN two_factor_enabled BOOLEAN NOT NULL DEFAULT 0"))
                if "two_factor_secret" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN two_factor_secret VARCHAR(64)"))
                if "two_factor_confirmed_at" not in user_columns:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN two_factor_confirmed_at DATETIME"))
                if added_project_access_mode:
                    db.session.execute(text("UPDATE users SET all_projects_access = 1 WHERE project_id IS NULL OR role IN ('admin', 'manager', 'verifier')"))
                # Больше не держим пароли в открытом виде в БД.
                db.session.execute(text("UPDATE users SET password_plain = NULL WHERE password_plain IS NOT NULL"))
                db.session.commit()
            if "apartments" in inspector.get_table_names():
                apartment_columns = {column["name"] for column in inspector.get_columns("apartments")}
                if "avr_archived_at" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN avr_archived_at DATETIME"))
                if "inspection_note" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN inspection_note TEXT"))
                    db.session.execute(text("UPDATE apartments SET inspection_note = comment WHERE comment IS NOT NULL AND comment != ''"))
                if "is_unsold" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN is_unsold BOOLEAN NOT NULL DEFAULT 0"))
                    # В старых версиях строка «не продано» сохранялась как пустой собственник.
                    # Один раз переносим такие уже загруженные строки в явный флаг,
                    # чтобы откат/дашборд не зависели от пустого ФИО.
                    db.session.execute(text("UPDATE apartments SET is_unsold = 1 WHERE owner_name IS NULL OR TRIM(owner_name) = '' OR owner_name LIKE '%не прод%' OR owner_name LIKE '%НЕ ПРОД%'"))
                if "first_inspection_date" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN first_inspection_date DATE"))
                if "inspection_date_backup" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN inspection_date_backup DATE"))
                    db.session.execute(text("UPDATE apartments SET inspection_date_backup = inspection_date WHERE inspection_date IS NOT NULL"))
                if "first_inspection_present" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN first_inspection_present BOOLEAN NOT NULL DEFAULT 0"))
                    db.session.execute(text("UPDATE apartments SET first_inspection_present = 1 WHERE first_inspection_date IS NOT NULL"))
                if "is_app_mode" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN is_app_mode BOOLEAN NOT NULL DEFAULT 0"))
                    db.session.execute(text("UPDATE apartments SET is_app_mode = 1 WHERE deadline_date IS NOT NULL"))
                if "po_status" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN po_status VARCHAR(30) NOT NULL DEFAULT 'not_ready'"))
                if "remark_deadline_date" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN remark_deadline_date DATE"))
                if "po_status_manual" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN po_status_manual BOOLEAN NOT NULL DEFAULT 0"))
                if "premise_type" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN premise_type VARCHAR(30) NOT NULL DEFAULT 'apartment'"))
                if "building" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN building VARCHAR(50)"))
                if "avr_status" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN avr_status VARCHAR(30) NOT NULL DEFAULT 'needed'"))
                if "avr_signed_date" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN avr_signed_date DATE"))
                if "app_deadline_date" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN app_deadline_date DATE"))
                if "app_deadline_raw" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN app_deadline_raw VARCHAR(255)"))
                if "app_deadline_status" not in apartment_columns:
                    db.session.execute(text("ALTER TABLE apartments ADD COLUMN app_deadline_status VARCHAR(30) NOT NULL DEFAULT 'normal'"))
                db.session.commit()

            if "material_requests" in inspector.get_table_names():
                material_request_columns = {column["name"] for column in inspector.get_columns("material_requests")}
                if "title" not in material_request_columns:
                    db.session.execute(text("ALTER TABLE material_requests ADD COLUMN title VARCHAR(255)"))
                    db.session.commit()

            if "glass_measurements" in inspector.get_table_names():
                glass_columns = {column["name"] for column in inspector.get_columns("glass_measurements")}
                if "apartment_id" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN apartment_id INTEGER"))
                if "width" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN width FLOAT"))
                if "height" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN height FLOAT"))
                if "quantity" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1"))
                if "glass_type" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN glass_type VARCHAR(160)"))
                if "measured_at" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN measured_at DATE"))
                if "ordered_at" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN ordered_at DATE"))
                if "replaced_at" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN replaced_at DATE"))
                if "material_request_item_id" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN material_request_item_id INTEGER"))
                if "material_writeoff_id" not in glass_columns:
                    db.session.execute(text("ALTER TABLE glass_measurements ADD COLUMN material_writeoff_id INTEGER"))
                db.session.execute(text("UPDATE glass_measurements SET status = 'measure_needed' WHERE status = 'not_ordered'"))
                db.session.execute(text("UPDATE glass_measurements SET apartment_id = (SELECT apartment_id FROM tasks WHERE tasks.id = glass_measurements.task_id) WHERE apartment_id IS NULL"))
                db.session.commit()

            if "site_visits" in inspector.get_table_names():
                site_visit_columns = {column["name"] for column in inspector.get_columns("site_visits")}
                if "visit_kind" not in site_visit_columns:
                    db.session.execute(text("ALTER TABLE site_visits ADD COLUMN visit_kind VARCHAR(20) NOT NULL DEFAULT 'request'"))
                if "tab_id" not in site_visit_columns:
                    db.session.execute(text("ALTER TABLE site_visits ADD COLUMN tab_id VARCHAR(80)"))
                db.session.execute(text("UPDATE site_visits SET visit_kind = 'request' WHERE visit_kind IS NULL OR TRIM(visit_kind) = ''"))
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_site_visits_visit_kind ON site_visits (visit_kind)"))
                db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_site_visits_tab_id ON site_visits (tab_id)"))
                db.session.commit()


            if "sync_conflicts" in inspector.get_table_names():
                sync_conflict_columns = {column["name"] for column in inspector.get_columns("sync_conflicts")}
                if "apartment_id" not in sync_conflict_columns:
                    db.session.execute(text("ALTER TABLE sync_conflicts ADD COLUMN apartment_id INTEGER"))
                if "target_type" not in sync_conflict_columns:
                    db.session.execute(text("ALTER TABLE sync_conflicts ADD COLUMN target_type VARCHAR(30) NOT NULL DEFAULT 'task'"))
                if "field_name" not in sync_conflict_columns:
                    db.session.execute(text("ALTER TABLE sync_conflicts ADD COLUMN field_name VARCHAR(120)"))
                if "field_label" not in sync_conflict_columns:
                    db.session.execute(text("ALTER TABLE sync_conflicts ADD COLUMN field_label VARCHAR(160)"))
                db.session.commit()

            if "sync_logs" in inspector.get_table_names():
                sync_log_columns = {column["name"] for column in inspector.get_columns("sync_logs")}
                if "project_id" not in sync_log_columns:
                    db.session.execute(text("ALTER TABLE sync_logs ADD COLUMN project_id INTEGER"))
                if "rolled_back_at" not in sync_log_columns:
                    db.session.execute(text("ALTER TABLE sync_logs ADD COLUMN rolled_back_at DATETIME"))
                if "rollback_note" not in sync_log_columns:
                    db.session.execute(text("ALTER TABLE sync_logs ADD COLUMN rollback_note TEXT"))
                if "rollback_data" not in sync_log_columns:
                    db.session.execute(text("ALTER TABLE sync_logs ADD COLUMN rollback_data TEXT"))
                db.session.commit()
                # Для старых баз: если объект один, привязываем прежние записи журнала к нему.
                first_project_id = db.session.execute(text("SELECT id FROM projects ORDER BY id ASC LIMIT 1")).scalar()
                project_count = db.session.execute(text("SELECT COUNT(*) FROM projects")).scalar() or 0
                if first_project_id and project_count == 1:
                    db.session.execute(text("UPDATE sync_logs SET project_id = :project_id WHERE project_id IS NULL"), {"project_id": first_project_id})
                    db.session.commit()

    from app.auth import bp as auth_bp
    from app.routes import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    from app.cli import register_cli

    register_cli(app)

    return app
