from datetime import datetime
import binascii
import json
import time
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app import db
from app.forms import LoginCaptchaForm, LoginForm, LoginTwoFactorForm
from app.models import ROLE_VERIFIER, SiteErrorReport, User, WebAuthnCredential, WORKER_ROLES
from app.services.task_service import get_setting
from app.security import (
    clear_captcha,
    client_ip,
    generate_captcha,
    hit_rate_limit,
    is_account_locked,
    mark_login_failure,
    mark_login_success,
    security_event,
    verify_captcha,
)
from app.two_factor import verify_totp

bp = Blueprint("auth", __name__)


def _passkey_rp_id() -> str:
    configured = (current_app.config.get("WEBAUTHN_RP_ID") or "").strip().lower()
    return configured or request.host.split(":", 1)[0].strip().lower()


def _passkey_origin() -> str:
    configured = (current_app.config.get("WEBAUTHN_ORIGIN") or "").strip().rstrip("/")
    if configured:
        return configured
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else request.scheme
    return f"{scheme}://{request.host}"


def _passkey_options_json(options) -> dict:
    return json.loads(options_to_json(options))


def _canonical_credential_id(value: str | None) -> str:
    return bytes_to_base64url(base64url_to_bytes(str(value or "")))


def _passkey_challenge(session_key: str) -> bytes | None:
    encoded = session.pop(session_key, None)
    issued_at = float(session.pop(f"{session_key}_issued_at", 0) or 0)
    if not encoded or not issued_at or time.time() - issued_at > 300:
        return None
    try:
        return base64url_to_bytes(encoded)
    except (TypeError, ValueError):
        return None


def _store_passkey_challenge(session_key: str, challenge: bytes) -> None:
    session[session_key] = bytes_to_base64url(challenge)
    session[f"{session_key}_issued_at"] = time.time()


