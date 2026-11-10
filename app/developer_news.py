"""Developer-only editorial tools; public releases never expose personal messages."""
from datetime import datetime, timezone
from flask import abort,flash,jsonify,redirect,render_template,request,session,url_for
from flask_login import current_user,login_required
from sqlalchemy.orm import selectinload
from app import db
from app.models import DeveloperUpdate,DeveloperPersonalMessage,User,WORKER_ROLES,ROLE_ADMIN
from app.permissions import role_required
from app.routes import bp,selected_project
from app.security import hit_rate_limit
from app.services.developer_news import eligible,published_updates,card_for_user
from app.time_utils import MOSCOW_TIMEZONE, utc_now


def text_fields():
    title=(request.form.get('title') or '').strip()
    body=(request.form.get('body') or '').strip()
    if not title or len(title)>160 or not body or len(body)>10000:
        raise ValueError('Укажите заголовок до 160 символов и текст до 10000 символов.')
    return title,body



def scheduled_publication_time(now):
    if 'publish_date' in request.form or 'publish_time' in request.form:
        day = request.form.get('publish_date', '').strip()
        time = request.form.get('publish_time', '').strip()
        raw = f'{day}T{time}'
    else:
        raw = request.form.get('publish_at', '').strip()
    try:
        local_time = datetime.strptime(raw, '%Y-%m-%dT%H:%M')
        publish_at = local_time.replace(tzinfo=MOSCOW_TIMEZONE).astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError):
        raise ValueError('Укажите дату и время публикации по Москве.') from None
    if publish_at <= now:
        raise ValueError('Дата и время публикации должны быть в будущем.')
    return publish_at


def is_scheduled(update, now):
    return bool(update.published_at and update.published_at > now and not update.withdrawn_at)


def editor_context(error=None,edit=None):
    mode=request.values.get('mode','updates')
    page=max(1,min(request.args.get('page',1,type=int),10000))
    updates=DeveloperUpdate.query.order_by(DeveloperUpdate.created_at.desc(),DeveloperUpdate.id.desc()).paginate(page=page,per_page=20,error_out=False)
    messages=DeveloperPersonalMessage.query.options(selectinload(DeveloperPersonalMessage.recipient)).order_by(DeveloperPersonalMessage.created_at.desc(),DeveloperPersonalMessage.id.desc()).paginate(page=page,per_page=20,error_out=False)
    recipients=User.query.filter(User.is_active.is_(True),User.role.notin_(WORKER_ROLES)).order_by(User.full_name,User.username).all()
    return render_template('developer_updates.html',updates=updates,messages=messages,recipients=recipients,
        mode=mode,error=error,edit=edit,now=utc_now())


def write_limit():
    if hit_rate_limit('developer-news-write',60,300,subject=f'user:{current_user.id}'):abort(429)


@bp.route('/developer/updates',methods=['GET','POST'])
@login_required
@role_required(ROLE_ADMIN)
def developer_updates():
    if request.method=='POST':
        write_limit()
        try:
            title,body=text_fields()
            action=request.form.get('action')
            if action not in {'draft','publish','schedule'}:raise ValueError('Выберите действие для обновления.')
            now=utc_now()
            published_at = scheduled_publication_time(now) if action=='schedule' else (now if action=='publish' else None)
            db.session.add(DeveloperUpdate(title=title,body=body,author_id=current_user.id,
                published_at=published_at))
            db.session.commit()
            flash({
                'publish': 'Обновление опубликовано для всех объектов.',
                'draft': 'Черновик сохранён.',
                'schedule': 'Публикация запланирована.',
            }[action], 'success')
            return redirect(url_for('main.developer_updates'),code=303)
        except ValueError as error:
            return editor_context(str(error)),400
    return editor_context()


@bp.route('/developer/updates/<int:update_id>/edit',methods=['GET','POST'])
@login_required
@role_required(ROLE_ADMIN)
def developer_update_edit(update_id):
    if request.method=='POST':
        write_limit()
        update=DeveloperUpdate.query.filter_by(id=update_id).with_for_update().first_or_404()
        try:
            title,body=text_fields()
            action=request.form.get('action')
            now = utc_now()
            if action not in {'draft','publish','schedule'}:
                raise ValueError('Некорректное действие.')
            scheduled = is_scheduled(update, now)
            if action == 'schedule':
                if update.published_at and not update.withdrawn_at and not scheduled:
                    raise ValueError('Снимите опубликованное обновление перед планированием.')
                update.published_at = scheduled_publication_time(now)
                update.withdrawn_at = None
            elif action == 'publish':
                if update.published_at is None or update.published_at > now:
                    update.published_at = now
                update.withdrawn_at = None
            elif scheduled:
                update.published_at = None
            elif update.published_at is not None:
                update.withdrawn_at = now
            update.title=title;update.body=body
            db.session.commit();flash('Публикация запланирована.' if action=='schedule' else 'Изменения сохранены.','success')
            return redirect(url_for('main.developer_updates'),code=303)
        except ValueError as error:return editor_context(str(error),update),400
    return editor_context(edit=db.session.get(DeveloperUpdate,update_id) or abort(404))


