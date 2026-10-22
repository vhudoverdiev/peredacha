"""Portable phrases only; no users, projects, tasks or database identifiers."""
from hashlib import sha256
import json
from pathlib import Path

from app import db
from app.models import AppSetting
from app.services.remark_catalog import get_catalog
from app.services.remark_learning import store_phrase

LIBRARY_PATH=Path(__file__).resolve().parents[1]/'data'/'remark_library.json'
SCHEMA='remark-library-v1'


def export_library(path=LIBRARY_PATH):
    entries=[{'text':entry['text'],'points':entry['points']} for entry in get_catalog().entries]
    payload=json.dumps({'schema':SCHEMA,'entries':entries},ensure_ascii=False,indent=2)+'\n'
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(payload,encoding='utf-8')
    temporary.replace(path)
    return len(entries)


def import_library(path=LIBRARY_PATH):
    path=Path(path)
    if not path.exists():return 0
    raw=path.read_bytes()
    if len(raw)>50*1024*1024:raise ValueError('Файл справочника превышает 50 МБ.')
    digest=sha256(raw).hexdigest()
    marker='remark_library_portable_sha256'
    if db.session.query(AppSetting.id).filter_by(key=marker,value=digest).first():return 0
    payload=json.loads(raw)
    if not isinstance(payload,dict) or payload.get('schema')!=SCHEMA or not isinstance(payload.get('entries'),list):
        raise ValueError('Неподдерживаемый формат файла формулировок.')
    entries=payload['entries']
    if len(entries)>100000:raise ValueError('В справочнике более 100000 формулировок.')
    # Validate everything before writing. A malformed update never imports half a file.
    for entry in entries:
        if (not isinstance(entry,dict) or not isinstance(entry.get('text'),str) or
            not entry['text'].strip() or len(entry['text'])>100000 or
            not isinstance(entry.get('points'),list) or
            any(not isinstance(point,str) or point not in {str(n) for n in range(10,27)} for point in entry['points'])):
            raise ValueError('Некорректная формулировка или номер пункта в файле справочника.')
    try:
        connection=db.session.connection()
        for entry in entries:
            store_phrase(connection,entry['text'],tuple(sorted(set(entry['points']),key=int)),increment=False,clean=False)
        table=AppSetting.__table__
        if db.engine.dialect.name=='sqlite':
            from sqlalchemy.dialects.sqlite import insert
            statement=insert(table).values(key=marker,value=digest).on_conflict_do_update(index_elements=['key'],set_={'value':digest})
        else:
            from sqlalchemy.dialects.mysql import insert
            statement=insert(table).values(key=marker,value=digest).on_duplicate_key_update(value=digest)
        db.session.execute(statement);db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(entries)
