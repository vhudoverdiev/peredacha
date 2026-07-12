from __future__ import annotations

import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import BoundedSemaphore
from typing import Iterable

from flask import current_app, g, request, session
from flask_login import current_user
from werkzeug.datastructures import FileStorage

from app import db


# In-process limiter. It is deliberately dependency-free so the CRM keeps working
# on the current hosting. For multi-worker production, replace this with Redis.
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_VISIT_WRITER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="site-visit")
_VISIT_WRITE_SLOTS = BoundedSemaphore(256)


def _write_site_visit(engine, table, payload: dict) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(table.insert().values(**payload))
    except Exception:
        pass


def client_ip() -> str:
    return request.remote_addr or "unknown"


def _bucket_key(scope: str) -> str:
    return f"{scope}:{client_ip()}"


def hit_rate_limit(scope: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    key = _bucket_key(scope)
    bucket = _BUCKETS[key]
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def _captcha_session_key(prefix: str, name: str) -> str:
    prefix = re.sub(r"[^a-z0-9_]+", "_", (prefix or "login").lower())
    return f"{prefix}_captcha_{name}"


def generate_captcha(prefix: str = "login") -> str:
    """Generate a small server-side math challenge.

    The optional prefix allows login and registration forms to have separate
    captcha answers in the same browser session.
    """
    mode = secrets.randbelow(3)

    if mode == 0:
        a = secrets.randbelow(5) + 1  # 1..5
        b = secrets.randbelow(5) + 1  # 1..5
        question = f"{a} + {b}"
        expected = a + b
    elif mode == 1:
        a = secrets.randbelow(6) + 5  # 5..10
        b = secrets.randbelow(a) + 1  # 1..a
        question = f"{a} - {b}"
        expected = a - b
    else:
        a = secrets.randbelow(4) + 1  # 1..4
        b = secrets.randbelow(4) + 1  # 1..4
        c = secrets.randbelow(3) + 1  # 1..3
        question = f"{a} + {b} + {c}"
        expected = a + b + c

    session[_captcha_session_key(prefix, "answer")] = str(expected)
    session[_captcha_session_key(prefix, "question")] = question
    session[_captcha_session_key(prefix, "issued_at")] = int(time.time())
    session[_captcha_session_key(prefix, "nonce")] = secrets.token_urlsafe(16)
    return question


def verify_captcha(answer: str | None, max_age_seconds: int = 900, prefix: str = "login") -> bool:
    expected = session.get(_captcha_session_key(prefix, "answer"))
    issued_at = int(session.get(_captcha_session_key(prefix, "issued_at")) or 0)
    if not expected or not issued_at:
        return False
    if int(time.time()) - issued_at > max_age_seconds:
        return False
    normalized = str(answer or "").strip().replace(" ", "")
    return hmac.compare_digest(normalized, str(expected))


def clear_captcha(prefix: str = "login") -> None:
    session.pop(_captcha_session_key(prefix, "answer"), None)
    session.pop(_captcha_session_key(prefix, "question"), None)
    session.pop(_captcha_session_key(prefix, "issued_at"), None)
    session.pop(_captcha_session_key(prefix, "nonce"), None)


def security_event(kind: str, message: str, user_id: int | None = None, severity: str = "info") -> None:
    try:
        from app.models import SecurityEvent

        event = SecurityEvent(
            user_id=user_id or (current_user.id if getattr(current_user, "is_authenticated", False) else None),
            kind=kind[:80],
            severity=severity[:30],
            ip_address=client_ip()[:80],
            path=(request.path or "")[:500],
            method=(request.method or "")[:20],
            user_agent=(request.headers.get("User-Agent") or "")[:500],
            message=(message or "")[:2000],
        )
        db.session.add(event)
        db.session.commit()
    except Exception:
        db.session.rollback()


def should_record_site_visit() -> bool:
    endpoint = request.endpoint or ""
    path = request.path or ""
    if request.method == "OPTIONS":
        return False
    if path.startswith("/static/"):
        return False
    if endpoint == "static" or endpoint.startswith("static."):
        return False
    if endpoint == "main.analytics_tab_open":
        return False
    return True


def resolve_site_visit_project_id() -> int | None:
    project_id = None
    if getattr(current_user, "is_authenticated", False):
        project_id = getattr(current_user, "project_id", None) or None
    if not project_id:
        raw_project_id = session.get("current_project_id")
        try:
            project_id = int(raw_project_id) if raw_project_id else None
        except (TypeError, ValueError):
            project_id = None
    return project_id


def record_site_visit(response) -> None:
    if not should_record_site_visit():
        return
    try:
        from app.models import SiteVisit

        started_at = getattr(g, "request_started_at", None)
        duration_ms = None
        if started_at is not None:
            duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        project_id = resolve_site_visit_project_id()
        full_path = request.full_path or request.path or ""
        path = full_path[:-1] if full_path.endswith("?") else full_path
        forwarded_for = (request.headers.get("X-Forwarded-For") or "")[:255] or None
        payload = {
            "project_id": project_id,
            "user_id": current_user.id if getattr(current_user, "is_authenticated", False) else None,
            "ip_address": client_ip()[:80],
            "forwarded_for": forwarded_for,
            "endpoint": (request.endpoint or "")[:120] or None,
            "method": (request.method or "")[:20] or None,
            "path": path[:500] or None,
            "referrer": (request.referrer or "")[:500] or None,
            "user_agent": (request.headers.get("User-Agent") or "")[:500] or None,
            "status_code": int(getattr(response, "status_code", 0) or 0),
            "duration_ms": duration_ms,
            "is_authenticated": bool(getattr(current_user, "is_authenticated", False)),
            "visit_kind": "request",
            "tab_id": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if _VISIT_WRITE_SLOTS.acquire(blocking=False):
            future = _VISIT_WRITER.submit(_write_site_visit, db.engine, SiteVisit.__table__, payload)
            future.add_done_callback(lambda _future: _VISIT_WRITE_SLOTS.release())
    except Exception:
        pass


def mark_login_success(user) -> None:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = client_ip()[:80]
    db.session.commit()


def mark_login_failure(user) -> None:
    if not user:
        return
    user.failed_login_count = int(user.failed_login_count or 0) + 1
    # 5 failures = 15 min; then progressively longer, capped at 24 hours.
    if user.failed_login_count >= 5:
        extra = max(user.failed_login_count - 5, 0)
        minutes = min(15 * (2 ** min(extra, 6)), 24 * 60)
        user.locked_until = datetime.utcnow() + timedelta(minutes=minutes)
    db.session.commit()


def is_account_locked(user) -> bool:
    return bool(user and user.locked_until and user.locked_until > datetime.utcnow())


def bump_session_version(user) -> None:
    user.session_version = int(user.session_version or 0) + 1


def is_session_version_valid() -> bool:
    if not getattr(current_user, "is_authenticated", False):
        return True
    return int(session.get("session_version", -1)) == int(getattr(current_user, "session_version", 0) or 0)


def allowed_upload_suffix(filename: str, allowed: Iterable[str]) -> bool:
    suffix = Path(filename or "").suffix.lower().lstrip(".")
    return suffix in {item.lower().lstrip(".") for item in allowed}


def validate_upload(file: FileStorage, allowed: Iterable[str], max_size: int | None = None) -> None:
    """Basic allow-list + magic-byte validation for user uploads."""
    filename = file.filename or ""
    if not allowed_upload_suffix(filename, allowed):
        raise ValueError("Недопустимый тип файла")
    if max_size is None:
        max_size = int(current_app.config.get("MAX_UPLOAD_FILE_BYTES") or current_app.config.get("MAX_CONTENT_LENGTH") or 0)
    stream = file.stream
    pos = stream.tell()
    header = stream.read(8)
    stream.seek(pos)
    if max_size:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(pos)
        if size > max_size:
            raise ValueError("Файл слишком большой")
    lower = filename.lower()
    if lower.endswith((".xlsx", ".docx")) and not header.startswith(b"PK"):
        raise ValueError("Файл повреждён или не соответствует расширению")
    if lower.endswith(".pdf") and not header.startswith(b"%PDF"):
        raise ValueError("Файл повреждён или не соответствует расширению")
    if lower.endswith(".doc") and not header.startswith(bytes.fromhex("D0CF11E0")):
        raise ValueError("Файл повреждён или не соответствует расширению")
