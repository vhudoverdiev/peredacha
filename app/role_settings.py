"""Developer-managed section permissions, stored with existing site settings."""
import json
from app.services.task_service import get_setting

def definitions():
    from flask import g, request
    request_key=id(request._get_current_object())
    if getattr(g, '_role_permission_request', None)==request_key and hasattr(g, '_role_permission_definitions'):
        return g._role_permission_definitions
    try:
        data=json.loads(get_setting('role_section_permissions','{}') or '{}')
        data=data if isinstance(data,dict) else {}
    except (ValueError,TypeError):
        data={}
    g._role_permission_request=request_key
    g._role_permission_definitions=data
    return data


def choices():
    from app.models import USER_ROLE_CHOICES
    return [(key,definitions().get(key,{}).get('name',label)) for key,label in USER_ROLE_CHOICES]+[(key,value['name']) for key,value in definitions().items() if key.startswith('custom_')]

def refresh_custom_roles():
    from app.permissions import OFFICE_MANAGER_ROLES
    from app.models import ROLE_LABELS
    for key,value in definitions().items():
        if key.startswith('custom_'):
            OFFICE_MANAGER_ROLES.add(key)
            ROLE_LABELS[key]=value['name']

# Each capability covers its page and its mutation endpoint, including direct URLs.
ACTIONS = [
 ('object_create','objects','Добавлять объекты',{'main.object_new'}),
 ('object_edit','objects','Редактировать объекты',{'main.object_edit'}),
 ('object_delete','objects','Удалять объекты',{'main.object_delete','main.object_delete_confirm'}),
 ('object_order','objects','Менять порядок объектов',{'main.object_order'}),
 ('premise_create','apartments','Добавлять помещения',{'main.premise_new','main.record_apartment_new'}),
 ('premise_edit','apartments','Редактировать данные помещений и режим АПП',{'main.update_apartment_details','main.update_apartment_app_status'}),
 ('premise_inspection','apartments','Изменять сведения об осмотрах',{'main.update_apartment_inspection_status','main.update_apartment_inspection_date','main.delete_apartment_inspection_date','main.update_apartment_inspection_note'}),
 ('premise_comments','apartments','Добавлять комментарии к помещениям',{'main.update_apartment_comment','main.update_apartment_office_manager_comment'}),
 ('premise_internal','apartments','Изменять внутренний статус помещения',{'main.update_apartment_po_status'}),
 ('premise_documents','apartments','Изменять статусы АВР и соглашений',{'main.update_apartment_avr_status','main.update_apartment_addendum_status'}),
 ('remark_create','remarks','Добавлять замечания и распознавать акты',{'main.task_new','main.task_recognition'}),
 ('remark_edit','remarks','Редактировать и разделять замечания',{'main.update_task','main.inline_update_text','main.split_task_remark'}),
 ('remark_status','remarks','Менять статус замечаний',{'main.quick_status'}),
 ('remark_delete','remarks','Удалять замечания',{'main.task_delete'}),
 ('remark_comments','remarks','Добавлять и удалять комментарии',{'main.add_task_comment','main.delete_task_comment'}),
 ('contractor_manage','contractors','Добавлять и редактировать подрядчиков',{'main.contractor_new','main.contractor_edit','main.contractor_points','main.contractor_response_statuses'}),
 ('contractor_delete','contractors','Удалять подрядчиков',{'main.contractor_delete'}),
 ('assignment_manage','assignments','Выдавать задачи и менять исполнителей, даты и статусы',{'main.assignments','main.assignment_unassign'}),
 ('assignment_manual','assignments','Добавлять ручные задачи',{'main.assignment_manual_task_new'}),
 ('assignment_delete','assignments','Удалять задачи у сотрудников',{'main.assignment_delete_from_employee'}),
 ('assignment_priority','assignments','Устанавливать срочность',{'main.assignment_task_priority'}),
 ('assignment_comments','assignments','Оставлять указания и удалять комментарии работников',{'main.assignment_comment_delete','main.assignment_worker_instruction'}),
 ('record_book','records','Записывать на осмотр и редактировать запись',{'main.record_new','main.record_detail'}),
 ('record_status','records','Менять статус записи',{'main.record_status'}),
 ('record_schedule','records','Настраивать время, открывать и закрывать интервалы',{'main.records_availability','main.records_availability_page','main.record_slot_toggle','main.record_slots_close_interval'}),
 ('record_calls','records','Работать со списком обзвона',{'main.records_call_list','main.records_call_list_comment','main.records_call_list_comment_delete','main.records_call_list_visibility'}),
 ('appeal_create','appeals','Создавать обращения',{'main.appeal_new'}),
 ('appeal_edit','appeals','Комментировать обращения и менять статус',{'main.appeal_detail','main.appeal_edit','main.appeal_status'}),
 ('appeal_delete','appeals','Удалять обращения',{'main.appeal_delete'}),
]