def _is_safe_next(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/")


def _clear_pending_login() -> None:
    session.pop("pending_login_user_id", None)
    session.pop("pending_login_remember", None)
    session.pop("pending_login_next", None)
    session.pop("pending_login_2fa", None)
    session.pop("pending_login_2fa_verified", None)
    session.pop("passkey_auth_challenge", None)
    session.pop("passkey_auth_challenge_issued_at", None)


def _render_login(form: LoginForm):
    clear_captcha()
    _clear_pending_login()
    registration_captcha_question = generate_captcha(prefix="registration")
    return render_template("login.html", form=form, registration_captcha_question=registration_captcha_question)


def _render_login_captcha(form: LoginCaptchaForm):
    captcha_question = generate_captcha()
    return render_template("login_captcha.html", form=form, captcha_question=captcha_question)


def _render_login_2fa(form: LoginTwoFactorForm):
    return render_template("login_2fa.html", form=form)


def _needs_two_factor_for_ip(user: User) -> bool:
    if not user.two_factor_enabled or not user.two_factor_secret:
        return False
    if str(get_setting("two_factor_every_login", "0") or "").strip().lower() in {"1", "true", "yes", "on", "да", "checked"}:
        return True
    current_ip = client_ip()[:80]
    return not user.last_login_ip or user.last_login_ip != current_ip


def _complete_pending_login(user: User):
    remember = bool(session.get("pending_login_remember"))
    next_url = session.get("pending_login_next") or None
    session.clear()
    login_user(user, remember=remember)
    session.permanent = True
    session["session_version"] = int(user.session_version or 0)
    mark_login_success(user)
    clear_captcha()
    security_event("login_success", f"Успешный вход {user.username}", user_id=user.id)
    return _redirect_after_login(user, next_url)


def _continue_after_password(user: User):
    clear_captcha()
    if not user.captcha_disabled:
        return redirect(url_for("auth.login_captcha"))
    if _needs_two_factor_for_ip(user) and not session.get("pending_login_2fa_verified"):
        session["pending_login_2fa"] = True
        return redirect(url_for("auth.login_2fa"))
    return _complete_pending_login(user)


def _redirect_after_login(user: User, next_url: str | None = None):
    is_worker = user.role in WORKER_ROLES
    next_path = urlparse(next_url or "").path
    next_is_worker_page = next_path.startswith("/my-tasks")

    if _is_safe_next(next_url) and (is_worker or not next_is_worker_page):
        return redirect(next_url)
    if is_worker:
        return redirect(url_for("main.my_tasks"))
    if user.role == ROLE_VERIFIER:
        if not session.get("current_project_id"):
            return redirect(url_for("main.objects"))
        return redirect(url_for("main.work_report"))
    return redirect(url_for("main.dashboard"))


@bp.route("/passkeys/register/options", methods=["POST"])
@login_required
def passkey_registration_options():
    user = db.session.get(User, current_user.id) or abort(404)
    options = generate_registration_options(
        rp_id=_passkey_rp_id(),
        rp_name=current_app.config.get("WEBAUTHN_RP_NAME") or "Передача",
        user_id=f"user:{user.id}".encode("utf-8"),
        user_name=user.username,
        user_display_name=user.full_name or user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    _store_passkey_challenge("passkey_registration_challenge", options.challenge)
    return jsonify(ok=True, publicKey=_passkey_options_json(options))


@bp.route("/passkeys/register/verify", methods=["POST"])
@login_required
def passkey_registration_verify():
    user = db.session.get(User, current_user.id) or abort(404)
    challenge = _passkey_challenge("passkey_registration_challenge")
    payload = request.get_json(silent=True) or {}
    credential = payload.get("credential") or {}
    if challenge is None:
        return jsonify(ok=False, message="Время привязки истекло. Запустите Face ID ещё раз."), 400

    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_passkey_rp_id(),
            expected_origin=_passkey_origin(),
            require_user_verification=True,
        )
        credential_id = bytes_to_base64url(verification.credential_id)
        response_payload = credential.get("response") or {}
        transports = [
            value for value in (response_payload.get("transports") or [])
            if value in {"internal", "hybrid", "usb", "nfc", "ble", "cable", "smart-card"}
        ]
        record = WebAuthnCredential(
            user_id=user.id,
            credential_id=credential_id,
            public_key=verification.credential_public_key,
            sign_count=int(verification.sign_count or 0),
            transports=json.dumps(transports, ensure_ascii=False),
            device_type=getattr(verification.credential_device_type, "value", str(verification.credential_device_type or "")),
            backed_up=bool(verification.credential_backed_up),
            name=(payload.get("name") or "Face ID / Passkey")[:120],
        )
        db.session.add(record)
        db.session.commit()
    except WebAuthnException:
        return jsonify(ok=False, message="Safari не подтвердил привязку Face ID."), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, message="Этот passkey уже привязан к аккаунту."), 409
    except (TypeError, ValueError, binascii.Error):
        db.session.rollback()
        return jsonify(ok=False, message="Получен некорректный ответ Face ID."), 400

    security_event("passkey_registered", f"Passkey подключён для {user.username}", user_id=user.id)
    return jsonify(ok=True, message="Вход по Face ID подключён.")


@bp.route("/passkeys/<int:credential_id>/delete", methods=["POST"])
@login_required
def passkey_delete(credential_id: int):
    record = WebAuthnCredential.query.filter_by(id=credential_id, user_id=current_user.id).first_or_404()
    db.session.delete(record)
    db.session.commit()
    security_event("passkey_deleted", f"Passkey удалён для {current_user.username}", user_id=current_user.id)
    flash("Вход по Face ID отключён для выбранного устройства.", "success")
    return redirect(url_for("main.account"))


