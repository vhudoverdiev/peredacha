import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from app import db
from app.services.task_service import set_setting
from app.ai_assistant import knowledge
from tests import test_worker_task_updates as fixture

class AiAssistantTests(unittest.TestCase):
    setUp=fixture.WorkerTaskUpdatesTests.setUp
    tearDown=fixture.WorkerTaskUpdatesTests.tearDown
    login=fixture.WorkerTaskUpdatesTests.login
    def ask(self,question,**extra):
        from app.security import _BUCKETS
        for key in list(_BUCKETS):
            if key.startswith('ai_assistant_interval:'):_BUCKETS.pop(key)
        return self.client.post('/ai-assistant/ask',json={'question':question,**extra},headers={'Accept':'application/json'})
    def test_knowledge_counts_and_every_example(self):
        engine=knowledge()
        self.assertEqual(len(engine.entries),500)
        phrases=[p for i in json.loads(Path('app/data/ai_assistant/intents.json').read_text()) for p in i['examples']]
        self.assertEqual(len(phrases),5000)
        self.assertEqual(len({engine.normalize(p) for p in phrases}),5000)
        for e in engine.entries:self.assertTrue(e['access'] is not None)
        for phrase in phrases:self.assertTrue(engine.answer(phrase)['found'])
    def test_authentication_required_without_selected_project(self):
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.get('/ai-assistant',headers={'Accept':'application/json'}).status_code,401)
        self.assertEqual(self.ask('Как добавить замечание?').status_code,401)
        self.login(self.manager)
        with self.client.session_transaction() as session:session.pop('current_project_id',None)
        self.assertEqual(self.client.get('/ai-assistant').status_code,200)
    def test_admin_has_twelve_frequent_questions(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        self.assertEqual(len(self.client.get('/ai-assistant').json['faqs']),12)

    def test_worker_does_not_receive_admin_answers_or_faq(self):
        self.login(self.worker)
        r=self.ask('Как создать свою роль?',profile='admin')
        self.assertEqual(r.status_code,200);self.assertFalse(r.json['found'])
        self.assertNotIn('В «Настройках доступа» создайте',str(r.json))
        self.assertNotIn('Как создать свою роль?',str(self.client.get('/ai-assistant').json))
    def test_custom_permissions_apply_immediately(self):
        self.manager.role='custom_ai';db.session.commit();self.login(self.manager)
        set_setting('role_section_permissions',json.dumps({'custom_ai':{'name':'AI test','sections':['remarks'],'actions':[]}}));db.session.commit()
        self.assertFalse(self.ask('Как добавить замечание?').json['found'])
        set_setting('role_section_permissions',json.dumps({'custom_ai':{'name':'AI test','sections':['remarks'],'actions':['remark_create']}}));db.session.commit()
        r=self.ask('Как добавить замечание?');self.assertTrue(r.json['found'])
        self.assertEqual(r.json['title'],'Как добавить замечание?')
    def test_csrf_and_payload_validation(self):
        self.login(self.manager)
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.ask('Как добавить замечание?').status_code,400)
        html=self.client.get('/objects').text
        token=re.search(r'name="csrf_token" value="([^"]+)"',html)[1]
        r=self.client.post('/ai-assistant/ask',json={'question':'Как добавить замечание?'},headers={'X-CSRFToken':token,'Accept':'application/json'})
        self.assertEqual(r.status_code,200)
        self.app.config['WTF_CSRF_ENABLED']=False
        for payload in [[],{}, {'question':False},{'question':'x'*1001}]:
            self.assertEqual(self.client.post('/ai-assistant/ask',json=payload).status_code,400)
    def test_rate_limit_and_private_cache(self):
        self.login(self.manager)
        def limited(scope,*args,**kwargs):return scope=='ai_assistant'
        with patch('app.security.hit_rate_limit',side_effect=limited):self.assertEqual(self.ask('Вопрос').status_code,429)
        r=self.client.get('/ai-assistant');self.assertIn('no-store',r.headers['Cache-Control'])
    def test_widgets_desktop_mobile_po_and_support(self):
        self.login(self.manager)
        set_setting('objects_support_enabled','1');set_setting('objects_support_phone','+7 (921) 080-82-00');set_setting('objects_support_text','Владимир');db.session.commit()
        for headers in [{},{'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}]:
            html=self.client.get('/objects',headers=headers).text
            self.assertNotIn('objects-support-card',html)
            if headers:
                self.assertNotIn('data-ai-open',html)
                self.assertNotIn('id="crm-ai-dialog"',html)
            else:
                self.assertIn('data-ai-open',html)
                self.assertIn('crm-ai-support',html)
                self.assertLess(html.index('Помогу разобраться с CRM'),html.index('+7 (921) 080-82-00'))
        html=self.client.get('/apartments').text
        corner=html.split('crm-floating-tools',1)[1].split('</div>',1)[0]
        self.assertIn('po-notification-widget',corner);self.assertIn('data-ai-open',corner)
        self.assertNotIn('preview-profile',html)
        self.assertNotIn('/api/profile',html)

    def test_report_launcher_requires_login_and_mobile(self):
        with self.client.session_transaction() as session:session.clear()
        html=self.client.get('/login').text
        self.assertNotIn('report-error-floating"',html)
        self.login(self.manager)
        html=self.client.get('/objects').text
        self.assertNotIn('report-error-floating"',html)
        self.assertIn('data-ai-report',html)
        mobile={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'}
        self.assertIn('report-error-floating"',self.client.get('/objects',headers=mobile).text)

    def test_report_from_chat_saved_with_identity_and_quota(self):
        from app.models import SiteErrorReport
        from app.security import _BUCKETS
        _BUCKETS.clear()
        self.login(self.manager)
        headers={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}
        response=self.client.post('/report-error',data={'message':'Не открывается карточка','page_url':'/objects'},headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertIn('отправлено',response.json['message'])
        row=SiteErrorReport.query.filter_by(user_id=self.manager.id).one()
        self.assertEqual(row.message,'Не открывается карточка')
        self.assertEqual(row.page_url,'/objects')
        for _ in range(2):
            self.assertEqual(self.client.post('/report-error',data={'message':'Ошибка'},headers=headers).status_code,200)
        self.assertEqual(self.client.post('/report-error',data={'message':'Ошибка'},headers=headers).status_code,429)
        self.assertEqual(SiteErrorReport.query.filter_by(user_id=self.manager.id).count(),3)
        self.assertEqual(self.client.post('/report-error',data={'message':' '},headers=headers).status_code,400)

    def test_support_uses_configured_text(self):
        self.login(self.manager)
        set_setting('objects_support_enabled','1')
        set_setting('objects_support_phone','+7 (999) 000-00-00')
        set_setting('objects_support_text','Обратитесь к администратору CRM')
        db.session.commit()
        html=self.client.get('/objects').text
        self.assertIn('<span>Обратитесь к администратору CRM</span>',html)
        self.assertNotIn('id="crm-ai-clear"',html)

    def test_chat_report_csrf_and_rate_limit(self):
        self.login(self.manager)
        headers={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'}
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/report-error',data={'message':'Ошибка'},headers=headers).status_code,400)
        self.app.config['WTF_CSRF_ENABLED']=False
        with patch('app.routes.hit_rate_limit',return_value=True):
            response=self.client.post('/report-error',data={'message':'Ошибка'},headers=headers)
        self.assertEqual(response.status_code,429)
        self.assertIn('Повторите',response.json['error'])

    def test_status_meanings_are_not_edit_instructions(self):
        engine=knowledge()
        for question,term in [('Что значит статус гарантия','Гарантия'),('Что означает сверить ПО','Сверить(ПО)'),('Что такое внутренний статус','Внутренний статус'),('Что означает не приглашать','Не приглашать'),('Что такое АПП','АПП')]:
            result=engine.answer(question)
            self.assertTrue(result['found'],question)
            self.assertIn(term,result['title'])
            self.assertNotIn('Откройте карточку',str(result['steps']))

    def test_developer_close_is_idempotent_and_delete_is_logged(self):
        from app.models import SiteErrorReport,DeletionActionLog
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        report=SiteErrorReport(message='Тест закрытия',kind='user',status='new',user_id=self.manager.id,project_id=self.project.id)
        db.session.add(report);db.session.commit();report_id=report.id
        for _ in range(2):
            response=self.client.post(f'/site-errors/{report_id}/close',data={'status':'closed'},headers={'Accept':'application/json'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['status'],'closed')
        self.assertEqual(self.client.post(f'/site-errors/{report_id}/close',data={'status':'bad'}).status_code,400)
        db.session.rollback()
        self.assertEqual(self.client.post(f'/site-errors/{report_id}/delete').status_code,302)
        self.assertIsNone(db.session.get(SiteErrorReport,report_id))
        self.assertIsNotNone(DeletionActionLog.query.filter_by(action_key='site_error_delete',entity_id=report_id).first())

    def test_act_help_explains_both_po_modes_without_step_fragments(self):
        engine=knowledge()
        for question in ['Как перенести замечания из акта вручную?', 'Как перенести замечания из акта вручную: в каком порядке выполнить шаги 3 и 4?', 'Как распознать PDF акт?']:
            result=engine.answer(question)
            self.assertTrue(result['found'])
            self.assertNotIn('шаги 3 и 4',result['title'])
            self.assertIn('автоматического распознавания',str(result['steps']))
            self.assertIn('идентичные замечания остаются невыполненными',str(result['steps']))
        result=engine.answer('Что значит ПО в распознавании')
        self.assertIn('другое действие',str(result['steps']))
        for question in ['Как перенести акт','Как добавить акт осмотра','Распознавание акта']:
            result=engine.answer(question)
            self.assertNotIn('шаге',str(result['related']))
            self.assertNotIn('выполнить шаги',str(result['related']))

    def test_daily_question_limit_is_per_account_and_moscow_day(self):
        from app.ai_assistant import consume_daily_question
        from app.models import AppSetting
        from datetime import datetime
        manager_id,worker_id=self.manager.id,self.worker.id
        with patch('app.time_utils.utc_now',return_value=datetime(2026,11,17,20,59)):
            for _ in range(40):self.assertTrue(consume_daily_question(manager_id))
            self.assertFalse(consume_daily_question(manager_id))
            self.assertTrue(consume_daily_question(worker_id))
            db.session.remove()
            self.assertFalse(consume_daily_question(manager_id))
        with patch('app.time_utils.utc_now',return_value=datetime(2026,11,17,21,0)):
            self.assertTrue(consume_daily_question(manager_id))
        self.assertEqual(json.loads(AppSetting.query.filter_by(key=f'ai_daily_questions:{manager_id}').one().value)['count'],1)

    def test_question_interval_is_enforced(self):
        from app.security import _BUCKETS
        _BUCKETS.clear();self.login(self.manager)
        headers={'Accept':'application/json'}
        self.assertEqual(self.client.post('/ai-assistant/ask',json={'question':'Что такое АПП'},headers=headers).status_code,200)
        response=self.client.post('/ai-assistant/ask',json={'question':'Что такое АПП'},headers=headers)
        self.assertEqual(response.status_code,429)
        self.assertIn('2 секунды',response.json['error'])
