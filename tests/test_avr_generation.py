from datetime import date
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app import create_app, db, login_manager
from app.models import Apartment, Project, User
from app.routes import _set_inspection_dates_backup
from app.services.avr_document import completion_phrase_with_inspection_date
from config import Config


class AvrConfig(Config):
    TESTING = True
    SECRET_KEY = 'avr-generation-test'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class AvrGenerationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(AvrConfig)
        self.context = self.app.app_context()
        self.context.push()
        self.protection = login_manager.session_protection
        login_manager.session_protection = None
        self.temp = tempfile.TemporaryDirectory()
        self.app.config['EXPORT_FOLDER'] = self.temp.name
        db.create_all()
        self.project = Project(name='AVR Test', address='Тестовая улица, дом 1')
        self.user = User(username='avr-manager', full_name='Иванов Иван Иванович', role='manager',
                         password_hash='unused', project=self.project)
        self.apartment = Apartment(project=self.project, apartment_number='6', floor='2',
                                   owner_name='Петров Пётр Петрович', first_inspection_date=date(2026, 4, 21),
                                   inspection_date=date(2026, 6, 5), reinspection_date=date(2026, 6, 10))
        db.session.add_all([self.user, self.apartment])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(_user_id=str(self.user.id), _fresh=True,
                           session_version=int(self.user.session_version or 0), current_project_id=self.project.id)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.protection
        self.temp.cleanup()

    def generate(self, **extra):
        data = dict(apartment_id=str(self.apartment.id), floor='2', owner_name='Петров Пётр Петрович')
        data.update(extra)
        response = self.client.post('/avr', data=data)
        self.assertEqual(response.status_code, 200)
        try:
            payload = response.get_data()
        finally:
            response.close()
        self.assertTrue(payload.startswith(b'PK'), payload[:100])
        with ZipFile(BytesIO(payload)) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
        text = ''.join(node.text or '' for node in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
        return text

    def test_document_uses_current_full_name_and_first_inspection(self):
        text = self.generate(inspection_date='2030-01-01',
                             completion_phrase='Все замечания с акта осмотра от __.__.____ устранены.\nДополнительный текст')
        self.assertIn('Иванов Иван Иванович', text)
        self.assertIn('Все замечания с акта осмотра от 21.04.2026 устранены.', text)
        self.assertIn('Дополнительный текст', text)
        self.assertNotIn('2030', text)

    def test_another_account_uses_its_own_full_name(self):
        self.user.full_name = 'Смирнова Анна Сергеевна'
        db.session.commit()
        text = self.generate()
        self.assertIn('Смирнова Анна Сергеевна', text)
        self.assertNotIn('Иванов Иван Иванович', text)

    def test_date_falls_back_to_earliest_stored_inspection(self):
        self.apartment.first_inspection_date = None
        db.session.commit()
        self.assertIn('от 05.06.2026 устранены', self.generate())

    def test_inspection_history_and_duplicate_apartment_rows_are_considered(self):
        self.apartment.first_inspection_present = True
        self.apartment.inspection_note = _set_inspection_dates_backup(None, [date(2026, 3, 12)])
        duplicate = Apartment(project=self.project, apartment_number='6', first_inspection_date=date(2026, 2, 1))
        db.session.add(duplicate)
        db.session.commit()
        self.assertIn('от 01.02.2026 устранены', self.generate())

    def test_missing_date_is_not_replaced_with_today(self):
        self.apartment.first_inspection_date = None
        self.apartment.inspection_date = None
        self.apartment.reinspection_date = None
        db.session.commit()
        self.assertIn('от __.__.____ устранены', self.generate())

    def test_missing_account_name_does_not_generate_another_persons_act(self):
        self.user.full_name = None
        db.session.commit()
        with patch('app.routes.build_avr_docx') as build:
            response = self.client.post('/avr', data={'apartment_id': str(self.apartment.id)})
        build.assert_not_called()
        self.assertIn('Укажите ФИО', response.get_data(as_text=True))

    def test_form_and_apartment_picker_use_same_values_as_document(self):
        response = self.client.get(f'/avr?apartment_id={self.apartment.id}')
        html = response.get_data(as_text=True)
        self.assertIn('value="Иванов Иван Иванович" data-avr-developer required', html)
        self.assertIn('от 21.04.2026 устранены', html)
        self.assertIn('value="2026-04-21" data-avr-inspection-date', html)

    def test_custom_completion_text_is_preserved(self):
        text = 'Отделочные работы выполнены.\nПретензий нет.'
        self.assertEqual(completion_phrase_with_inspection_date(text, date(2026, 4, 21)), text)
        self.assertEqual(completion_phrase_with_inspection_date('Все замечания с акта осмотра от 01.01.2020 устранены', date(2026, 4, 21)), 'Все замечания с акта осмотра от 21.04.2026 устранены')

    def test_date_replacement_does_not_remove_qualifications(self):
        text = 'Все замечания с акта осмотра от 01.01.2020, кроме пункта 15, устранены'
        self.assertEqual(completion_phrase_with_inspection_date(text, date(2026, 4, 21)),
                         'Все замечания с акта осмотра от 21.04.2026, кроме пункта 15, устранены')
        self.assertEqual(completion_phrase_with_inspection_date('Все замечания с акта осмотра от     устранены', date(2026, 4, 21)),
                         'Все замечания с акта осмотра от 21.04.2026 устранены')

    def test_manual_representative_is_used_without_changing_account(self):
        text = self.generate(developer_representative='  Смирнова  Анна Сергеевна  ')
        self.assertIn('Смирнова Анна Сергеевна', text)
        self.assertNotIn('Иванов Иван Иванович', text)
        self.assertEqual(self.user.full_name, 'Иванов Иван Иванович')

    def test_manual_representative_works_without_profile_name(self):
        self.user.full_name = None
        db.session.commit()
        self.assertIn('Смирнова Анна Сергеевна', self.generate(developer_representative='Смирнова Анна Сергеевна'))

    def test_explicitly_empty_representative_is_rejected(self):
        with patch('app.routes.build_avr_docx') as build:
            response = self.client.post('/avr', data={'apartment_id': str(self.apartment.id), 'developer_representative': '   '})
        build.assert_not_called()
        self.assertIn('Укажите ФИО', response.get_data(as_text=True))
