import re
import unittest
from pathlib import Path
from sqlalchemy import text

from app import create_app, db
from app.models import Apartment, InspectionCallNote, Project
import test_worker_task_updates as fixture


class InspectionCallListTests(unittest.TestCase):
    setUp = fixture.WorkerTaskUpdatesTests.setUp
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def invited(self):
        self.login(self.manager)
        self.apartment.po_status = 'thrown'
        self.apartment.po_status_manual = True
        db.session.commit()

    def test_numeric_sort_matches_other_premise_lists(self):
        self.invited()
        added = [Apartment(project=self.project, apartment_number=number, owner_name='Собственник',
                           po_status='thrown', po_status_manual=True) for number in ('20', '2', '10', '1')]
        db.session.add_all(added)
        db.session.commit()
        page = self.client.get('/records/call-list').text
        ids = [int(value) for value in re.findall(r'<article class="call-list-card" id="call-list-(\d+)"', page)]
        self.assertEqual([db.session.get(Apartment, value).apartment_number for value in ids], ['1', '2', '10', '20', '173'])

    def test_hiding_persists_without_changing_invitation_status_or_notes(self):
        self.invited()
        note = InspectionCallNote(project_id=self.project.id, apartment_id=self.apartment.id,
                                  user_id=self.manager.id, body='Перезвонить')
        db.session.add(note)
        db.session.commit()
        response = self.client.post(f'/records/call-list/{self.apartment.id}/visibility', data={'hidden': '1'})
        self.assertEqual(response.status_code, 303)
        page = self.client.get('/records/call-list').text
        self.assertNotIn(f'id="call-list-{self.apartment.id}"', page)
        self.assertIn('Показать скрытые (1)', page)
        self.assertEqual(self.apartment.po_status, 'thrown')
        self.assertIsNotNone(db.session.get(InspectionCallNote, note.id))
        self.assertNotIn('Помещений для обзвона:', self.client.get('/records').text)
        hidden_page = self.client.get('/records/call-list?hidden=1').text
        self.assertNotIn('Скрыть убранные карточки', hidden_page)
        self.assertIn('Вернуть в обзвон', hidden_page)
        self.assertIn('Перезвонить', hidden_page)
        response = self.client.post(f'/records/call-list/{self.apartment.id}/visibility', data={'hidden': '0'})
        self.assertEqual(response.status_code, 303)
        self.assertIn(f'id="call-list-{self.apartment.id}"', self.client.get('/records/call-list').text)

    def test_mobile_can_open_call_list_and_booking_settings(self):
        self.invited()
        headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1'}
        for path in ('/records/call-list', '/records/availability'):
            self.assertEqual(self.client.get(path, headers=headers).status_code, 200)

    def test_visibility_requires_csrf_and_project_access(self):
        self.invited()
        endpoint = f'/records/call-list/{self.apartment.id}/visibility'
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post(endpoint, data={'hidden': '1'}).status_code, 400)
        self.app.config['WTF_CSRF_ENABLED'] = False
        other_project = Project(name='Другой объект')
        other = Apartment(project=other_project, apartment_number='42', po_status='thrown', po_status_manual=True)
        db.session.add(other)
        db.session.commit()
        self.assertEqual(self.client.post(f'/records/call-list/{other.id}/visibility', data={'hidden': '1'}).status_code, 404)
        self.assertFalse(other.call_list_hidden)

    def test_invalid_action_and_readonly_role_cannot_hide_cards(self):
        self.invited()
        endpoint = f'/records/call-list/{self.apartment.id}/visibility'
        self.assertEqual(self.client.post(endpoint, data={'hidden': 'invalid'}).status_code, 400)
        self.manager.role = 'viewer'
        db.session.commit()
        self.login(self.manager)
        self.assertEqual(self.client.post(endpoint, data={'hidden': '1'}).status_code, 403)
        self.assertFalse(self.apartment.call_list_hidden)

    def test_existing_database_gets_the_additive_visibility_column(self):
        class LegacyConfig(fixture.WorkerConfig):
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{Path(self.temp_files.name) / "legacy.sqlite"}'

        old_app = create_app(LegacyConfig)
        with old_app.app_context():
            project = Project(name='Существующий объект')
            apartment = Apartment(project=project, apartment_number='12')
            db.session.add(apartment)
            db.session.commit()
            db.session.execute(text('ALTER TABLE apartments DROP COLUMN call_list_hidden'))
            db.session.commit()
            db.session.remove()
            db.engine.dispose()
        for _ in range(2):
            upgraded = create_app(LegacyConfig)
            with upgraded.app_context():
                apartment = Apartment.query.one()
                self.assertEqual(apartment.apartment_number, '12')
                self.assertFalse(apartment.call_list_hidden)
                db.session.remove()
                db.engine.dispose()
