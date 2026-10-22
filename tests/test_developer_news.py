"""Developer news, private delivery, deadlines, access and publication lifecycle."""
from datetime import datetime,timedelta
from unittest.mock import patch
import unittest
from app import db
from app.models import DeveloperUpdate,DeveloperPersonalMessage,Project,User
from app.services.developer_news import card_for_user
import test_worker_task_updates as fixture


class DeveloperNewsTests(unittest.TestCase):
    setUp=fixture.WorkerTaskUpdatesTests.setUp
    tearDown=fixture.WorkerTaskUpdatesTests.tearDown
    login=fixture.WorkerTaskUpdatesTests.login

    def admin(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)

    def update(self,title='Обновили CRM',published=True):
        update=DeveloperUpdate(title=title,body='Исправлены замечания и улучшена запись на осмотр.',published_at=datetime(2026,10,23,8) if published else None)
        db.session.add(update);db.session.commit();return update

    def message(self,user=None,minutes=60,title='Спасибо за сообщение об ошибке'):
        message=DeveloperPersonalMessage(recipient_id=(user or self.manager).id,title=title,body='Мы исправили ошибку. Спасибо!',duration_minutes=minutes)
        db.session.add(message);db.session.commit();return message

    def test_editor_forms_are_separate_subpages(self):
        self.admin()
        archive=self.client.get('/updates')
        self.assertIn('dev-news-empty',archive.text)
        self.assertIn('dev-news-empty-icon',archive.text)
        self.assertNotIn('Опубликованные разработчиком изменения',archive.text)
        home=self.client.get('/')
        self.assertNotIn('dev-news-manage',home.text)
        self.assertIn('dev-news-brand',home.text)
        self.assertNotIn('Здесь появятся сообщения о новых',home.text)
        listing=self.client.get('/developer/updates')
        self.assertNotIn('name="title"',listing.text)
        self.assertIn('Добавить',listing.text)
        self.assertNotIn('>Отправить</a>',listing.text)
        personal=self.client.get('/developer/updates?mode=messages')
        self.assertIn('>Отправить</a>',personal.text)
        self.assertNotIn('>Добавить</a>',personal.text)
        for url in ('/developer/updates?compose=1','/developer/updates?mode=messages&compose=1'):
            page=self.client.get(url)
            self.assertEqual(page.status_code,200)
            self.assertIn('name="title"',page.text)
            self.assertNotIn('Публикация появится на главной',page.text)
            self.assertNotIn('Сообщение временно заменит',page.text)
            self.assertNotIn('Пока пользователь не увидел',page.text)

    def test_dashboard_and_archive_share_global_update_between_projects(self):
        self.login(self.manager);update=self.update()
        first=self.client.get('/');self.assertEqual(first.status_code,200)
        self.assertIn('Худовердиев В',first.text);self.assertIn(update.title,first.text);self.assertIn('Посмотреть все',first.text)
        other=Project(name='Другой доступный объект');db.session.add(other);self.manager.all_projects_access=True;db.session.commit()
        with self.client.session_transaction() as session:session['current_project_id']=other.id
        self.assertIn(update.title,self.client.get('/').text)
        self.assertIn(update.title,self.client.get('/updates').text)
        self.assertIn('no-store',first.headers['Cache-Control'])

    def test_publication_day_is_shown_in_moscow_timezone(self):
        self.login(self.manager);update=self.update()
        update.published_at=datetime(2026,10,22,22);db.session.commit()
        self.assertIn('23.10.2026',self.client.get('/').text)

    def test_drafts_and_withdrawn_updates_are_not_public(self):
        self.login(self.manager);self.update('SECRET_DRAFT',False)
        update=self.update('SECRET_WITHDRAWN');update.withdrawn_at=datetime(2026,10,23,9);db.session.commit()
        for path in ('/','/updates','/updates/card'):
            response=self.client.get(path)
            self.assertNotIn('SECRET_DRAFT',response.text);self.assertNotIn('SECRET_WITHDRAWN',response.text)

    def test_personal_timer_starts_at_first_home_display_and_does_not_restart(self):
        self.login(self.manager);message=self.message();start=datetime(2026,10,23,10)
        self.client.get('/updates');db.session.refresh(message);self.assertIsNone(message.first_seen_at)
        with patch('app.services.developer_news.utc_now',return_value=start):
            page=self.client.get('/');self.assertIn(message.title,page.text)
        db.session.refresh(message)
        self.assertEqual(message.first_seen_at,start);self.assertEqual(message.expires_at,start+timedelta(hours=1))
        with patch('app.services.developer_news.utc_now',return_value=start+timedelta(minutes=59)):
            self.assertEqual(card_for_user(self.manager)['item'].id,message.id)
        self.assertEqual(message.first_seen_at,start)
        self.assertEqual(message.expires_at,start+timedelta(hours=1))

    def test_personal_badge_uses_recipient_name_or_login(self):
        self.login(self.manager);self.message()
        for full_name,expected in [('Владимир Иванов','Владимир'),('   ',self.manager.username)]:
            self.manager.full_name=full_name;db.session.commit()
            response=self.client.get('/updates/card')
            self.assertEqual(response.status_code,200)
            from html import escape
            self.assertIn(f'</i>{escape(expected)}</span>',response.json['html'])

    def test_expiry_returns_global_card_at_exact_deadline(self):
        self.login(self.manager);update=self.update();self.message();start=datetime(2026,10,23,10)
        with patch('app.services.developer_news.utc_now',return_value=start):card_for_user(self.manager)
        with patch('app.services.developer_news.utc_now',return_value=start+timedelta(hours=1)):
            card=card_for_user(self.manager);self.assertEqual(card['kind'],'update');self.assertEqual(card['item'].id,update.id)
            self.assertNotIn('Лично вам',self.client.get('/updates/card').json['html'])

    def test_queued_messages_get_their_own_full_duration(self):
        self.login(self.manager);first=self.message(minutes=1,title='Первое');second=self.message(minutes=60,title='Второе')
        start=datetime(2026,10,23,10)
        with patch('app.services.developer_news.utc_now',return_value=start):self.assertEqual(card_for_user(self.manager)['item'].id,first.id)
        db.session.refresh(second);self.assertIsNone(second.first_seen_at)
        later=start+timedelta(minutes=15)
        with patch('app.services.developer_news.utc_now',return_value=later):self.assertEqual(card_for_user(self.manager)['item'].id,second.id)
        self.assertEqual(second.expires_at,later+timedelta(hours=1))

    def test_personal_content_is_private_and_never_appears_in_archive(self):
        self.message(title='PRIVATE_RECIPIENT_TOKEN');self.login(self.other)
        self.other.role='manager';db.session.commit()
        for url in ('/','/updates','/updates/card'):
            self.assertNotIn('PRIVATE_RECIPIENT_TOKEN',self.client.get(url).text)
        self.login(self.manager)
        self.assertNotIn('PRIVATE_RECIPIENT_TOKEN',self.client.get('/updates').text)
        self.assertIn('PRIVATE_RECIPIENT_TOKEN',self.client.get('/updates/card').json['html'])

    def test_workers_never_receive_cards_or_start_message_timers(self):
        for role in ('executor','painter','handyman','glazier'):
            self.worker.role=role;db.session.commit();message=self.message(self.worker);self.login(self.worker)
            self.assertIsNone(card_for_user(self.worker))
            for url in ('/updates','/updates/card','/developer/updates'):
                response=self.client.get(url);self.assertIn(response.status_code,(302,403))
                self.assertNotIn(message.title,response.text)
            db.session.refresh(message);self.assertIsNone(message.first_seen_at)

    def test_editor_requires_developer_and_csrf(self):
        self.login(self.manager)
        self.assertEqual(self.client.get('/developer/updates').status_code,403)
        self.assertEqual(self.client.post('/developer/updates',data={'title':'x','body':'y','action':'publish'}).status_code,403)
        self.admin();self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/developer/updates',data={'title':'x','body':'y','action':'publish'}).status_code,400)
        self.assertEqual(DeveloperUpdate.query.count(),0)

    def test_delete_requires_admin_and_csrf_and_removes_records(self):
        update=self.update();message=self.message()
        paths=(f'/developer/updates/{update.id}/delete',f'/developer/updates/messages/{message.id}/delete')
        self.login(self.manager)
        for url in paths:self.assertEqual(self.client.post(url).status_code,403)
        self.admin();self.app.config['WTF_CSRF_ENABLED']=True
        for url in paths:self.assertEqual(self.client.post(url).status_code,400)
        self.assertEqual(DeveloperUpdate.query.count(),1)
        self.assertEqual(DeveloperPersonalMessage.query.count(),1)
        self.app.config['WTF_CSRF_ENABLED']=False
        for url in paths:
            self.assertEqual(self.client.get(url).status_code,405)
            self.assertEqual(self.client.post(url).status_code,303)
            self.assertEqual(self.client.post(url).status_code,404)
        self.assertEqual(DeveloperUpdate.query.count(),0)
        self.assertEqual(DeveloperPersonalMessage.query.count(),0)
        self.assertNotIn(message.title,self.client.get('/updates/card').json['html'])

    def test_editor_lifecycle_plain_text_and_public_pagination(self):
        self.admin()
        response=self.client.post('/developer/updates',data={'title':'Новая функция','body':'<script>alert(1)</script>','action':'draft'})
        self.assertEqual(response.status_code,303);update=DeveloperUpdate.query.one()
        self.assertIsNone(update.published_at)
        response=self.client.post(f'/developer/updates/{update.id}/edit',data={'title':'Опубликовано','body':'<script>alert(1)</script>','action':'publish'})
        self.assertEqual(response.status_code,303)
        archive=self.client.get('/updates').text
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',archive);self.assertNotIn('<script>alert(1)</script>',archive)
        self.assertEqual(self.client.post(f'/developer/updates/{update.id}/withdraw').status_code,303)
        self.assertNotIn('Опубликовано',self.client.get('/updates').text)
        for i in range(21):self.update(f'Обновление {i}')
        self.assertIn('Далее',self.client.get('/updates').text)
        self.assertIn('Страница 2',self.client.get('/updates?page=2').text)

    def test_send_validation_revoke_and_head_do_not_consume_timer(self):
        self.admin();base={'title':'Спасибо','body':'Исправлено','recipient_id':str(self.manager.id),'duration_value':'1','duration_unit':'60','mode':'messages'}
        for invalid in ({'duration_value':'0'},{'duration_value':'169'},{'duration_unit':'99'},{'recipient_id':str(self.worker.id)},{'body':''},{'recipient_id':'999999'}):
            response=self.client.post('/developer/updates/messages',data=base|invalid)
            self.assertEqual(response.status_code,400,invalid)
        self.assertEqual(DeveloperPersonalMessage.query.count(),0)
        self.assertEqual(self.client.post('/developer/updates/messages',data=base).status_code,303)
        message=DeveloperPersonalMessage.query.one()
        self.client.head('/');self.client.head('/updates/card');db.session.refresh(message);self.assertIsNone(message.first_seen_at)
        self.assertEqual(self.client.post(f'/developer/updates/messages/{message.id}/revoke').status_code,303)
        self.assertEqual(card_for_user(self.manager)['kind'],'update')

    def test_viewer_and_mobile_access_public_history_but_not_editor(self):
        self.manager.role='viewer';db.session.commit();self.login(self.manager);self.update()
        mobile={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1'}
        self.assertEqual(self.client.get('/updates',headers=mobile).status_code,200)
        self.assertEqual(self.client.get('/updates/card',headers=mobile).status_code,200)
        self.assertIn(self.client.get('/developer/updates',headers=mobile).status_code,(302,403))
        self.admin();self.assertEqual(self.client.get('/developer/updates',headers=mobile).status_code,200)
