import re
import unittest
from app import create_app, db, login_manager
from app.models import Apartment, AppSetting, Project, Task, User, WorkCategory, WorkPoint
from app.services.mapping_service import ensure_default_categories, group_mapping_points, _mapping_custom_key
from config import Config


class MappingConfig(Config):
    TESTING = True
    SECRET_KEY = 'mapping-point-groups'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class MappingPointGroupTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(MappingConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.protection = login_manager.session_protection
        login_manager.session_protection = None
        db.create_all()
        self.project = Project(name='Mapping own')
        self.other = Project(name='Mapping other')
        self.user = User(username='mapping-admin', password_hash='unused', role='admin', project=self.project)
        apartment = Apartment(project=self.project, apartment_number='1')
        self.points = []
        for number in ('15', '22', '24'):
            for sheet in ('Таблица', 'Кладовые'):
                point = WorkPoint(point_number=number, source_sheet_name=sheet, short_name=f'{number} source label')
                self.points.append(point)
                db.session.add(Task(source_uid=f'{number}-{sheet}', project=self.project, apartment=apartment, work_point=point))
        self.foreign_point = WorkPoint(point_number='external-technical', source_sheet_name='Other')
        db.session.add(Task(source_uid='foreign', project=self.other,
                            apartment=Apartment(project=self.other, apartment_number='2'), work_point=self.foreign_point))
        db.session.add(self.user)
        ensure_default_categories()
        self.category = WorkCategory.query.filter_by(name='Маляры').one()
        self.category.work_points = [self.points[1], self.foreign_point]
        db.session.add(AppSetting(key=_mapping_custom_key(self.category.id), value='1'))
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(_user_id=str(self.user.id), _fresh=True, session_version=int(self.user.session_version or 0), current_project_id=self.project.id)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        login_manager.session_protection = self.protection

    def test_groups_merge_import_sheets_but_keep_different_numbers(self):
        groups = group_mapping_points(self.points)
        self.assertEqual([row['point_number'] for row in groups], ['15', '22', '24'])
        self.assertTrue(all(len(row['member_ids']) == 2 for row in groups))
        self.assertEqual(groups[-1]['display_name'], 'Электрика')

    def test_page_has_one_checkbox_per_logical_point_and_union_selection(self):
        response = self.client.get('/mappings')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        inputs = re.findall(r'<input[^>]*name="category_%s"[^>]*>' % self.category.id, html)
        self.assertEqual(len(inputs), 15)
        first = next(item for item in inputs if f'value="{self.points[0].id}"' in item)
        self.assertIn('checked', first)
        self.assertTrue(all(point.is_active for point in self.points))
        self.assertEqual(Task.query.filter(Task.work_point_id.in_([point.id for point in self.points])).count(), 6)

    def test_saving_one_checkbox_updates_every_sheet_without_clearing_other_project(self):
        response = self.client.post('/mappings', data={f'category_{self.category.id}': str(self.points[0].id)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual({point.id for point in self.category.work_points}, {self.points[0].id, self.points[1].id, self.foreign_point.id})

    def test_unchecking_group_clears_all_sheets_and_preserves_unshown_assignments(self):
        self.client.post('/mappings', data={})
        self.assertEqual({point.id for point in self.category.work_points}, {self.foreign_point.id})

    def test_old_client_can_submit_any_member_and_invalid_ids_are_ignored(self):
        self.client.post('/mappings', data={f'category_{self.category.id}': [str(self.points[1].id), '999999', 'invalid']})
        self.assertEqual({point.id for point in self.category.work_points}, {self.points[0].id, self.points[1].id, self.foreign_point.id})

    def test_full_catalogue_is_available_without_any_project_tasks(self):
        Task.query.filter_by(project_id=self.project.id).delete(synchronize_session=False)
        db.session.commit()
        response = self.client.get('/mappings')
        html = response.get_data(as_text=True)
        numbers = re.findall(r'<label[^>]*><b>([^<]+)</b>', html)
        self.assertEqual(set(numbers), {str(number) for number in range(10, 25)})
        self.assertIn('Работы по монтажу входных дверей', html)
        self.assertIn('Электрика', html)
        self.assertEqual(Task.query.filter_by(project_id=self.project.id).count(), 0)

    def test_missing_catalogue_point_can_be_saved_then_applied_to_a_new_import_sheet(self):
        self.client.get('/mappings')
        doors = WorkPoint.query.filter_by(point_number='23', source_sheet_name='manual').one()
        self.client.post('/mappings', data={f'category_{self.category.id}': str(doors.id)})
        self.assertIn(doors, self.category.work_points)
        from app.services.task_service import get_or_update_work_point
        imported = get_or_update_work_point('23', 'Работы по монтажу входных дверей', 'New sheet', 23)
        self.assertIn(self.category, imported.categories)
        self.assertEqual(imported.source_sheet_name, 'New sheet')

    def test_catalogue_is_idempotent(self):
        self.client.get('/mappings')
        count = WorkPoint.query.count()
        self.client.get('/mappings')
        self.assertEqual(WorkPoint.query.count(), count)