def baseline_endpoint(role, endpoint, mutation=False):
    """Mirror the existing role policy without changing the active account."""
    from app.routes import (OFFICE_FORBIDDEN_ENDPOINTS, OFFICE_MANAGER_FORBIDDEN_SECTION_KEYS,
        OFFICE_MANAGER_INSPECTION_ENDPOINTS, SUPERVISOR_FORBIDDEN_ENDPOINTS,
        VIEWER_ALLOWED_GET_ENDPOINTS, WORKER_ALLOWED_ENDPOINTS, _section_lock_choice_for_endpoint)
    from app.models import WORKER_ROLES
    section=_section_lock_choice_for_endpoint(endpoint)
    key=section['key'] if section else None
    if role=='admin': return True
    if endpoint in {'main.object_order','main.premise_new','main.object_delete','main.object_delete_confirm'}: return False
    if key in {'users','service','site_errors'}: return False
    if role in WORKER_ROLES: return endpoint in WORKER_ALLOWED_ENDPOINTS
    if role=='viewer': return not mutation and endpoint in VIEWER_ALLOWED_GET_ENDPOINTS
    if role=='office_manager' and (key in OFFICE_MANAGER_FORBIDDEN_SECTION_KEYS or endpoint in OFFICE_MANAGER_INSPECTION_ENDPOINTS): return False
    if role=='supervisor' and endpoint in SUPERVISOR_FORBIDDEN_ENDPOINTS: return False
    if role in {'office','office_manager'} and endpoint in OFFICE_FORBIDDEN_ENDPOINTS:
        if role=='office' and key=='assignments': return True
        return role=='office_manager' and endpoint=='main.update_apartment_po_status'
    if endpoint=='main.update_apartment_office_manager_comment': return role=='office_manager'
    if endpoint=='main.appeal_new': return role in {'office','office_manager'}
    if endpoint in {'main.records_availability','main.records_availability_page','main.record_slot_toggle','main.record_slots_close_interval'} and role=='supervisor': return False
    if role=='new': return False
    return role in {'manager','supervisor','office','office_manager'} or role.startswith('custom_')


HISTORY_SCOPES = {'apartments': 'История изменений по помещению', 'remarks': 'История изменений замечания'}
HISTORY_OWN_ACTIONS = {f'{section}_history_own' for section in HISTORY_SCOPES}
for section, label in HISTORY_SCOPES.items():
    ACTIONS.extend([
        (f'{section}_history_own', section, f'{label} — только свои записи', set()),
        (f'{section}_history_all', section, f'{label} — записи всех пользователей', set()),
    ])


def effective(role):
    from app.routes import SECTION_LOCK_CHOICES
    configured=definitions().get(role)
    sections=[item['key'] for item in SECTION_LOCK_CHOICES if item['key'] not in {'users','service','site_errors'}]
    defaults=[key for key in sections if any(baseline_endpoint(role,ep) for item in SECTION_LOCK_CHOICES if item['key']==key for ep in item['endpoints'])]
    default_actions=[key for key,section,label,endpoints in ACTIONS if any(baseline_endpoint(role,ep,mutation=True) for ep in endpoints)]
    if role in {'admin','manager'}:
        default_actions.append('remark_view_comments')
    if role not in {'painter', 'handyman', 'glazier', 'new'}:
        default_actions.extend(sorted(HISTORY_OWN_ACTIONS))
    if configured:
        actions = [key for key in configured.get('actions', default_actions)
                   if key not in {'dashboard_history_own', 'dashboard_history_all'}]
        if not configured.get('history_permissions_saved'):
            actions.extend(sorted(HISTORY_OWN_ACTIONS.intersection(default_actions).difference(actions)))
        return {'sections': configured.get('sections', []), 'actions': actions}
    return {'sections':defaults,'actions':default_actions}


