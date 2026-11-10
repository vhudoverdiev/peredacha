from datetime import date, timedelta
import unittest
from app.models import Project
from app.forms import ProjectForm
from tests import test_worker_task_updates as fixture


class ProjectHandoverTests(unittest.TestCase):
    setUp=fixture.WorkerTaskUpdatesTests.setUp
    tearDown=fixture.WorkerTaskUpdatesTests.tearDown
    login=fixture.WorkerTaskUpdatesTests.login

    def test_days_and_russian_labels(self):
        today=date(2026,10,29)
        for days,text in [(0,'Осталось 0 дней'),(1,'Остался 1 день'),(2,'Осталось 2 дня'),(11,'Осталось 11 дней'),(21,'Остался 21 день'),(114,'Осталось 114 дней'),(-1,'Передан')]:
            self.project.handover_date=today+timedelta(days=days)
            self.assertEqual(self.project.handover_countdown(today)['label'],text)
        self.project.handover_date=None
        self.assertIsNone(self.project.handover_countdown(today))

    def test_mobile_cards_show_saved_values_and_empty_fields(self):
        from app import db

        self.login(self.manager)
        self.project.technical_customer = "Технический заказчик тест"
        self.project.developer_name = "Застройщик тест"
        self.project.developer_representative = "Представитель тест"
        self.project.developer_representative_phone = "+7 900 000-00-00"
        self.project.handover_waiting = True
        db.session.commit()
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"}

        response = self.client.get("/objects", headers=headers)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for value in ("Технический заказчик тест", "Застройщик тест", "Представитель тест", "+7 900 000-00-00", "Ждёт"):
            self.assertIn(value, html)

        self.project.developer_representative_phone = None
        self.project.handover_waiting = False
        self.project.handover_date = None
        db.session.commit()
        html = self.client.get("/objects", headers=headers).get_data(as_text=True)
        self.assertIn("<strong>Телефон представителя:</strong> Не указано", html)
        self.assertIn("<strong>Не указан</strong>", html)

    def test_date_can_be_saved_changed_and_cleared(self):
        self.login(self.manager)
        from app import db
        from flask import g
        for value,expected in [('2027-01-01',date(2027,1,1)),('2027-02-15',date(2027,2,15)),('',None)]:
            response=self.client.post(f'/objects/{self.project.id}/edit',data={'name':'Объект','has_apartments':'y','handover_date':value})
            self.assertEqual(response.status_code,302,response.data)
            db.session.expire_all()
            self.assertEqual(db.session.get(Project,self.project.id).handover_date,expected)

    def test_date_is_saved_on_new_object(self):
        from app import db
        self.login(self.manager)
        response=self.client.post('/objects/new',data={'name':'Объект со сроком','has_apartments':'y','handover_date':'2027-03-10'})
        self.assertEqual(response.status_code,302,response.data)
        project=Project.query.filter_by(name='Объект со сроком').one()
        self.assertEqual(project.handover_date,date(2027,3,10))

    def test_additive_schema_upgrade_preserves_existing_project(self):
        import tempfile
        from pathlib import Path
        from sqlalchemy import text, inspect
        from app import create_app, db
        with tempfile.TemporaryDirectory() as scratch:
            class FileConfig(fixture.WorkerConfig):
                SQLALCHEMY_DATABASE_URI='sqlite:///'+str(Path(scratch)/'old.sqlite')
                UPLOAD_FOLDER=str(Path(scratch)/'uploads')
                EXPORT_FOLDER=str(Path(scratch)/'exports')
            old=create_app(FileConfig)
            with old.app_context():
                db.session.add(Project(name='Существующий объект'))
                db.session.commit()
                db.session.execute(text('ALTER TABLE projects DROP COLUMN handover_date'))
                db.session.execute(text('DROP TABLE worker_offline_operations'))
                db.session.commit()
                db.session.remove()
            upgraded=create_app(FileConfig)
            with upgraded.app_context():
                project=Project.query.filter_by(name='Существующий объект').one()
                self.assertIsNone(project.handover_date)
                self.assertIn('worker_offline_operations',inspect(db.engine).get_table_names())
                db.session.remove()
