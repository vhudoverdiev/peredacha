"""Global release notes and a recipient-scoped, serialized display queue."""
from datetime import timedelta
from sqlalchemy import or_
from app import db
from app.models import DeveloperUpdate,DeveloperPersonalMessage,User,WORKER_ROLES
from app.time_utils import utc_now


def eligible(user):
    return bool(user and user.is_authenticated and user.is_active and user.role not in WORKER_ROLES)


def published_updates():
    return DeveloperUpdate.query.filter(DeveloperUpdate.published_at.isnot(None),DeveloperUpdate.withdrawn_at.is_(None))


def card_for_user(user,*,start=True):
    if not eligible(user):return None
    # One user lock prevents two tabs from starting two queued messages.
    if start:User.query.filter_by(id=user.id).with_for_update().one()
    now=utc_now()
    query=DeveloperPersonalMessage.query.filter_by(recipient_id=user.id,revoked_at=None)
    query=query.filter(or_(DeveloperPersonalMessage.first_seen_at.is_(None),DeveloperPersonalMessage.expires_at>now))
    message=query.order_by(DeveloperPersonalMessage.created_at,DeveloperPersonalMessage.id).first()
    if message and message.first_seen_at is None:
        if start:
            message.first_seen_at=now
            message.expires_at=now+timedelta(minutes=message.duration_minutes)
        else:message=None
    if start:db.session.commit()
    update=published_updates().order_by(DeveloperUpdate.published_at.desc(),DeveloperUpdate.id.desc()).first()
    return {'kind':'personal' if message else 'update','item':message or update,'expires_at':message.expires_at if message else None,'fallback':update,'server_now':now}