def allowed(user, endpoint, mutation=False):
    from app.routes import _section_lock_choice_for_endpoint
    if user.role=='admin': return True
    config=definitions().get(user.role)
    if not config: return baseline_endpoint(user.role,endpoint,mutation)
    policy=effective(user.role)
    action=next((item for item in ACTIONS if endpoint in item[3]),None)
    section=_section_lock_choice_for_endpoint(endpoint)
    if action:
        if action[1] not in policy['sections']: return False
        # Read-only details/list pages remain available without the edit action.
        read_page=endpoint in {'main.assignments','main.record_detail','main.appeal_detail','main.avr'} and not mutation
        return read_page or action[0] in policy['actions']
    if section: return section['key'] in policy['sections']
    return endpoint in {'main.account','main.account_password','main.updates_archive','main.updates_card'}

# Remaining project workflows expose separate edit/delete/export capabilities.
ACTIONS += [
 ('materials_create','materials','Создавать заявки, списания и ручные задачи',{'main.material_request_new','main.material_writeoff_new','main.material_writeoff_submit','main.material_manual_task_new'}),
 ('materials_edit','materials','Редактировать заявки и списания',{'main.material_request_rename','main.material_request_update','main.material_writeoff_edit'}),
 ('materials_delete','materials','Удалять заявки, списания и остатки',{'main.material_balance_delete','main.material_request_delete','main.material_requests_bulk_delete','main.material_writeoff_delete','main.material_writeoffs_bulk_delete'}),
 ('glass_edit','glass','Добавлять и редактировать замеры',{'main.glass_need_measure','main.glass_measurement_add','main.glass_measurement_save','main.glass_manual_task_new'}),
 ('glass_order','glass','Заказывать замеры и менять их статус',{'main.glass_measurement_return_to_all','main.glass_status_update','main.glass_create_material_request','main.glass_order'}),
 ('glass_delete','glass','Удалять замеры',{'main.glass_measurements_delete'}),
 ('remark_export','remarks','Скачивать таблицы и PDF замечаний',{'main.remarks_excel_selection','main.export_tasks','main.export_category_tasks','main.export_category_tasks_pdf','main.export_source_with_strikes'}),
 ('premise_export','apartments','Скачивать таблицы помещений',{'main.apartments_export','main.apartment_remarks_export','main.apartment_source_export'}),
 ('contractor_export','contractors','Скачивать документы подрядчиков',{'main.contractors_export','main.contractors_excel_selection'}),
 ('assignment_export','assignments','Скачивать выданные задачи',{'main.assignment_issued_employee_export'}),
 ('records_export','records','Скачивать расписание осмотров',{'main.records_download'}),
 ('report_export','report','Скачивать отчёты',{'main.work_report_export','main.assignments_report_worker_pdf'}),
 ('materials_export','materials','Скачивать заявки и расходы',{'main.material_request_export','main.material_expense_export'}),
 ('glass_export','glass','Скачивать заказы замеров',{'main.glass_order_export'}),
]
ACTIONS += [
 ('worker_status','worker_tasks','Менять статус своих задач',{'main.my_task_done','main.my_task_return','main.my_task_status','main.worker_offline_operation'}),
 ('worker_comment','worker_tasks','Оставлять и удалять свои комментарии',{'main.my_task_comment','main.my_task_comment_delete'}),
 ('worker_measure','worker_tasks','Добавлять и удалять свои замеры',{'main.my_task_measurement','main.my_task_measurement_delete'}),
]

ACTIONS += [
 ('avr_generate','avr','Формировать АВР',{'main.avr'}),
 ('notifications_archive','notifications','Архивировать уведомления АВР',{'main.archive_apartment_avr'}),
]

ACTIONS.append(('remark_view_comments','remarks','Просматривать комментарии к замечаниям',set()))
