"""Project-scoped appeals and inspection appointments on the main CRM blueprint."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from flask import abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import db
from app.models import Appeal, AppealAttachment, AppealComment, Apartment, InspectionBooking, InspectionCallNote, InspectionSlot, Project, ROLE_ADMIN, ROLE_MANAGER, ROLE_OFFICE, ROLE_OFFICE_MANAGER, ROLE_SUPERVISOR, User
from app.permissions import can_use_project_workflows, can_create_appeal
from app.routes import bp, selected_project, _project_apartment_options, _is_visible_apartment_row, _active_users_for_project, _group_project_apartments, _build_apartment_overview, _apartment_sort_value, PO_STATUS_THROWN, format_ru_datetime
from app.security import hit_rate_limit, validate_upload
from app.services.inspection_schedule import has_prior_inspection, inspection_contact_lines, inspection_phone_lines
from app.services.task_service import parse_date, text_field_search_clause
from app.time_utils import to_moscow_datetime, utc_now

APPEAL_STATUSES = {'required': 'Ждет ответа', 'in_progress': 'В работе', 'done': 'Выполнено'}
BOOKING_STATUSES = {'booked': 'Запланирован', 'completed': 'Осмотр проведён', 'cancelled': 'Отменён'}
APPEAL_ATTACHMENT_TYPES = {'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}


def project_context():
    if not can_use_project_workflows(current_user):
        abort(403)
    return selected_project()


def project_item(model, item_id, project):
    item = db.session.get(model, item_id)
    if item is None:
        g.http_error_reason = "workflow_item_not_found"
        abort(404)
    item_project = item.slot.project_id if isinstance(item, InspectionBooking) else item.project_id
    if not project or item_project != project.id or not current_user.can_access_project(project):
        g.http_error_reason = "workflow_project_mismatch_or_denied"
        abort(404)
    return item


def selected_apartment(project):
    apartment_id = request.form.get('apartment_id', type=int)
    apartment = db.session.get(Apartment, apartment_id) if apartment_id else None
    if not apartment or apartment.project_id != project.id or not _is_visible_apartment_row(apartment):
        raise ValueError('Выберите помещение этого объекта.')
    return apartment


def staff_options(project):
    return [u for u in _active_users_for_project(project.id) if can_use_project_workflows(u)]


def booking_fields(project):
    staff_id = request.form.get('staff_id', type=int)
    staff = db.session.get(User, staff_id) if staff_id else None
    if staff_id and (not staff or not staff.is_active or not staff.can_access_project(project) or not can_use_project_workflows(staff)):
        raise ValueError('Выберите ответственного этого объекта.')
    contact = request.form.get('contact', '').strip()
    phone = request.form.get('contact_phone', '').strip()
    note = request.form.get('note', '').strip()
    if len(contact) > 255 or len(phone) > 255 or len(note) > 4000:
        raise ValueError('Контакт — до 255 символов, примечание — до 4000.')
    return staff_id, contact, phone, note


def requested_appointment_time(slot, exclude_booking_id=None):
    raw = request.form.get('appointment_time') or slot.start_time.strftime('%H:%M')
    try:
        chosen = datetime.strptime(raw, '%H:%M').time()
    except ValueError:
        raise ValueError('Выберите время осмотра.') from None
    begins = datetime.combine(slot.day, chosen)
    finishes = begins + timedelta(minutes=slot.duration_minutes)
    if finishes.date() != slot.day:
        raise ValueError('Осмотр должен завершиться в тот же день.')
    existing = InspectionBooking.query.join(InspectionSlot, InspectionBooking.slot_id == InspectionSlot.id).filter(
        InspectionSlot.project_id == slot.project_id, InspectionSlot.day == slot.day,
        InspectionBooking.active_slot_id.isnot(None)
    ).options(selectinload(InspectionBooking.slot)).all()
    for booking in existing:
        if booking.id == exclude_booking_id:
            continue
        other_start = datetime.combine(slot.day, booking.appointment_time or booking.slot.start_time)
        other_finish = other_start + timedelta(minutes=booking.slot.duration_minutes)
        if begins < other_finish and finishes > other_start:
            raise ValueError('Это время уже занято. Выберите другое время.')
    return chosen


@bp.route('/appeals')
@login_required
def appeals():
    project = project_context()
    if project is None:
        return redirect(url_for('main.objects'))
    query = Appeal.query.filter_by(project_id=project.id).options(selectinload(Appeal.apartment), selectinload(Appeal.created_by))
    status = request.args.get('status', '')
    if status in APPEAL_STATUSES:
        query = query.filter(Appeal.status == status)
    q = request.args.get('q', '').strip()
    if q:
        query = query.join(Apartment).filter(or_(
            text_field_search_clause(Appeal.body, q),
            text_field_search_clause(Appeal.caller_name, q),
            text_field_search_clause(Appeal.caller_phone, q),
            text_field_search_clause(Apartment.owner_name, q),
            text_field_search_clause(Apartment.phone, q),
            text_field_search_clause(Apartment.apartment_number, q),
            text_field_search_clause(Apartment.construction_number, q),
        ))
    page = max(1, request.args.get('page', 1, type=int) or 1)
    pagination = query.order_by(Appeal.created_at.desc(), Appeal.id.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('appeals.html', project=project, pagination=pagination, statuses=APPEAL_STATUSES, status=status, q=q)


@bp.route('/appeals/new', methods=['GET', 'POST'])
@login_required
def appeal_new():
    if not can_create_appeal(current_user):
        abort(403)
    project = project_context()
    if project is None:
        return redirect(url_for('main.objects'))
    if request.method == 'POST':
        saved_path = None
        try:
            apartment = selected_apartment(project)
            body = request.form.get('body', '').strip()
            caller_name = request.form.get('caller_name', '').strip()
            caller_phone = request.form.get('caller_phone', '').strip()
            if not caller_name or len(caller_name) > 180:
                raise ValueError('Укажите имя позвонившего — до 180 символов.')
            if not caller_phone or len(caller_phone) > 100 or not any(char.isdigit() for char in caller_phone):
                raise ValueError('Укажите номер телефона позвонившего — до 100 символов.')
            if not body or len(body) > 4000:
                raise ValueError('Введите обращение длиной до 4000 символов.')
            if hit_rate_limit('appeal-create', 30, 300):
                abort(429)
            appeal = Appeal(project_id=project.id, apartment_id=apartment.id, created_by_id=current_user.id, body=body, caller_name=caller_name, caller_phone=caller_phone, status='required')
            db.session.add(appeal)
            upload = request.files.get('attachment')
            if upload and upload.filename:
                validate_upload(upload, APPEAL_ATTACHMENT_TYPES, max_size=current_app.config.get('MAX_UPLOAD_FILE_BYTES'))
                original_name = Path(upload.filename).name[:255]
                suffix = Path(original_name).suffix.lower().lstrip('.')
                normalized_suffix = 'jpg' if suffix == 'jpeg' else suffix
                stored_name = f'{uuid4().hex}.{normalized_suffix}'
                folder = Path(current_app.config['UPLOAD_FOLDER']) / 'appeals' / str(project.id)
                folder.mkdir(parents=True, exist_ok=True)
                saved_path = folder / stored_name
                upload.stream.seek(0)
                upload.save(saved_path)
                appeal.attachment = AppealAttachment(
                    original_name=original_name,
                    stored_name=stored_name,
                    mime_type=APPEAL_ATTACHMENT_TYPES[suffix],
                    size_bytes=saved_path.stat().st_size,
                )
            db.session.commit()
            return redirect(url_for('main.appeal_detail', appeal_id=appeal.id))
        except ValueError as error:
            db.session.rollback()
            if saved_path:
                saved_path.unlink(missing_ok=True)
            flash(str(error), 'warning')
    return render_template('appeal_form.html', project=project, apartments=_project_apartment_options(project.id))


@bp.route('/appeals/<int:appeal_id>', methods=['GET', 'POST'])
@login_required
def appeal_detail(appeal_id):
    project = project_context()
    appeal = project_item(Appeal, appeal_id, project)
    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if not body or len(body) > 4000:
            flash('Введите комментарий длиной до 4000 символов.', 'warning')
        else:
            if hit_rate_limit('appeal-comment', 60, 300):
                abort(429)
            db.session.add(AppealComment(appeal=appeal, user_id=current_user.id, body=body))
            db.session.commit()
            return redirect(url_for('main.appeal_detail', appeal_id=appeal.id))
    return render_template('appeal_detail.html', project=project, appeal=appeal, statuses=APPEAL_STATUSES)


@bp.route('/appeals/<int:appeal_id>/edit', methods=['GET', 'POST'])
@login_required
def appeal_edit(appeal_id):
    project = project_context()
    appeal = project_item(Appeal, appeal_id, project)
    if current_user.role != ROLE_ADMIN and appeal.created_by_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        try:
            apartment_id = request.form.get('apartment_id', type=int)
            apartment = db.session.get(Apartment, apartment_id) if apartment_id else None
            if apartment is None or apartment.project_id != project.id:
                raise ValueError('Выберите помещение.')
            body = request.form.get('body', '').strip()
            caller_name = request.form.get('caller_name', '').strip()
            caller_phone = request.form.get('caller_phone', '').strip()
            if not caller_name or len(caller_name) > 180:
                raise ValueError('Укажите имя позвонившего — до 180 символов.')
            if not caller_phone or len(caller_phone) > 100 or not any(char.isdigit() for char in caller_phone):
                raise ValueError('Укажите номер телефона позвонившего — до 100 символов.')
            if not body or len(body) > 4000:
                raise ValueError('Введите обращение длиной до 4000 символов.')
            appeal.apartment = apartment
            appeal.body, appeal.caller_name, appeal.caller_phone = body, caller_name, caller_phone
            upload = request.files.get('attachment')
            if upload and upload.filename:
                validate_upload(upload, APPEAL_ATTACHMENT_TYPES, max_size=current_app.config.get('MAX_UPLOAD_FILE_BYTES'))
                folder = Path(current_app.config['UPLOAD_FOLDER']) / 'appeals' / str(project.id)
                folder.mkdir(parents=True, exist_ok=True)
                original_name = Path(upload.filename).name[:255]
                suffix = Path(original_name).suffix.lower().lstrip('.')
                normalized_suffix = 'jpg' if suffix == 'jpeg' else suffix
                stored_name = f'{uuid4().hex}.{normalized_suffix}'
                saved_path = folder / stored_name
                upload.save(saved_path)
                if appeal.attachment:
                    old = (folder / appeal.attachment.stored_name).resolve()
                    if old.parent == folder.resolve(): old.unlink(missing_ok=True)
                    appeal.attachment.original_name, appeal.attachment.stored_name = original_name, stored_name
                    appeal.attachment.mime_type, appeal.attachment.size_bytes = APPEAL_ATTACHMENT_TYPES[suffix], saved_path.stat().st_size
                else:
                    appeal.attachment = AppealAttachment(original_name=original_name, stored_name=stored_name, mime_type=APPEAL_ATTACHMENT_TYPES[suffix], size_bytes=saved_path.stat().st_size)
            db.session.commit()
            return redirect(url_for('main.appeal_detail', appeal_id=appeal.id))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), 'warning')
    return render_template('appeal_form.html', project=project, apartments=_project_apartment_options(project.id), appeal=appeal, edit_mode=True)


@bp.route('/appeals/<int:appeal_id>/attachment')
@login_required
def appeal_attachment(appeal_id):
    project = project_context()
    appeal = project_item(Appeal, appeal_id, project)
    attachment = appeal.attachment or abort(404)
    folder = (Path(current_app.config['UPLOAD_FOLDER']) / 'appeals' / str(project.id)).resolve()
    path = (folder / attachment.stored_name).resolve()
    if path.parent != folder or not path.is_file():
        abort(404)
    return send_file(
        path,
        mimetype=attachment.mime_type,
        as_attachment=False,
        download_name=attachment.original_name,
        conditional=True,
    )


@bp.route('/appeals/<int:appeal_id>/delete', methods=['POST'])
@login_required
def appeal_delete(appeal_id):
    project = project_context()
    appeal = project_item(Appeal, appeal_id, project)
    if current_user.role != ROLE_ADMIN and appeal.created_by_id != current_user.id:
        abort(403)
    attachment_path = None
    if appeal.attachment:
        folder = (Path(current_app.config['UPLOAD_FOLDER']) / 'appeals' / str(project.id)).resolve()
        candidate = (folder / appeal.attachment.stored_name).resolve()
        if candidate.parent == folder:
            attachment_path = candidate
    db.session.delete(appeal)
    db.session.commit()
    if attachment_path:
        attachment_path.unlink(missing_ok=True)
    flash('Обращение удалено.', 'success')
    return redirect(url_for('main.appeals'))


@bp.route('/appeals/<int:appeal_id>/status', methods=['POST'])
@login_required
def appeal_status(appeal_id):
    project = project_context()
    appeal = project_item(Appeal, appeal_id, project)
    status = request.form.get('status')
    if status not in APPEAL_STATUSES:
        abort(400)
    if hit_rate_limit('appeal-status', 60, 300):
        abort(429)
    if appeal.status != status:
        appeal.status = status
        db.session.add(AppealComment(appeal=appeal, user_id=current_user.id, body='Статус: ' + APPEAL_STATUSES[status], is_system=True))
        db.session.commit()
    return redirect(url_for('main.appeal_detail', appeal_id=appeal.id))


def calendar_period(value, view):
    if not 2000 <= value.year <= 2100:
        abort(400)
    if view == 'month':
        first = value.replace(day=1)
        last = value.replace(day=monthrange(value.year, value.month)[1])
        start = first - timedelta(days=first.weekday())
        end = last + timedelta(days=6-last.weekday())
        previous = (first - timedelta(days=1)).replace(day=1)
        following = (last + timedelta(days=1)).replace(day=1)
    elif view == 'week':
        start = value - timedelta(days=value.weekday()); end = start + timedelta(days=6)
        previous = start - timedelta(days=7); following = start + timedelta(days=7)
    else:
        start = end = value; previous = value - timedelta(days=1); following = value + timedelta(days=1)
    return start, end, previous, following


def _inspection_call_list_rows(project_id, include_hidden=False):
    rows = [
        row for group in _group_project_apartments(project_id, include_activity=False)
        if (row := _build_apartment_overview(group, include_activity=False))['po_status'] == PO_STATUS_THROWN
        and row['inspection_status'] != 'Будет'
        and row['mode'] != 'не продана'
    ]
    for row in rows:
        row['call_list_hidden'] = any(item.call_list_hidden for item in row['apartments'])
    if not include_hidden:
        rows = [row for row in rows if not row['call_list_hidden']]
    rows.sort(key=lambda row: _apartment_sort_value(row['apartment']))
    return rows


@bp.route('/records/call-list')
@login_required
def records_call_list():
    project = project_context()
    if project is None:
        return redirect(url_for('main.objects'))
    all_rows = _inspection_call_list_rows(project.id, include_hidden=True)
    show_hidden = request.args.get('hidden') == '1'
    rows = [row for row in all_rows if row['call_list_hidden'] == show_hidden]
    hidden_count = sum(row['call_list_hidden'] for row in all_rows)
    apartment_ids = [apartment.id for row in rows for apartment in row['apartments']]
    notes = InspectionCallNote.query.filter(
        InspectionCallNote.project_id == project.id,
        InspectionCallNote.apartment_id.in_(apartment_ids),
    ).options(selectinload(InspectionCallNote.user)).order_by(InspectionCallNote.created_at, InspectionCallNote.id).all() if apartment_ids else []
    for row in rows:
        group_ids = {apartment.id for apartment in row['apartments']}
        row['call_notes'] = [note for note in notes if note.apartment_id in group_ids]
    return render_template('records_call_list.html', project=project, rows=rows, hidden_count=hidden_count,
                           show_hidden=show_hidden, format_ru_datetime=format_ru_datetime)


@bp.post('/records/call-list/<int:apartment_id>/visibility')
@login_required
def records_call_list_visibility(apartment_id):
    project = project_context()
    if current_user.role == 'viewer':
        abort(403)
    apartment = project_item(Apartment, apartment_id, project)
    hidden = request.form.get('hidden')
    if hidden not in {'0', '1'}:
        abort(400)
    row = next((row for row in _inspection_call_list_rows(project.id, include_hidden=True)
                if row['apartment'].id == apartment.id), None)
    if row is None:
        abort(409)
    if hit_rate_limit('inspection-call-visibility', 60, 300):
        abort(429)
    for item in row['apartments']:
        item.call_list_hidden = hidden == '1'
    db.session.commit()
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(ok=True, hidden=hidden == '1')
    return redirect(url_for('main.records_call_list'), code=303)


@bp.route('/records/call-list/<int:apartment_id>/comments', methods=['POST'])
@login_required
def records_call_list_comment(apartment_id):
    project = project_context()
    apartment = db.session.get(Apartment, apartment_id) or abort(404)
    if project is None or apartment.project_id != project.id or not _is_visible_apartment_row(apartment):
        abort(404)
    if not any(row['apartment'].id == apartment_id for row in _inspection_call_list_rows(project.id)):
        abort(409)
    body = (request.form.get('body') or '').strip()
    if not body or len(body) > 1000:
        abort(400)
    if hit_rate_limit('inspection-call-comment', 40, 300):
        abort(429)
    note = InspectionCallNote(project_id=project.id, apartment_id=apartment_id, user_id=current_user.id, body=body)
    db.session.add(note)
    db.session.commit()
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(ok=True, note={'id': note.id, 'body': note.body, 'author': current_user.full_name or current_user.username, 'date': format_ru_datetime(note.created_at), 'delete_url': url_for('main.records_call_list_comment_delete', apartment_id=apartment_id, note_id=note.id)})
    return redirect(url_for('main.records_call_list') + f'#call-list-{apartment_id}')


@bp.route('/records/call-list/<int:apartment_id>/comments/<int:note_id>/delete', methods=['POST'])
@login_required
def records_call_list_comment_delete(apartment_id, note_id):
    project = project_context()
    note = db.session.get(InspectionCallNote, note_id) or abort(404)
    if project is None or note.project_id != project.id or note.apartment_id != apartment_id:
        abort(404)
    if note.user_id != current_user.id and current_user.role not in {ROLE_ADMIN, ROLE_OFFICE_MANAGER}:
        abort(403)
    db.session.delete(note)
    db.session.commit()
    if request.accept_mimetypes.best == 'application/json':
        return jsonify(ok=True)
    return redirect(url_for('main.records_call_list') + f'#call-list-{apartment_id}')


@bp.route('/records')
@login_required
def records():
    project = project_context()
    if project is None:
        return redirect(url_for('main.objects'))
    call_list_count = len(_inspection_call_list_rows(project.id))
    today = to_moscow_datetime(utc_now()).date()
    value = parse_date(request.args.get('date')) or today
    view = request.args.get('view', 'day')
    if view not in {'day', 'week', 'month'}:
        view = 'day'
    start, end, previous, following = calendar_period(value, view)
    slots = InspectionSlot.query.filter(InspectionSlot.project_id == project.id, InspectionSlot.day.between(start, end)).order_by(InspectionSlot.day, InspectionSlot.start_time).all()
    bookings = InspectionBooking.query.filter(InspectionBooking.active_slot_id.in_([slot.id for slot in slots])).options(selectinload(InspectionBooking.apartment), selectinload(InspectionBooking.staff)).all() if slots else []
    booked = {booking.slot_id: booking for booking in bookings}
    occupied_intervals = [(datetime.combine(booking.slot.day, booking.appointment_time or booking.slot.start_time),
                           datetime.combine(booking.slot.day, booking.appointment_time or booking.slot.start_time) + timedelta(minutes=booking.slot.duration_minutes)) for booking in bookings]
    days = [{'date': start + timedelta(days=i), 'slots': []} for i in range((end-start).days + 1)]
    by_day = {day['date']: day for day in days}
    can_view_closed_slots = current_user.role in {ROLE_ADMIN, ROLE_MANAGER, ROLE_OFFICE, ROLE_OFFICE_MANAGER}
    for slot in slots:
        if not slot.is_open and slot.id not in booked and not can_view_closed_slots and slot.closed_by_user_id != current_user.id:
            continue
        begins = datetime.combine(slot.day, slot.start_time)
        unavailable = not booked.get(slot.id) and any(begins < finish and begins + timedelta(minutes=slot.duration_minutes) > start_time for start_time, finish in occupied_intervals)
        by_day[slot.day]['slots'].append({'slot': slot, 'booking': booked.get(slot.id), 'unavailable': unavailable})
    cancelled = InspectionBooking.query.join(InspectionSlot, InspectionBooking.slot_id == InspectionSlot.id).filter(InspectionSlot.project_id == project.id, InspectionSlot.day.between(start, end), InspectionBooking.status == 'cancelled').order_by(InspectionSlot.day, InspectionSlot.start_time).all()
    return render_template('records.html', project=project, today=today, selected=value, view=view, start=start, end=end,
                           previous=previous, following=following, days=days, cancelled=cancelled, statuses=BOOKING_STATUSES,
                           leading=0, availability=request.args.get('availability')=='1', availability_end=(value + timedelta(days=62)).isoformat(),
                           has_prior_inspection=has_prior_inspection, inspection_contact_lines=inspection_contact_lines,
                           inspection_phone_lines=inspection_phone_lines,
                           can_manage_closed_interval=current_user.role in {ROLE_ADMIN, ROLE_OFFICE_MANAGER},
                           can_view_closed_slots=can_view_closed_slots,
                           can_configure_inspections=current_user.role != ROLE_SUPERVISOR,
                           call_list_count=call_list_count)


@bp.route('/records/availability', methods=['GET'])
@login_required
def records_availability_page():
    if current_user.role == ROLE_SUPERVISOR:
        abort(403)
    project = project_context()
    if project is None:
        return redirect(url_for('main.objects'))
    today = to_moscow_datetime(utc_now()).date()
    selected = parse_date(request.args.get('date')) or today
    return render_template('records_availability.html', project=project, selected=selected,
                           availability_end=(selected + timedelta(days=62)).isoformat())


@bp.route('/records/availability', methods=['POST'])
@login_required
def records_availability():
    if current_user.role == ROLE_SUPERVISOR:
        abort(403)
    project = project_context()
    if project is None:
        return redirect(url_for('main.objects'))
    try:
        start = parse_date(request.form.get('start_date'))
        end = parse_date(request.form.get('end_date')) or start
        if not start or not end or not 2000 <= start.year <= 2100 or not 2000 <= end.year <= 2100 or end < start:
            raise ValueError('Укажите правильные даты начала и окончания периода.')
        begins = datetime.strptime(request.form.get('start_time',''), '%H:%M').time()
        finishes = datetime.strptime(request.form.get('end_time',''), '%H:%M').time()
        lunch_start_raw = request.form.get('lunch_start', '').strip()
        lunch_end_raw = request.form.get('lunch_end', '').strip()
        lunch_start = datetime.strptime(lunch_start_raw, '%H:%M').time() if lunch_start_raw else None
        lunch_end = datetime.strptime(lunch_end_raw, '%H:%M').time() if lunch_end_raw else None
        duration = request.form.get('duration', type=int)
        weekdays = {int(v) for v in request.form.getlist('weekday') if v.isdigit() and 0 <= int(v) <= 6}
        if request.form.get('single_day') == '1':
            end = start
            weekdays = {start.weekday()}
        if duration not in {15,30,45,60,120} or begins >= finishes or not weekdays or ((lunch_start is None) != (lunch_end is None)) or (lunch_start and lunch_start >= lunch_end):
            raise ValueError('Выберите рабочие дни, интервал времени и длительность осмотра.')
        if hit_rate_limit('inspection-availability', 30, 300):
            abort(429)
        # Serialize availability changes, including overlapping intervals on MySQL.
        Project.query.filter_by(id=project.id).with_for_update().first()
        existing = InspectionSlot.query.filter(InspectionSlot.project_id==project.id, InspectionSlot.day.between(start,end)).all()
        intervals = {}
        for slot in existing:
            begin = datetime.combine(slot.day,slot.start_time)
            intervals.setdefault(slot.day,[]).append((begin,begin+timedelta(minutes=slot.duration_minutes)))
        created = 0
        for offset in range((end-start).days+1):
            day = start + timedelta(days=offset)
            if day.weekday() not in weekdays:
                continue
            moment = datetime.combine(day,begins); limit = datetime.combine(day,finishes)
            while moment + timedelta(minutes=duration) <= limit:
                finish = moment + timedelta(minutes=duration)
                lunch_begin = datetime.combine(day, lunch_start) if lunch_start else None
                lunch_finish = datetime.combine(day, lunch_end) if lunch_end else None
                in_lunch = lunch_begin and lunch_finish and moment < lunch_finish and finish > lunch_begin
                if not in_lunch and not any(moment < b and finish > a for a,b in intervals.get(day,[])):
                    db.session.add(InspectionSlot(project_id=project.id,day=day,start_time=moment.time(),duration_minutes=duration,is_open=True))
                    intervals.setdefault(day,[]).append((moment,finish)); created += 1
                    if created > 25000:
                        raise ValueError('Слишком много интервалов за один раз. Сохраните расписание по частям.')
                moment = finish
        db.session.commit()
        flash(f'Добавлено доступных интервалов: {created}. Уже существующие интервалы сохранены.', 'success')
        return redirect(url_for('main.records_availability',date=start.isoformat()))
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        flash(str(error) if isinstance(error,ValueError) else 'Расписание уже изменено. Обновите страницу.', 'warning')
    return redirect(url_for('main.records_availability'))


@bp.route('/records/slots/<int:slot_id>/toggle', methods=['POST'])
@login_required
def record_slot_toggle(slot_id):
    if current_user.role == ROLE_SUPERVISOR:
        abort(403)
    project = project_context()
    slot = project_item(InspectionSlot,slot_id,project)
    # The same lock is used when booking this slot.
    slot = InspectionSlot.query.filter_by(id=slot.id).populate_existing().with_for_update().one()
    wants_json = request.accept_mimetypes.best == 'application/json'
    if not slot.is_open and slot.closed_by_interval and current_user.role not in {ROLE_ADMIN, ROLE_OFFICE_MANAGER}:
        db.session.rollback()
        if wants_json:
            return jsonify(error='Открыть этот интервал может только офис-менеджер или разработчик.'), 403
        abort(403)
    if InspectionBooking.query.filter_by(active_slot_id=slot.id).first():
        db.session.rollback()
        if wants_json:
            return jsonify(error='Сначала отмените запись на это время.'), 409
        flash('Сначала отмените запись на это время.', 'warning')
    else:
        reason = request.form.get('closed_reason', '').strip()
        if slot.is_open and len(reason) > 300:
            db.session.rollback()
            if wants_json:
                return jsonify(error='Комментарий должен быть не длиннее 300 символов.'), 400
            flash('Комментарий должен быть не длиннее 300 символов.', 'warning')
            return redirect(url_for('main.records',date=slot.day.isoformat()))
        slot.closed_reason = (reason or None) if slot.is_open else None
        slot.closed_by_user_id = current_user.id if slot.is_open else None
        slot.closed_by_interval = False
        slot.is_open = not slot.is_open
        db.session.commit()
        if wants_json:
            return jsonify(is_open=slot.is_open, label='Свободно' if slot.is_open else 'Закрыто')
    return redirect(url_for('main.records',date=slot.day.isoformat()))


@bp.route('/records/slots/close-interval', methods=['POST'])
@login_required
def record_slots_close_interval():
    if current_user.role == ROLE_SUPERVISOR:
        abort(403)
    project = project_context()
    if project is None:
        abort(404)
    wants_json = request.accept_mimetypes.best == 'application/json'
    try:
        day = parse_date(request.form.get('day'))
        if not day:
            raise ValueError('Выберите дату.')
        try:
            begins = datetime.strptime(request.form.get('start_time', ''), '%H:%M').time()
            ends = datetime.strptime(request.form.get('end_time', ''), '%H:%M').time()
        except ValueError:
            raise ValueError('Выберите начало и окончание интервала.') from None
        if begins >= ends:
            raise ValueError('Окончание интервала должно быть позже начала.')
        reason = request.form.get('closed_reason', '').strip()
        if len(reason) > 300:
            raise ValueError('Причина должна быть не длиннее 300 символов.')
        slots = InspectionSlot.query.filter(
            InspectionSlot.project_id == project.id, InspectionSlot.day == day,
            InspectionSlot.start_time >= begins, InspectionSlot.start_time < ends,
            InspectionSlot.is_open.is_(True),
        ).with_for_update().all()
        booked_ids = {booking.active_slot_id for booking in InspectionBooking.query.filter(
            InspectionBooking.active_slot_id.in_([slot.id for slot in slots])
        ).all()}
        available = [slot for slot in slots if slot.id not in booked_ids]
        if not available:
            raise ValueError('В выбранном интервале нет свободного времени для закрытия.')
        for slot in available:
            slot.is_open = False
            slot.closed_reason = reason or None
            slot.closed_by_interval = True
            slot.closed_by_user_id = current_user.id
        db.session.commit()
        if wants_json:
            return jsonify(closed_slot_ids=[slot.id for slot in available], count=len(available),
                           closed_reason=reason if current_user.role in {ROLE_ADMIN, ROLE_OFFICE_MANAGER} else '')
        flash(f'Закрыто интервалов: {len(available)}.', 'success')
    except ValueError as error:
        db.session.rollback()
        if wants_json:
            return jsonify(error=str(error)), 400
        flash(str(error), 'warning')
    return redirect(url_for('main.records', date=request.form.get('day') or date.today().isoformat()))


@bp.route('/records/apartment/<int:apartment_id>/book', methods=['GET', 'POST'])
@login_required
def record_apartment_new(apartment_id):
    project = project_context()
    apartment = project_item(Apartment, apartment_id, project)
    if not _is_visible_apartment_row(apartment):
        abort(404)
    selected_day = parse_date(request.values.get('date'))
    if request.method == 'POST':
        try:
            slot_id = request.form.get('slot_id', type=int)
            if not selected_day or not slot_id:
                raise ValueError('Выберите дату и свободное время осмотра.')
            Project.query.filter_by(id=project.id).with_for_update().first()
            slot = InspectionSlot.query.filter_by(id=slot_id, project_id=project.id, day=selected_day).with_for_update().first()
            if not slot or not slot.is_open or InspectionBooking.query.filter_by(active_slot_id=slot_id).first():
                raise ValueError('Это время уже занято или закрыто. Выберите другое время.')
            appointment_time = requested_appointment_time(slot)
            staff_id, contact, phone, note = booking_fields(project)
            if hit_rate_limit('inspection-book', 60, 300):
                abort(429)
            db.session.add(InspectionBooking(slot_id=slot.id, active_slot_id=slot.id,
                appointment_time=appointment_time, apartment_id=apartment.id,
                created_by_id=current_user.id, staff_id=staff_id, contact=contact,
                contact_phone=phone, note=note, status='booked'))
            apartment.inspection_note = f'__inspection_schedule__:{selected_day.isoformat()}'
            db.session.commit()
            return redirect(url_for('main.records', date=selected_day.isoformat()))
        except (ValueError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error, ValueError) else 'Это время уже занято. Выберите другое время.', 'warning')
    slots = InspectionSlot.query.filter_by(project_id=project.id, day=selected_day).order_by(InspectionSlot.start_time).all() if selected_day else []
    bookings = InspectionBooking.query.join(InspectionSlot, InspectionBooking.slot_id == InspectionSlot.id).filter(
        InspectionSlot.project_id == project.id, InspectionSlot.day == selected_day,
        InspectionBooking.active_slot_id.isnot(None)).options(selectinload(InspectionBooking.slot)).all() if selected_day else []
    occupied = [(datetime.combine(selected_day, booking.appointment_time or booking.slot.start_time),
                 datetime.combine(selected_day, booking.appointment_time or booking.slot.start_time) + timedelta(minutes=booking.slot.duration_minutes)) for booking in bookings]
    available = []
    booked_ids = {booking.slot_id for booking in bookings}
    for slot in slots:
        begins = datetime.combine(selected_day, slot.start_time)
        ends = begins + timedelta(minutes=slot.duration_minutes)
        if slot.is_open and slot.id not in booked_ids and not any(begins < finish and ends > start for start, finish in occupied):
            available.append(slot)
    return render_template('record_apartment_form.html', project=project, apartment=apartment,
                           selected_day=selected_day, available=available,
                           inspection_contact_lines=inspection_contact_lines,
                           has_prior_inspection=has_prior_inspection)


@bp.route('/records/slots/<int:slot_id>/book', methods=['GET','POST'])
@login_required
def record_new(slot_id):
    project = project_context()
    slot = project_item(InspectionSlot,slot_id,project)
    if request.method == 'POST':
        try:
            Project.query.filter_by(id=project.id).with_for_update().first()
            slot = InspectionSlot.query.filter_by(id=slot.id).populate_existing().with_for_update().one()
            if not slot.is_open or InspectionBooking.query.filter_by(active_slot_id=slot.id).first():
                raise ValueError('Это время уже занято или закрыто. Выберите другой интервал.')
            appointment_time = requested_appointment_time(slot)
            apartment = selected_apartment(project)
            staff_id,contact,phone,note = booking_fields(project)
            if hit_rate_limit('inspection-book', 60, 300):
                abort(429)
            booking = InspectionBooking(slot_id=slot.id,active_slot_id=slot.id,appointment_time=appointment_time,apartment_id=apartment.id,
                                        created_by_id=current_user.id,staff_id=staff_id,contact=contact,contact_phone=phone,note=note,status='booked')
            apartment.inspection_note = f"__inspection_schedule__:{slot.day.isoformat()}"
            db.session.add(booking); db.session.commit()
            return redirect(url_for('main.records',date=slot.day.isoformat()))
        except (ValueError,IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error,ValueError) else 'Это время уже занято. Выберите другой интервал.', 'warning')
    return render_template('record_form.html',project=project,slot=slot,booking=None,apartments=_project_apartment_options(project.id),staff_options=staff_options(project),statuses=BOOKING_STATUSES)


@bp.route('/records/<int:booking_id>', methods=['GET','POST'])
@login_required
def record_detail(booking_id):
    project = project_context()
    booking = project_item(InspectionBooking,booking_id,project)
    if request.method == 'POST':
        try:
            Project.query.filter_by(id=project.id).with_for_update().first()
            InspectionSlot.query.filter_by(id=booking.slot_id).with_for_update().one()
            appointment_time = requested_appointment_time(booking.slot, booking.id)
            staff_id,contact,phone,note = booking_fields(project)
            booking.staff_id=staff_id; booking.contact=contact; booking.contact_phone=phone; booking.note=note; booking.appointment_time=appointment_time
            db.session.commit(); flash('Запись обновлена.', 'success')
            return redirect(url_for('main.records',date=booking.slot.day.isoformat()))
        except ValueError as error:
            flash(str(error),'warning')
    return render_template('record_form.html',project=project,slot=booking.slot,booking=booking,apartments=[],staff_options=staff_options(project),statuses=BOOKING_STATUSES)


@bp.route('/records/<int:booking_id>/status', methods=['POST'])
@login_required
def record_status(booking_id):
    project=project_context()
    booking=project_item(InspectionBooking,booking_id,project)
    # Lock slot first, consistently with booking and availability controls.
    InspectionSlot.query.filter_by(id=booking.slot_id).with_for_update().one()
    db.session.refresh(booking)
    status=request.form.get('status')
    if status not in {'completed','cancelled'} or booking.status=='cancelled':
        abort(400)
    if hit_rate_limit('inspection-status', 60, 300):
        abort(429)
    if status=='completed' and booking.status!='completed':
        from app.services.inspection_completion import complete_inspection
        complete_inspection(booking)
    else:
        booking.status=status
    if status=='cancelled':
        booking.active_slot_id=None
        if booking.apartment.inspection_note and booking.apartment.inspection_note.startswith('__inspection_schedule__:'):
            booking.apartment.inspection_note = None
    db.session.commit()
    return redirect(url_for('main.records',date=booking.slot.day.isoformat()))


@bp.route('/records/download')
@login_required
def records_download():
    project=project_context()
    if project is None:
        return redirect(url_for('main.objects'))
    day=parse_date(request.args.get('date')) or to_moscow_datetime(utc_now()).date()
    bookings=InspectionBooking.query.join(InspectionSlot,InspectionBooking.slot_id==InspectionSlot.id).filter(
        InspectionSlot.project_id==project.id,InspectionSlot.day==day,InspectionBooking.active_slot_id.isnot(None)
    ).options(selectinload(InspectionBooking.apartment),selectinload(InspectionBooking.staff)).order_by(InspectionSlot.start_time).all()
    from app.services.inspection_schedule import render_schedule_png
    slots=InspectionSlot.query.filter_by(project_id=project.id,day=day).order_by(InspectionSlot.start_time).all()
    try:
        output=render_schedule_png(project,day,bookings,slots)
    except RuntimeError as error:
        flash(str(error), 'warning')
        return redirect(url_for('main.records',date=day.isoformat()))
    return send_file(BytesIO(output),mimetype='image/png',as_attachment=True,download_name=f'Записи на осмотр {day.strftime("%d.%m.%Y")}.png')


@bp.before_request
def settle_elapsed_inspection_appointments():
    if request.method not in {'GET','HEAD'} or not current_user.is_authenticated or not request.endpoint:
        return
    project=selected_project()
    if project is not None and current_user.can_access_project(project):
        from app.services.inspection_completion import complete_elapsed_inspections
        complete_elapsed_inspections(project.id)
