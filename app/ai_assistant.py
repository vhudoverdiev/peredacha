"""Authenticated, read-only help; permissions are checked on every request."""
import re
import json
from functools import lru_cache
from flask import Blueprint, jsonify, request, g
from flask_login import current_user, login_required
from app.services.ai_assistant import KnowledgeAssistant

bp = Blueprint('ai_assistant', __name__, url_prefix='/ai-assistant')

@lru_cache(maxsize=1)
def knowledge():
    return KnowledgeAssistant()


def permitted(entry):
    cache = getattr(g, '_ai_permissions', None)
    current_request = request._get_current_object()
    if cache is None or getattr(g, '_ai_permission_request', None) is not current_request:
        cache = g._ai_permissions = {}
        g._ai_permission_request = current_request
    key = (entry['access']['section'], entry['access']['action'])
    if key not in cache:
        cache[key] = _permitted(entry)
    return cache[key]


def _permitted(entry):
    from app.role_settings import ACTIONS, allowed, effective
    from app.routes import SECTION_LOCK_CHOICES, _blocked_section_keys
    from app.permissions import OFFICE_MANAGER_ROLES
    if current_user.role == 'admin':
        return True
    section = entry['access']['section']
    action = entry['access']['action']
    if section and section in _blocked_section_keys():
        return False
    if section == 'service' and current_user.role in OFFICE_MANAGER_ROLES:
        return False
    # These help topics describe administrator-only handlers, not just their tabs.
    if section in {'users', 'site_errors'}:
        return False
    policy = effective(current_user.role)
    if action:
        item = next((item for item in ACTIONS if item[0] == action), None)
        if not item or action not in policy['actions']:
            return False
        if item[3] and not any(allowed(current_user, endpoint, mutation=True) for endpoint in item[3]):
            return False
    if section:
        item = next((item for item in SECTION_LOCK_CHOICES if item['key'] == section), None)
        if not item or section not in policy['sections']:
            return False
        if not any(allowed(current_user, endpoint) for endpoint in item['endpoints']):
            return False
    return True


def visible_faq():
    engine = knowledge()
    by_question = {entry['question']: entry for entry in engine.entries}
    return [item for item in engine.faq() if permitted(by_question[item['question']])]


@bp.app_context_processor
def widget_context():
    support = dict(phone='', tel='', text='')
    if current_user.is_authenticated:
        from app.routes import _setting_bool, _role_shows_support
        from app.services.task_service import get_setting
        if _setting_bool('objects_support_enabled') and _role_shows_support(current_user.role):
            phone = (get_setting('objects_support_phone', '') or '').strip()
            support = dict(phone=phone, tel=re.sub(r'[^+0-9]', '', phone),
                           text=get_setting('objects_support_text', 'Поддержка') or 'Поддержка')
    return {'ai_support': support}


@bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store, no-cache, must-revalidate'
    return response


@bp.get('')
@login_required
def info():
    return jsonify(faqs=visible_faq())


def consume_daily_question(user_id):
    from app import db
    from app.models import AppSetting, User
    from app.time_utils import utc_now, to_moscow_datetime
    today = to_moscow_datetime(utc_now()).date().isoformat()
    # Serialise the short counter update across workers, including first use.
    db.session.query(User.id).filter_by(id=user_id).with_for_update().one()
    key = f'ai_daily_questions:{user_id}'
    setting = AppSetting.query.filter_by(key=key).with_for_update().first()
    value = json.loads(setting.value) if setting and setting.value else {}
    used = int(value.get('count', 0)) if value.get('date') == today else 0
    if used >= 40:
        db.session.rollback()
        return False
    if setting is None:
        setting = AppSetting(key=key)
        db.session.add(setting)
    setting.value = json.dumps({'date': today, 'count': used + 1})
    db.session.commit()
    return True


@bp.post('/ask')
@login_required
def ask():
    from app.security import hit_rate_limit
    if request.content_length and request.content_length > 8192:
        return jsonify(error='Вопрос слишком большой'), 413
    data = request.get_json(silent=True)
    question = data.get('question') if isinstance(data, dict) else None
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        return jsonify(error='Введите вопрос от 1 до 1000 символов'), 400
    if hit_rate_limit('ai_assistant', 30, 60, subject=str(current_user.id)):
        return jsonify(error='Слишком много вопросов. Попробуйте через минуту.'), 429
    if hit_rate_limit('ai_assistant_interval', 1, 2, subject=str(current_user.id)):
        return jsonify(error='Подождите 2 секунды перед следующим вопросом.'), 429
    if not consume_daily_question(current_user.id):
        return jsonify(error='Вы использовали 40 вопросов за сутки. Лимит обновится в 00:00 по московскому времени.'), 429
    engine = knowledge()
    by_question = {entry['question']: entry for entry in engine.entries}
    result = engine.answer(question.strip())
    entry = by_question.get(result['title'])
    defaults = visible_faq()[:3]
    if entry and not permitted(entry):
        return jsonify(found=False, title='Подберём доступное действие',
                       steps=['Выберите доступный вопрос ниже или уточните задачу.'], related=defaults)
    result['related'] = [item for item in result.get('related', [])
                         if item['question'] in by_question and permitted(by_question[item['question']])]
    if result['title'] in {'Чем могу помочь', 'Здравствуйте! Я AI агент'}:
        groups = list(dict.fromkeys(entry['group'] for entry in engine.entries if permitted(entry)))
        result['steps'] = ['Помогу с доступными вам темами: ' + ', '.join(groups) + '.',
                           'Выберите частый вопрос или задайте свой. Я не изменяю данные в CRM.']
        result['related'] = defaults
    elif not result['found'] and not result['related']:
        result['related'] = defaults
    return jsonify(result)
