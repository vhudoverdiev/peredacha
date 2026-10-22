import unittest

from flask import g

from app import db
from app.models import Apartment, ChangeLog, Project
import test_apartment_history_contracts as fixture


class ApartmentConstructionNumberTests(unittest.TestCase):
    tearDown = fixture.ApartmentHistoryContractsTests.tearDown

    def setUp(self):
        fixture.ApartmentHistoryContractsTests.setUp(self)
        self.apartment.construction_number = 'C-001'
        db.session.commit()

    def save(self, **changes):
        data = {
            'owner_name': self.apartment.owner_name or '',
            'phone': self.apartment.phone or '',
            'finishing_type': self.apartment.finishing_type or '',
            'contract_number': self.apartment.contract_number or '',
            'mode': 'not_accepted',
            **changes,
        }
        g.pop('_login_user', None)
        return self.client.post(f'/apartments/{self.apartment.id}/details', data=data,
                                headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})

    def test_field_is_editable_on_desktop_and_phone(self):
        for agent in ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                      'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1'):
            with self.subTest(agent=agent):
                page = self.client.get(f'/apartments/{self.apartment.id}', headers={'User-Agent': agent}).text
                self.assertIn('Строительный номер', page)
                self.assertIn('name="construction_number" type="text" value="C-001" maxlength="80"', page)

    def test_number_is_saved_and_added_to_history(self):
        response = self.save(construction_number='  12/3-А  ')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['construction_number'], '12/3-А')
        db.session.refresh(self.apartment)
        self.assertEqual(self.apartment.construction_number, '12/3-А')
        history = ChangeLog.query.filter_by(field_name='construction_number').one()
        self.assertEqual((history.old_value, history.new_value), ('C-001', '12/3-А'))
        page = self.client.get(f'/apartments/{self.apartment.id}').text
        self.assertIn('Строительный номер изменён', page)

    def test_clearing_and_omitting_the_field_are_distinct(self):
        self.assertEqual(self.save(owner_name='Другой собственник').status_code, 200)
        self.assertEqual(self.apartment.construction_number, 'C-001')
        self.assertEqual(self.save(construction_number='').status_code, 200)
        self.assertIsNone(self.apartment.construction_number)

    def test_length_is_validated_before_any_changes_are_saved(self):
        self.assertEqual(self.save(construction_number='1' * 80).status_code, 200)
        response = self.save(construction_number='2' * 81, owner_name='Не сохранять')
        self.assertEqual(response.status_code, 400)
        db.session.refresh(self.apartment)
        self.assertEqual(self.apartment.construction_number, '1' * 80)
        self.assertEqual(self.apartment.owner_name, 'Старый собственник')

    def test_other_imported_rows_are_preserved_and_identity_collision_is_rejected(self):
        other = Apartment(project=self.project, apartment_number='1', construction_number='C-002')
        db.session.add(other)
        db.session.commit()
        self.assertEqual(self.save(construction_number='C-003').status_code, 200)
        self.assertEqual(other.construction_number, 'C-002')
        response = self.save(construction_number='C-002', owner_name='Не сохранять')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.apartment.construction_number, 'C-003')
        self.assertEqual(self.apartment.owner_name, 'Старый собственник')

    def test_viewer_can_read_but_cannot_edit(self):
        self.user.role = 'viewer'
        db.session.commit()
        g.pop('_login_user', None)
        page = self.client.get(f'/apartments/{self.apartment.id}').text
        self.assertIn('Строительный номер', page)
        self.assertIn('C-001', page)
        self.assertNotRegex(page, r'<input\b[^>]*name="construction_number"')
        self.assertEqual(self.save(construction_number='C-002').status_code, 403)

    def test_wrong_project_and_missing_csrf_cannot_change_the_number(self):
        other_project = Project(name='Другой объект')
        db.session.add(other_project)
        db.session.commit()
        with self.client.session_transaction() as state:
            state['current_project_id'] = other_project.id
        self.assertEqual(self.save(construction_number='C-002').status_code, 404)
        with self.client.session_transaction() as state:
            state['current_project_id'] = self.project.id
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.save(construction_number='C-002').status_code, 400)
        self.assertEqual(self.apartment.construction_number, 'C-001')
