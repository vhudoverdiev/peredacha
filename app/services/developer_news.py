"""Global release notes and a recipient-scoped, serialized display queue."""
from datetime import timedelta
from sqlalchemy import or_
from app import db
from app.models import DeveloperUpdate,DeveloperPersonalMessage,WORKER_ROLES
from app.time_utils import utc_now


def eligible(user):
    return bool(user and user.is_authenticated and user.is_active and user.role not in WORKER_ROLES)


def published_updates(now=None):
    return DeveloperUpdate.query.filter(
        DeveloperUpdate.published_at <= (now if now is not None else utc_now()),
        DeveloperUpdate.withdrawn_at.is_(None),
    )


def _next_personal_message(user, now):
    return DeveloperPersonalMessage.query.filter_by(recipient_id=user.id, revoked_at=None).filter(
        or_(DeveloperPersonalMessage.first_seen_at.is_(None), DeveloperPersonalMessage.expires_at > now)
    ).order_by(DeveloperPersonalMessage.created_at, DeveloperPersonalMessage.id).first()


def has_unread_personal_message(user):
    message = _next_personal_message(user, utc_now()) if eligible(user) else None
    return message is not None and message.first_seen_at is None


def claim_desktop_login_notice(user):
    if not eligible(user):
        return None
    now = utc_now()
    message = _next_personal_message(user, now)
    if message is None or message.first_seen_at is not None or message.login_notified_at is not None:
        return None
    message_id = message.id
    claimed = DeveloperPersonalMessage.query.filter_by(
        id=message_id, recipient_id=user.id, first_seen_at=None, revoked_at=None, login_notified_at=None,
    ).update({'login_notified_at': now})
    db.session.commit()
    return message_id if claimed else None


def card_for_user(user, *, start=True, personal_only=False):
    if not eligible(user):
        return None
    now = utc_now()
    message = _next_personal_message(user, now)
    if message and message.first_seen_at is None:
        if start:
            # Claim only the pending message, leaving the recipient row unlocked.
            claimed = DeveloperPersonalMessage.query.filter_by(
                id=message.id, recipient_id=user.id, first_seen_at=None, revoked_at=None,
            ).update({
                'first_seen_at': now,
                'expires_at': now + timedelta(minutes=message.duration_minutes),
            })
            db.session.commit()
            if not claimed:
                # A concurrent request started or revoked this message.
                message = _next_personal_message(user, now)
                if message is not None and message.first_seen_at is None:
                    message = None
        else:
            message = None
    if personal_only and not message:
        return None
    update = None if personal_only else published_updates(now).order_by(
        DeveloperUpdate.published_at.desc(), DeveloperUpdate.id.desc()
    ).first()
    return {
        'kind': 'personal' if message else 'update',
        'item': message or update,
        'expires_at': message.expires_at if message else None,
        'fallback': update,
        'server_now': now,
        'personal_only': personal_only,
    }