@bp.route("/passkeys/authenticate/options", methods=["POST"])
def passkey_authentication_options():
    if current_user.is_authenticated:
        return jsonify(ok=False, message="Вы уже вошли в систему."), 400
    if hit_rate_limit("passkey-options-ip", 60, 300):
        return jsonify(ok=False, message="Слишком много запросов. Попробуйте позже."), 429

    options = generate_authentication_options(
        rp_id=_passkey_rp_id(),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _store_passkey_challenge("passkey_auth_challenge", options.challenge)
    next_url = (request.get_json(silent=True) or {}).get("next")
    session["pending_login_next"] = next_url if _is_safe_next(next_url) else ""
    session["pending_login_remember"] = True
    return jsonify(ok=True, publicKey=_passkey_options_json(options))


@bp.route("/passkeys/authenticate/verify", methods=["POST"])
def passkey_authentication_verify():
    if current_user.is_authenticated:
        return jsonify(ok=False, message="Вы уже вошли в систему."), 400
    if hit_rate_limit("passkey-verify-ip", 30, 300):
        return jsonify(ok=False, message="Слишком много попыток. Попробуйте позже."), 429

    challenge = _passkey_challenge("passkey_auth_challenge")
    payload = request.get_json(silent=True) or {}
    credential = payload.get("credential") or {}
    if challenge is None:
        return jsonify(ok=False, message="Время входа истекло. Запустите Face ID ещё раз."), 400

    try:
        credential_id = _canonical_credential_id(credential.get("id"))
        record = WebAuthnCredential.query.filter_by(credential_id=credential_id).first()
        user = record.user if record else None
        if record is None or user is None or not user.is_active or is_account_locked(user):
            raise InvalidAuthenticationResponse("Credential is not available")

        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=_passkey_rp_id(),
            expected_origin=_passkey_origin(),
            credential_public_key=record.public_key,
            credential_current_sign_count=int(record.sign_count or 0),
            require_user_verification=True,
        )
        record.sign_count = int(verification.new_sign_count or 0)
        record.last_used_at = datetime.utcnow()
        db.session.commit()
    except (WebAuthnException, TypeError, ValueError, binascii.Error):
        db.session.rollback()
        security_event("passkey_login_failed", "Неуспешная попытка входа по passkey", severity="warning")
        return jsonify(ok=False, message="Не удалось подтвердить вход по Face ID."), 401

    session["pending_login_user_id"] = int(user.id)
    response = _complete_pending_login(user)
    security_event("passkey_login_success", f"Вход по passkey {user.username}", user_id=user.id)
    return jsonify(ok=True, redirect=response.location or url_for("main.dashboard"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    form = LoginForm()
    if form.validate_on_submit():
        username = (form.username.data or "").strip()
        user = User.query.filter_by(username=username).first()

        if hit_rate_limit("login-ip", 40, 300) or hit_rate_limit(f"login-user:{username.lower()}", 10, 300):
            security_event("login_rate_limited", f"Слишком много попыток входа для логина {username}", user_id=user.id if user else None, severity="warning")
            flash("Слишком много попыток входа. Попробуйте позже.", "danger")
            return _render_login(form)

        if user and is_account_locked(user):
            security_event("login_locked", f"Попытка входа в заблокированный аккаунт {username}", user_id=user.id, severity="warning")
            flash("Аккаунт временно заблокирован из-за неверных попыток входа. Попробуйте позже.", "danger")
            return _render_login(form)

        if user is None or not user.check_password(form.password.data) or not user.is_active:
            mark_login_failure(user)
            security_event("login_failed", f"Неверный логин/пароль для {username}", user_id=user.id if user else None, severity="warning")
            flash("Неверный логин или пароль", "danger")
            return _render_login(form)

        remember = bool(form.remember.data)
        next_url = request.args.get("next") or request.form.get("next")
        session["pending_login_user_id"] = int(user.id)
        session["pending_login_remember"] = remember
        session["pending_login_next"] = next_url if _is_safe_next(next_url) else ""
        return _continue_after_password(user)

    return _render_login(form)


@bp.route("/login/captcha", methods=["GET", "POST"])
def login_captcha():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    user_id = session.get("pending_login_user_id")
    if not user_id:
        flash("Сначала введите логин и пароль.", "warning")
        return redirect(url_for("auth.login"))

    user = db.session.get(User, int(user_id))
    if user is None or not user.is_active:
        _clear_pending_login()
        clear_captcha()
        flash("Неверный логин или пароль", "danger")
        return redirect(url_for("auth.login"))

    if is_account_locked(user):
        _clear_pending_login()
        clear_captcha()
        security_event("login_locked", f"Попытка входа в заблокированный аккаунт {user.username}", user_id=user.id, severity="warning")
        flash("Аккаунт временно заблокирован из-за неверных попыток входа. Попробуйте позже.", "danger")
        return redirect(url_for("auth.login"))

    form = LoginCaptchaForm()
    if form.validate_on_submit():
        if not verify_captcha(form.captcha_answer.data):
            mark_login_failure(user)
            security_event("captcha_failed", f"Неверная CAPTCHA для логина {user.username}", user_id=user.id, severity="warning")
            flash("Проверка от ботов не пройдена. Решите пример ещё раз.", "danger")
            return _render_login_captcha(form)

        clear_captcha()
        if _needs_two_factor_for_ip(user) and not session.get("pending_login_2fa_verified"):
            session["pending_login_2fa"] = True
            return redirect(url_for("auth.login_2fa"))
        return _complete_pending_login(user)

    return _render_login_captcha(form)


@bp.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    user_id = session.get("pending_login_user_id")
    if not user_id or not session.get("pending_login_2fa"):
        flash("Сначала введите логин и пароль.", "warning")
        return redirect(url_for("auth.login"))

    user = db.session.get(User, int(user_id))
    if user is None or not user.is_active:
        _clear_pending_login()
        clear_captcha()
        flash("Неверный логин или пароль", "danger")
        return redirect(url_for("auth.login"))

    if not user.two_factor_enabled or not user.two_factor_secret:
        return _complete_pending_login(user)

    form = LoginTwoFactorForm()
    if form.validate_on_submit():
        if not verify_totp(user.two_factor_secret, form.two_factor_code.data):
            mark_login_failure(user)
            security_event("two_factor_failed", f"Неверный 2FA-код для {user.username}", user_id=user.id, severity="warning")
            flash("Неверный код двухэтапной аутентификации.", "danger")
            return _render_login_2fa(form)
        session.pop("pending_login_2fa", None)
        session["pending_login_2fa_verified"] = True
        return _complete_pending_login(user)

    return _render_login_2fa(form)


@bp.route("/registration-request", methods=["POST"])
def registration_request():
    """Принимает заявку на регистрацию без создания аккаунта.

    Заявка сохраняется в разделе «Для разработчика» отдельным типом registration,
    чтобы разработчик/администратор увидел, кто пытался зарегистрироваться.
    """
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    captcha_answer = (request.form.get("captcha_answer") or "").strip()

    if hit_rate_limit("registration-request-ip", 8, 300):
        security_event("registration_request_rate_limited", "Слишком много заявок на регистрацию", severity="warning")
        flash("Слишком много заявок. Попробуйте немного позже.", "warning")
        return redirect(url_for("auth.login"))

    if not verify_captcha(captcha_answer, prefix="registration"):
        security_event("registration_request_bad_captcha", "Неверная капча при заявке на регистрацию", severity="warning")
        clear_captcha(prefix="registration")
        flash("Подтвердите регистрацию: решите капчу правильно.", "warning")
        return redirect(url_for("auth.login"))

    if len(name) < 2 or len(name) > 160:
        flash("Укажите корректное имя.", "warning")
        return redirect(url_for("auth.login"))
    if len(email) > 180 or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        flash("Укажите корректный email.", "warning")
        return redirect(url_for("auth.login"))

    message = (
        "Новая заявка на регистрацию в CRM\n"
        f"Имя: {name}\n"
        f"Email: {email}\n"
        f"IP: {request.headers.get('X-Forwarded-For', request.remote_addr or '—')}"
    )
    report = SiteErrorReport(
        kind="registration",
        message=message[:5000],
        page_url=request.referrer or request.url,
        user_agent=(request.headers.get("User-Agent") or "")[:500],
        status="new",
    )
    db.session.add(report)
    db.session.commit()
    clear_captcha(prefix="registration")
    security_event("registration_request", f"Заявка на регистрацию от {email}", severity="info")
    flash("Заявка отправлена. Разработчик данной CRM свяжется с вами.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Вы вышли из CRM", "info")
    return redirect(url_for("auth.login"))