@bp.post('/developer/updates/<int:update_id>/withdraw')
@login_required
@role_required(ROLE_ADMIN)
def developer_update_withdraw(update_id):
    write_limit()
    update=DeveloperUpdate.query.filter_by(id=update_id).with_for_update().first_or_404()
    now=utc_now()
    scheduled=is_scheduled(update, now)
    if scheduled:
        update.published_at=None
    else:
        update.withdrawn_at=now
    db.session.commit()
    flash('Планирование отменено. Черновик сохранён.' if scheduled else 'Публикация скрыта у пользователей.','success')
    return redirect(url_for('main.developer_updates'),code=303)


@bp.post('/developer/updates/messages')
@login_required
@role_required(ROLE_ADMIN)
def developer_message_send():
    write_limit()
    try:
        title,body=text_fields()
        recipient=db.session.get(User,request.form.get('recipient_id',type=int))
        if recipient is None or not eligible(recipient):raise ValueError('Выберите активного пользователя, которому доступна карточка обновлений.')
        amount=request.form.get('duration_value',type=int)
        unit=request.form.get('duration_unit',type=int)
        if amount is None or unit not in {1,60,1440} or not 1<=amount*unit<=10080:
            raise ValueError('Срок показа должен составлять от 1 минуты до 7 дней.')
        db.session.add(DeveloperPersonalMessage(recipient_id=recipient.id,author_id=current_user.id,title=title,body=body,duration_minutes=amount*unit))
        db.session.commit();flash('Сообщение отправлено. Отсчёт начнётся при первом показе на главной странице.','success')
        return redirect(url_for('main.developer_updates',mode='messages'),code=303)
    except ValueError as error:return editor_context(str(error)),400


@bp.post('/developer/updates/messages/<int:message_id>/revoke')
@login_required
@role_required(ROLE_ADMIN)
def developer_message_revoke(message_id):
    write_limit();message=db.session.get(DeveloperPersonalMessage,message_id) or abort(404)
    message.revoked_at=utc_now();db.session.commit();flash('Сообщение отозвано.','success')
    return redirect(url_for('main.developer_updates',mode='messages'),code=303)


@bp.get('/updates')
@login_required
def updates_archive():
    if not eligible(current_user):abort(403)
    if request.args.get('personal') == '1':
        if hit_rate_limit('developer-news-card',120,60,subject=f'user:{current_user.id}'):abort(429)
        if request.method == 'GET':
            session.pop('developer_personal_alert', None)
        card = card_for_user(current_user, start=request.method == 'GET', personal_only=True)
        return render_template('developer_personal_message.html', news_card=card), 200, {'Cache-Control': 'private, no-store'}
    page=max(1,min(request.args.get('page',1,type=int),10000))
    updates=published_updates().order_by(DeveloperUpdate.published_at.desc(),DeveloperUpdate.id.desc()).paginate(page=page,per_page=20,error_out=False)
    response=render_template('updates_archive.html',updates=updates)
    return response,200,{'Cache-Control':'private, no-store'}


@bp.get('/updates/card')
@login_required
def updates_card():
    if not eligible(current_user):abort(403)
    personal_only = request.args.get('personal') == '1'
    if request.accept_mimetypes.best_match(('application/json', 'text/html')) == 'text/html':
        return redirect(url_for('main.updates_archive', **({'personal': 1} if personal_only else {})))
    if not personal_only and selected_project() is None:
        response = jsonify(error='project_required')
        response.headers['Cache-Control'] = 'private, no-store'
        return response, 400
    if hit_rate_limit('developer-news-card',120,60,subject=f'user:{current_user.id}'):abort(429)
    card=card_for_user(current_user,start=request.method=='GET',personal_only=personal_only)
    response=jsonify(html=render_template('_developer_update_card.html',news_card=card),
        expires_at=card['expires_at'].isoformat(timespec='seconds')+'Z' if card and card['expires_at'] else None)
    response.headers['Cache-Control']='private, no-store'
    return response


@bp.post('/developer/updates/<int:update_id>/delete')
@login_required
@role_required(ROLE_ADMIN)
def developer_update_delete(update_id):
    write_limit()
    update=db.session.get(DeveloperUpdate,update_id) or abort(404)
    db.session.delete(update);db.session.commit()
    flash('Обновление удалено.','success')
    return redirect(url_for('main.developer_updates'),code=303)


@bp.post('/developer/updates/messages/<int:message_id>/delete')
@login_required
@role_required(ROLE_ADMIN)
def developer_message_delete(message_id):
    write_limit()
    message=db.session.get(DeveloperPersonalMessage,message_id) or abort(404)
    db.session.delete(message);db.session.commit()
    flash('Личное сообщение удалено.','success')
    return redirect(url_for('main.developer_updates',mode='messages'),code=303)
