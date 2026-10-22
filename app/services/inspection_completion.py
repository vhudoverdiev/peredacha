"""Complete elapsed Moscow-time appointment intervals once per booking."""
from datetime import datetime,timedelta
from app import db
from app.models import InspectionBooking,InspectionSlot
from app.time_utils import to_moscow_datetime,utc_now


def complete_inspection(booking):
    from app.routes import (_apartment_group_for_project,_apply_inspection_date_to_group,
                            _parse_inspection_schedule_marker,_log_apartment_field_change,
                            _build_apartment_overview,_add_apartment_inspection_date,
                            _apartment_inspection_values)
    group=_apartment_group_for_project(booking.apartment,booking.slot.project_id)
    old_status=_build_apartment_overview(group,include_activity=False).get('po_status')
    _apply_inspection_date_to_group(group,booking.slot.day)
    for apartment in group:
        marker=_parse_inspection_schedule_marker(apartment.inspection_note)
        marker_day=marker.date() if isinstance(marker,datetime) else marker
        if marker_day==booking.slot.day:
            apartment.inspection_note=(apartment.inspection_note.partition('\n')[2].strip() or None)
            _add_apartment_inspection_date(apartment,booking.slot.day)
            existing={value.date() if isinstance(value,datetime) else value for value in _apartment_inspection_values(apartment)}
            if booking.slot.day not in existing:
                # This day already existed as the booking marker. Preserve it
                # when moving a full legacy history, without adding a new day.
                line=f"Дополнительный осмотр: {booking.slot.day.strftime('%d.%m.%Y')}"
                apartment.inspection_note='\n'.join(filter(None,[apartment.inspection_note,line]))
        apartment.first_inspection_present=True
        apartment.po_status='not_ready';apartment.po_status_manual=True
    _log_apartment_field_change(group,'po_status',old_status,'not_ready')
    booking.status='completed'


def complete_elapsed_inspections(project_id,now=None):
    now=to_moscow_datetime(now or utc_now()).replace(tzinfo=None)
    bookings=(InspectionBooking.query.join(InspectionSlot,InspectionBooking.slot_id==InspectionSlot.id)
        .filter(InspectionSlot.project_id==project_id,InspectionSlot.day<=now.date(),InspectionBooking.status=='booked')
        .order_by(InspectionSlot.id,InspectionBooking.id).all())
    changed=0
    for booking in bookings:
        finish=datetime.combine(booking.slot.day,booking.appointment_time or booking.slot.start_time)+timedelta(minutes=booking.slot.duration_minutes)
        if finish>now:continue
        # Same slot-first lock order as booking/cancellation routes.
        InspectionSlot.query.filter_by(id=booking.slot_id).populate_existing().with_for_update().one()
        db.session.refresh(booking,with_for_update=True)
        finish=datetime.combine(booking.slot.day,booking.appointment_time or booking.slot.start_time)+timedelta(minutes=booking.slot.duration_minutes)
        if booking.status!='booked' or finish>now:continue
        complete_inspection(booking);changed+=1
    if changed:db.session.commit()
    return changed
