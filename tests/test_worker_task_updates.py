from datetime import date, datetime
import unittest
import tempfile
from unittest.mock import patch
from flask import g

from app import create_app, db, login_manager
from app.models import User, Project, Apartment, WorkPoint, Task, TaskComment, STATUS_IN_PROGRESS
from config import Config


class WorkerConfig(Config):
    TESTING = True
    SECRET_KEY = 'worker-task-test'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class WorkerTaskUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.temp_files = tempfile.TemporaryDirectory()
        self.app = create_app(WorkerConfig)
        self.app.config.update(EXPORT_FOLDER=self.temp_files.name, UPLOAD_FOLDER=self.temp_files.name)
        self.context = self.app.app_context(); self.context.push()
        self.previous = login_manager.session_protection; login_manager.session_protection = None
        db.create_all()
        self.project = Project(name='Worker project')
        self.worker = User(username='worker', full_name='Петров Пётр Петрович', role='painter', project=self.project)
        self.other = User(username='other', role='handyman', project=self.project)
        self.manager = User(username='manager', role='manager', project=self.project)
        for user in (self.worker, self.other, self.manager):
            user.set_password('worker-test-password')
        self.apartment = Apartment(project=self.project, apartment_number='173')
        self.point = WorkPoint(point_number='1', short_name='Отделка', source_sheet_name='manual')
        self.task = Task(source_uid='worker-task', project=self.project, apartment=self.apartment,
                         work_point=self.point, responsible=self.worker, description='Покрасить стену',
                         planned_date=date(2026, 10, 21))
        db.session.add_all([self.worker, self.other, self.manager, self.task]); db.session.commit()
        self.client = self.app.test_client()
        self.login(self.worker)

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.context.pop()
        login_manager.session_protection = self.previous
        self.temp_files.cleanup()

    def login(self, user):
        g.pop('_login_user', None)
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user.id); sess['_fresh'] = True
            sess['session_version'] = int(user.session_version or 0)
            sess['current_project_id'] = self.project.id

    def post(self, suffix, data):
        return self.client.post(f'/my-tasks/{self.task.id}/{suffix}', data=data,
                                headers={'Accept':'application/json','X-Requested-With':'XMLHttpRequest'})

    def test_all_worker_roles_can_set_progress_and_comment_with_real_author(self):
        for role in ('painter', 'handyman', 'glazier'):
            self.worker.role = role; db.session.commit()
            with self.subTest(role=role):
                response = self.post('status', {'status':'in_progress'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['status_label'], 'В работе')
                self.assertFalse(response.json['is_done'])
                response = self.post('comment', {'body':'  Нужен материал <script>alert(1)</script>  ', 'user_id':self.other.id})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['comment']['body'],'Нужен материал <script>alert(1)</script>')
                self.assertIn('message',response.json)
        self.assertEqual(TaskComment.query.count(), 3)
        self.assertTrue(all(c.user_id == self.worker.id for c in TaskComment.query.all()))
        self.login(self.manager)
        html = self.client.get(f'/tasks/{self.task.id}').get_data(as_text=True)
        self.assertIn(self.worker.full_name, html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('В работе', html)

    def test_progress_rolls_after_moscow_midnight_not_on_click(self):
        with patch('app.routes.utc_now', return_value=datetime(2026,10,21,20,59,59)):
            self.assertEqual(self.post('status', {'status':'in_progress'}).status_code, 200)
            self.assertIn('Покрасить стену', self.client.get('/my-tasks').get_data(as_text=True))
            db.session.refresh(self.task)
            self.assertEqual(self.task.planned_date, date(2026,10,21))
        with patch('app.routes.utc_now', return_value=datetime(2026,10,21,21,0,0)):
            html = self.client.get('/my-tasks').get_data(as_text=True)
            self.assertIn('Покрасить стену', html)
            db.session.refresh(self.task)
            self.assertEqual(self.task.planned_date, date(2026,10,22))
        with patch('app.routes.utc_now', return_value=datetime(2026,10,24,5)):
            self.client.get('/my-tasks'); db.session.refresh(self.task)
            self.assertEqual(self.task.planned_date, date(2026,10,24))

    def test_done_and_future_tasks_do_not_roll(self):
        with patch('app.routes.utc_now', return_value=datetime(2026,10,22,10)):
            self.post('status', {'status':'done'})
            self.client.get('/my-tasks'); db.session.refresh(self.task)
            self.assertEqual(self.task.planned_date, date(2026,10,21))
            self.task.status = STATUS_IN_PROGRESS; self.task.is_done = False
            self.task.planned_date = date(2026,10,30); db.session.commit()
            self.client.get('/my-tasks'); db.session.refresh(self.task)
            self.assertEqual(self.task.planned_date, date(2026,10,30))

    def test_other_worker_and_manager_cannot_impersonate_assignee(self):
        for user in (self.other, self.manager):
            self.login(user)
            self.assertEqual(self.post('status', {'status':'in_progress'}).status_code, 403)
            self.assertEqual(self.post('comment', {'body':'Чужой комментарий'}).status_code, 403)
        self.assertEqual(TaskComment.query.count(), 0)

    def test_invalid_status_empty_long_comment_and_archived_task_are_rejected(self):
        self.assertEqual(self.post('status', {'status':'arbitrary'}).status_code, 400)
        for text in ('   ', 'x'*4001):
            self.assertEqual(self.post('comment', {'body':text}).status_code, 400)
        self.task.is_archived = True; db.session.commit()
        self.assertEqual(self.post('comment', {'body':'Комментарий'}).status_code, 404)
        self.assertEqual(TaskComment.query.count(), 0)

    def test_csrf_is_still_required_when_enabled(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.post('status', {'status':'in_progress'}).status_code, 400)
        self.assertEqual(self.post('comment', {'body':'Комментарий'}).status_code, 400)

    def test_worker_shell_never_claims_or_renders_sidebar(self):
        for role in ('painter', 'handyman', 'glazier'):
            self.worker.role = role; db.session.commit()
            html = self.client.get('/my-tasks').get_data(as_text=True)
            root = html.split('<html',1)[1].split('>',1)[0]
            self.assertNotIn('desktop-shell-with-sidebar', root)
            self.assertNotIn('id="appSidebar"', html)

    def test_assignee_cannot_comment_on_task_outside_accessible_project(self):
        other_project = Project(name='Other project')
        self.task.project = other_project; db.session.add(other_project); db.session.commit()
        self.assertEqual(self.post('comment', {'body':'Чужой объект'}).status_code, 404)
        self.assertEqual(self.post('status', {'status':'in_progress'}).status_code, 404)
        self.assertEqual(TaskComment.query.count(), 0)

    def test_tasks_are_grouped_across_accessible_projects_with_independent_actions(self):
        second = Project(name='Второй объект')
        hidden = Project(name='Закрытый объект')
        db.session.add_all([second, hidden]); db.session.flush()
        planned_date = self.task.planned_date
        extra = Task(source_uid='second-worker-task', project=second, apartment=Apartment(project=second, apartment_number='1'), responsible=self.worker,
                     work_point=self.point, description='Работа на втором объекте', planned_date=planned_date)
        forbidden = Task(source_uid='hidden-worker-task', project=hidden, apartment=Apartment(project=hidden, apartment_number='1'), responsible=self.worker,
                         work_point=self.point, description='Скрытая работа', planned_date=planned_date)
        db.session.add_all([extra, forbidden])
        self.worker.set_project_access([self.project.id, second.id]); db.session.commit()
        with patch('app.routes.utc_now', return_value=datetime(2026,10,21,10)):
            for role in ('painter', 'handyman', 'glazier'):
                self.worker.role = role; db.session.commit()
                page = self.client.get('/my-tasks').get_data(as_text=True)
                self.assertEqual(page.count('data-worker-project-group'),2)
                self.assertIn('Второй объект</span></h2>',page)
                self.assertIn('Работа на втором объекте',page)
                self.assertNotIn('Скрытая работа',page)
                self.assertNotIn('Объект: не назначен',page)
                self.assertEqual(page.count('data-worker-done-toggle'),2)
            response = self.client.post(f'/my-tasks/{extra.id}/status',data={'status':'done'},headers={'Accept':'application/json'})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json['is_done'])
            response = self.client.post(f'/my-tasks/{extra.id}/comment',data={'body':'Второй объект'},headers={'Accept':'application/json'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(self.client.post(f'/my-tasks/{forbidden.id}/status',data={'status':'done'}).status_code,404)
            extra.status = STATUS_IN_PROGRESS; extra.is_done = False; db.session.commit()
        with patch('app.routes.utc_now', return_value=datetime(2026,10,21,21)):
            self.client.get('/my-tasks'); db.session.refresh(extra)
            self.assertEqual(extra.planned_date,date(2026,10,22))

    def test_comment_privacy_in_worker_crm_apartment_and_history(self):
        secret = 'Только инженер видит этот комментарий 789'
        self.assertEqual(self.post('comment', {'body':secret}).status_code,200)
        db.session.add(TaskComment(task=self.task, user=self.manager, body='Чужой комментарий скрыт 654')); db.session.commit()
        with patch('app.routes.utc_now', return_value=datetime(2026,10,21,10)):
            page=self.client.get('/my-tasks').get_data(as_text=True)
            self.assertIn(secret,page)
            self.assertNotIn('Чужой комментарий скрыт 654',page)
            self.assertNotIn('data-worker-comments',page)
            self.assertIn('data-worker-comment-toggle',page)
        for role in ('manager','admin','supervisor','office','viewer'):
            self.manager.role=role; db.session.commit(); self.login(self.manager)
            # Own history must not reveal text for a role without comment access.
            self.task.changes[-1].user_id=self.manager.id; db.session.commit()
            for path in (f'/tasks/{self.task.id}',f'/apartments/{self.apartment.id}'):
                with self.subTest(role=role,path=path):
                    response=self.client.get(path)
                    self.assertEqual(response.status_code,200)
                    if role in ('manager','admin'):
                        self.assertIn(secret,response.get_data(as_text=True))
                    else:
                        self.assertNotIn(secret,response.get_data(as_text=True))
            if role not in ('manager','admin'):
                response=self.client.post(f'/tasks/{self.task.id}/comment',data={'body':'forbidden'},headers={'Accept':'application/json'})
                self.assertEqual(response.status_code,403)

    def test_worker_can_delete_only_own_comment_on_assigned_accessible_task(self):
        for role in ('painter','handyman','glazier'):
            self.worker.role=role; db.session.commit()
            response=self.post('comment',{'body':'Комментарий для удаления'})
            delete_url=response.json['comment']['delete_url']
            self.assertEqual(self.client.post(delete_url,headers={'Accept':'application/json'}).status_code,200)
            self.assertEqual(self.client.post(delete_url,headers={'Accept':'application/json'}).status_code,404)
        comment=TaskComment(task=self.task,user=self.manager,body='Чужой комментарий')
        db.session.add(comment);db.session.commit()
        url=f'/my-tasks/{self.task.id}/comments/{comment.id}/delete'
        self.assertEqual(self.client.post(url).status_code,404)
        own_url=self.post('comment',{'body':'Свой комментарий'}).json['comment']['delete_url']
        self.login(self.other)
        self.assertEqual(self.client.post(own_url).status_code,403)
        self.login(self.worker)
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.client.post(own_url).status_code,400)
        self.assertEqual(TaskComment.query.count(),2)

    def test_not_started_task_rolls_only_after_moscow_midnight(self):
        with patch('app.routes.utc_now',return_value=datetime(2026,10,21,20,59,59)):
            self.client.get('/my-tasks');db.session.refresh(self.task)
            self.assertEqual(self.task.planned_date,date(2026,10,21))
        with patch('app.routes.utc_now',return_value=datetime(2026,10,21,21)):
            self.client.get('/my-tasks');db.session.refresh(self.task)
            self.assertEqual(self.task.planned_date,date(2026,10,22))
            self.assertFalse(self.task.is_done)
            self.assertEqual(self.task.status,'not_started')

    def test_assignment_word_search_matches_visible_remark_not_other_columns(self):
        from app.routes import _assignment_base_query
        self.task.responsible=None
        self.task.description='Требуется проверка электричества в квартире.'
        self.task.title='Другое название'
        self.point.short_name='проверка'
        self.point.point_number='10'
        extra=Task(source_uid='unrelated-word-match',project=self.project,apartment=self.apartment,
                   work_point=self.point,title='проверка',description='Покрасить стену',source_cell_value='старая проверка')
        fallback=Task(source_uid='source-word-match',project=self.project,apartment=self.apartment,
                      work_point=self.point,description='',source_cell_value='ПРОВЕРКА окон')
        db.session.add_all([extra,fallback]);db.session.commit()
        for term in ('проверка','Проверка','ПРОВЕРКА'):
            self.assertEqual({t.id for t in _assignment_base_query(self.project.id,{'q':term}).all()},
                             {self.task.id,fallback.id})
        self.assertEqual({t.id for t in _assignment_base_query(self.project.id,{'q':'173'}).all()},
                         {self.task.id,extra.id,fallback.id})

    def test_manual_task_without_premise_survives_assignment_worker_and_reports(self):
        self.login(self.manager)
        before=Apartment.query.count()
        response=self.client.post('/assignments/manual/new',data={
            'without_premise':'1','apartment_id':'999999','responsible_id':self.worker.id,
            'planned_date':'2026-10-21','description':'Общая задача объекта без квартиры'})
        self.assertEqual(response.status_code,302)
        task=Task.query.filter_by(source_sheet_name='assignment_manual').one()
        self.assertIsNone(task.apartment_id)
        self.assertEqual(Apartment.query.count(),before)
        with patch('app.routes.utc_now',return_value=datetime(2026,10,21,10)):
            self.assertIn('Общая задача объекта без квартиры',self.client.get('/assignments?view=issued').get_data(as_text=True))
            self.assertIn('Общая задача объекта без квартиры',self.client.get('/assignments/report?date=2026-10-21').get_data(as_text=True))
            self.assertEqual(self.client.get(f'/tasks/{task.id}').status_code,200)
            for path in (f'/assignments/issued/{self.worker.id}/export',f'/assignments/report/{self.worker.id}/pdf?date=2026-10-21'):
                with self.client.get(path) as export:
                    self.assertEqual(export.status_code,200)
            self.login(self.worker)
            page=self.client.get('/my-tasks').get_data(as_text=True)
            self.assertIn('Общая задача объекта без квартиры',page)
            self.assertIn('Без помещения',page)
            self.assertEqual(self.client.post(f'/my-tasks/{task.id}/status',data={'status':'done'},headers={'Accept':'application/json'}).status_code,200)
        self.login(self.manager)
        task.responsible_id=None;task.status='not_started';task.is_done=False;db.session.commit()
        self.assertIn('Общая задача объекта без квартиры',self.client.get('/assignments').get_data(as_text=True))
        self.assertEqual(self.client.post('/assignments',data={'task_ids':str(task.id),'responsible_id':self.worker.id,
                         'planned_date':'2026-10-21'}).status_code,302)
        db.session.refresh(task)
        self.assertEqual(task.responsible_id,self.worker.id)

    def test_manual_premise_selection_and_worker_project_access_are_validated(self):
        self.login(self.manager)
        base_count=Task.query.count()
        for data in ({'description':'Нет помещения'}, {'apartment_id':'999999','description':'Чужое помещение'},
                     {'without_premise':'1','description':'','responsible_id':self.worker.id}):
            self.assertEqual(self.client.post('/assignments/manual/new',data=data).status_code,200)
        self.assertEqual(Task.query.count(),base_count)
        self.login(self.worker)
        self.assertEqual(self.client.post('/assignments/manual/new',data={'without_premise':'1','description':'forbidden'}).status_code,403)

    def test_comment_rate_limit_keeps_database_unchanged(self):
        with patch('app.routes.hit_rate_limit', return_value=True):
            self.assertEqual(self.post('comment', {'body':'Комментарий'}).status_code, 429)
        self.assertEqual(TaskComment.query.count(), 0)

    def test_crm_view_rolls_progress_tasks_even_before_employee_opens_cabinet(self):
        self.task.status = STATUS_IN_PROGRESS; db.session.commit()
        self.login(self.manager)
        with patch('app.routes.utc_now', return_value=datetime(2026,10,21,21,0,0)):
            response = self.client.get('/assignments?view=issued')
        self.assertEqual(response.status_code, 200)
        db.session.refresh(self.task)
        self.assertEqual(self.task.planned_date, date(2026,10,22))
        self.assertIn('В работе', response.get_data(as_text=True))
