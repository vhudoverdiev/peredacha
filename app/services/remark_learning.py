"""Transactional collection of new phrases; never self-validates their points."""
from hashlib import sha256
import json
import re
from functools import lru_cache
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session
from app.models import Task, WorkPoint, RemarkLibraryEntry
from app.services.remark_catalog import normalize, point_keys
from app.time_utils import utc_now


@lru_cache(maxsize=1)
def reference_words():
    from app.services.remark_catalog import get_base_catalog
    from app.services.remark_text_cleaning import vocabulary
    return vocabulary(entry['text'] for entry in get_base_catalog().entries)


def record_phrase(mapper,connection,task):
    from sqlalchemy.orm import object_session
    if object_session(task).info.get('retiring_work_point'):
        return
    state=inspect(task)
    if state.persistent and not any(state.attrs[name].history.has_changes() for name in ('description','source_cell_value','work_point_id')):
        return
    point=connection.execute(select(WorkPoint.short_name,WorkPoint.original_column_name).where(WorkPoint.id==task.work_point_id)).first()
    from app.work_points import is_retired_point_label
    if point and (is_retired_point_label(point.short_name) or is_retired_point_label(point.original_column_name)):
        return
    points=(point_keys(point.short_name) or point_keys(point.original_column_name)) if point else ()
    store_phrase(connection, task.description or task.source_cell_value, points)


def store_phrase(connection, text, points, *, increment=True, clean=True):
    # Legacy portable files may still carry the retired internal key.
    if '16' in {str(p) for p in points}:
        return
    text=str(text or '').strip()
    if not text:return
    text=re.sub(r'\s+',' ',text)
    from app.services.remark_text_cleaning import clean_reference
    if clean:
        text=clean_reference(text,reference_words())
    else:
        from app.services.remark_text_cleaning import strip_worker_marker
        text=strip_worker_marker(text)
    if not text:return
    text=re.sub(r'(?<!\d)(?:\+7|8|7)[\s(-]*\d{3}[)\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)','[контакт удалён]',text)
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[контакт удалён]', text)
    first=re.search('[а-яА-ЯёЁa-zA-Z]',text)
    if first:
        i=first.start();text=text[:i]+text[i].upper()+text[i+1:]
    if not increment:
        from app.work_points import retired_phrase_hashes
        if sha256(normalize(text).encode()).hexdigest() in retired_phrase_hashes():
            return
    table=RemarkLibraryEntry.__table__
    values=dict(normalized_hash=sha256(normalize(text).encode()).hexdigest(),point_key=','.join(points),
                text=text,points_json=json.dumps(points),occurrences=1,created_at=utc_now(),updated_at=utc_now())
    if connection.dialect.name=='sqlite':
        from sqlalchemy.dialects.sqlite import insert
        statement=insert(table).values(**values)
        statement=(statement.on_conflict_do_update(index_elements=['normalized_hash','point_key'],set_={'occurrences':table.c.occurrences+1,'updated_at':utc_now()}) if increment else statement.on_conflict_do_nothing(index_elements=['normalized_hash','point_key']))
    else:
        from sqlalchemy.dialects.mysql import insert
        statement=insert(table).values(**values)
        statement=statement.on_duplicate_key_update(**({'occurrences':table.c.occurrences+1,'updated_at':utc_now()} if increment else {'id':table.c.id}))
    connection.execute(statement)


event.listen(Task,'after_insert',record_phrase)
event.listen(Task,'after_update',record_phrase)


def clear_library_cache(session):
    from app.services.remark_catalog import _merged_catalog
    _merged_catalog.cache_clear()


event.listen(Session,'after_commit',clear_library_cache)
event.listen(Session,'after_rollback',clear_library_cache)


def backfill_existing_phrases(*, force=False, batch_size=500):
    """Copy historical phrases once, without editing tasks or inflating repeats."""
    from app import db
    from app.models import AppSetting
    key='remark_library_historical_backfill_v1'
    if not force and db.session.query(AppSetting.id).filter_by(key=key,value='complete').first():
        return 0
    after=0;scanned=0
    while True:
        rows=db.session.execute(select(Task.id,Task.description,Task.source_cell_value,WorkPoint.short_name,WorkPoint.original_column_name)
            .outerjoin(WorkPoint,Task.work_point_id==WorkPoint.id).where(Task.id>after, (Task.source_sheet_name.is_(None)) | (Task.source_sheet_name != 'manual_retired_point')).order_by(Task.id).limit(batch_size)).all()
        if not rows:break
        connection=db.session.connection()
        for row in rows:
            from app.work_points import is_retired_point_label
            if is_retired_point_label(row.short_name) or is_retired_point_label(row.original_column_name):
                continue
            store_phrase(connection,row.description or row.source_cell_value,
                         point_keys(row.short_name) or point_keys(row.original_column_name),increment=False)
        after=rows[-1].id;scanned+=len(rows)
        db.session.commit()
    table=AppSetting.__table__
    if db.engine.dialect.name=='sqlite':
        from sqlalchemy.dialects.sqlite import insert
        statement=insert(table).values(key=key,value='complete')
        statement=statement.on_conflict_do_update(index_elements=['key'],set_={'value':'complete'})
    else:
        from sqlalchemy.dialects.mysql import insert
        statement=insert(table).values(key=key,value='complete').on_duplicate_key_update(value='complete')
    db.session.execute(statement);db.session.commit()
    return scanned
