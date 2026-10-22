"""Developer-only editorial tools; public releases never expose personal messages."""
from flask import abort,flash,jsonify,redirect,render_template,request,url_for
from flask_login import current_user,login_required
from sqlalchemy.orm import selectinload
from app import db
from app.models import DeveloperUpdate,DeveloperPersonalMessage,User,WORKER_ROLES,ROLE_ADMIN
from app.permissions import role_required
from app.routes import bp,selected_project
from app.security import hit_rate_limit
from app.services.developer_news import eligible,published_updates,card_for_user
from app.time_utils import utc_now


def text_fields():
    title=(request.form.get('title') or '').strip()
    body=(request.form.get('body') or '').strip()
    if not title or len(title)>160 or not body or len(body)>10000:
        raise ValueError('Укажите заголовок до 160 символов и текст до 10000 символов.')
    return title,body


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
            if action not in {'draft','publish'}:raise ValueError('Выберите сохранение черновика или публикацию.')
            db.session.add(DeveloperUpdate(title=title,body=body,author_id=current_user.id,
                published_at=utc_now() if action=='publish' else None))
            db.session.commit();flash('Обновление опубликовано для всех объектов.' if action=='publish' else 'Черновик сохранён.','success')
            return redirect(url_for('main.developer_updates'),code=303)
        except ValueError as error:
            return editor_context(str(error)),400
    return editor_context()


@bp.route('/developer/updates/<int:update_id>/edit',methods=['GET','POST'])
@login_required
@role_required(ROLE_ADMIN)
def developer_update_edit(update_id):
    update=db.session.get(DeveloperUpdate,update_id) or abort(404)
    if request.method=='POST':
        write_limit()
        try:
            title,body=text_fields()
            action=request.form.get('action')
            if action not in {'draft','publish'}:raise ValueError('Некорректное действие.')
            update.title=title;update.body=body
            if action=='publish':update.published_at=update.published_at or utc_now();update.withdrawn_at=None
            elif update.published_at is not None:update.withdrawn_at=utc_now()
            db.session.commit();flash('Изменения сохранены.','success')
            return redirect(url_for('main.developer_updates'),code=303)
        except ValueError as error:return editor_context(str(error),update),400
    return editor_context(edit=update)


@bp.post('/developer/updates/<int:update_id>/withdraw')
@login_required
@role_required(ROLE_ADMIN)
def developer_update_withdraw(update_id):
    write_limit();update=db.session.get(DeveloperUpdate,update_id) or abort(404)
    update.withdrawn_at=utc_now();db.session.commit()
    flash('Публикация скрыта у пользователей.','success')
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
    page=max(1,min(request.args.get('page',1,type=int),10000))
    updates=published_updates().order_by(DeveloperUpdate.published_at.desc(),DeveloperUpdate.id.desc()).paginate(page=page,per_page=20,error_out=False)
    response=render_template('updates_archive.html',updates=updates)
    return response,200,{'Cache-Control':'private, no-store'}


@bp.get('/updates/card')
@login_required
def updates_card():
    if not eligible(current_user):abort(403)
    if selected_project() is None:abort(400)
    if hit_rate_limit('developer-news-card',120,60,subject=f'user:{current_user.id}'):abort(429)
    card=card_for_user(current_user,start=request.method=='GET')
    response=jsonify(html=render_template('_developer_update_card.html',news_card=card),
        expires_at=card['expires_at'].isoformat(timespec='seconds')+'Z' if card['expires_at'] else None)
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
