import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _csv_env(name: str) -> set[str]:
    value = os.getenv(name, "")
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _normalize_database_url(raw_url: str | None) -> str:
    """
    Read DATABASE_URL from the environment.

    The project runs on MariaDB.  Do not silently fall back to a local SQLite
    file because that can hide a broken deployment configuration.  SQLite URLs
    are still returned here so test configs can import this module safely; the
    runtime guard lives in create_app, where TESTING is available.
    """
    if not raw_url:
        return ""

    url = raw_url.strip()
    return url


def _normalize_fs_path(raw_path: str | None, default_relative: str) -> str:
    """
    Make filesystem paths stable regardless of the current working directory.

    If `raw_path` is relative, resolve it relative to BASE_DIR.
    """
    value = (raw_path or default_relative).strip()
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((BASE_DIR / path).resolve())


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _normalize_database_url(os.getenv("DATABASE_URL"))
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    COMPRESS_MIMETYPES = [
        "text/html",
        "text/css",
        "text/javascript",
        "application/javascript",
        "application/json",
        "image/svg+xml",
    ]
    COMPRESS_LEVEL = 6
    COMPRESS_BR_LEVEL = 8
    COMPRESS_MIN_SIZE = 500

    SYNC_ON_STARTUP = _bool_env("SYNC_ON_STARTUP", False)
    SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "30"))

    UPLOAD_FOLDER = _normalize_fs_path(os.getenv("UPLOAD_FOLDER"), "uploads")
    EXPORT_FOLDER = _normalize_fs_path(os.getenv("EXPORT_FOLDER"), "exports")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(50 * 1024 * 1024)))
    MAX_UPLOAD_FILE_BYTES = int(os.getenv("MAX_UPLOAD_FILE_BYTES", str(25 * 1024 * 1024)))
    MAX_FORM_MEMORY_SIZE = int(os.getenv("MAX_FORM_MEMORY_SIZE", str(2 * 1024 * 1024)))

    WTF_CSRF_TIME_LIMIT = int(os.getenv("WTF_CSRF_TIME_LIMIT", str(60 * 60 * 8)))
    WTF_CSRF_SSL_STRICT = _bool_env("WTF_CSRF_SSL_STRICT", False)
    TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "1"))

    # Базовые настройки безопасности cookie. SESSION_COOKIE_SECURE нужно включить
    # на продакшене через .env, когда сайт работает только по HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = int(os.getenv("PERMANENT_SESSION_LIFETIME", str(60 * 60 * 8)))
    PREFERRED_URL_SCHEME = "https" if SESSION_COOKIE_SECURE else "http"
    FORCE_HSTS = _bool_env("FORCE_HSTS", False)
    PROTECTED_DEVELOPER_USERNAMES = _csv_env("PROTECTED_DEVELOPER_USERNAMES")

    @staticmethod
    def init_app(app):
        Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
        Path(app.config["EXPORT_FOLDER"]).mkdir(parents=True, exist_ok=True)
        Path(BASE_DIR / "instance").mkdir(parents=True, exist_ok=True)
