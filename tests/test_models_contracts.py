from datetime import date, timedelta
import unittest

from config import Config
from app import create_app, db
from app.models import (
    AppSetting,
    Apartment,
    Contractor,
    Project,
    ROLE_ADMIN,
    ROLE_MANAGER,
    STATUS_CONCESSION,
    STATUS_CONTRACTOR,
    STATUS_DONE,
    STATUS_GUARANTEE,
    STATUS_NOT_STARTED,
    Task,
    User,
    WorkPoint,
    task_guarantee_contractor_setting_key,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "models-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class UserAccessContractsTests(unittest.TestCase):
    def test_project_access_ids_ignore_invalid_json_values_and_include_primary_project(self):
        user = User(project_id=7, project_access_ids_json='[1, "2", "bad", null]')

        self.assertEqual(user.project_access_ids, {1, 2, 7})
        self.assertFalse(user.can_access_project("bad"))
        self.assertTrue(user.can_access_project(2))
        self.assertTrue(user.can_access_project(type("ProjectRef", (), {"id": 7})()))

    def test_admin_and_explicit_all_project_access_override_project_allowlist(self):
        admin = User(role=ROLE_ADMIN, project_access_ids_json="[]")
        manager = User(role=ROLE_MANAGER, all_projects_access=True, project_access_ids_json="[]")

        self.assertTrue(admin.can_access_all_projects)
        self.assertTrue(admin.can_access_project("not-an-int"))
        self.assertTrue(manager.can_access_all_projects)
        self.assertTrue(manager.can_access_project(999))

    def test_set_project_access_normalizes_duplicates_and_admin_always_gets_all_projects(self):
        manager = User(role=ROLE_MANAGER)
        manager.set_project_access([3, "1", 3])

        self.assertFalse(manager.all_projects_access)
        self.assertEqual(manager.project_access_ids_json, "[1, 3]")
        self.assertIsNone(manager.project_id)

        single_project_user = User(role=ROLE_MANAGER)
        single_project_user.set_project_access(["5"])
        self.assertEqual(single_project_user.project_id, 5)

        admin = User(role=ROLE_ADMIN)
        admin.set_project_access([5], all_projects=False)
        self.assertTrue(admin.all_projects_access)
        self.assertEqual(admin.project_access_ids_json, "[]")

    def test_set_password_clears_plaintext_resets_lockout_and_revokes_old_sessions(self):
        user = User(password_plain="secret", failed_login_count=4, locked_until=date.today(), session_version=2)

        user.set_password("new-password")

        self.assertIsNone(user.password_plain)
        self.assertEqual(user.failed_login_count, 0)
        self.assertIsNone(user.locked_until)
        self.assertEqual(user.session_version, 3)
        self.assertTrue(user.check_password("new-password"))
        self.assertFalse(user.check_password("old-password"))


class ApartmentAndTaskModelContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_apartment_display_number_rejects_descriptive_service_text_and_uses_safe_fallback(self):
        apartment = Apartment(id=42, apartment_number="Building 3, total", construction_number="1-2-42")
        self.assertEqual(apartment.display_number(), "1-2-42")

        service_only = Apartment(id=99, apartment_number="Building 3, total", construction_number="No number")
        self.assertEqual(service_only.display_number(), "ID 99")
        self.assertEqual(service_only.display_number(fallback_to_id=False), "")

    def test_apartment_labels_distinguish_apartment_and_commercial_premises(self):
        apartment = Apartment(id=1, apartment_number="15", premise_type="apartment")
        commercial = Apartment(id=2, apartment_number="к15/к2", building="", premise_type="commercial")
        commercial_with_building = Apartment(id=3, apartment_number="15", building="2", premise_type="commercial")

        self.assertIn("15", apartment.label())
        self.assertIn("15", apartment.detail_label())
        self.assertIn("15", commercial.label())
        self.assertIn("2", commercial.label())
        self.assertIn("15", commercial_with_building.full_label())
        self.assertIn("2", commercial_with_building.full_label())

    def test_app_deadline_label_and_badge_use_effective_deadline_boundaries(self):
        today = date(2026, 7, 29)
        no_deadline = Apartment(app_deadline_raw="без замечаний")
        explicit = Apartment(app_deadline_date=date(2026, 8, 1))
        derived = Apartment(is_app_mode=True, inspection_date=date(2026, 7, 1))

        self.assertIn("срок", no_deadline.app_deadline_label().lower())
        self.assertEqual(explicit.app_deadline_label(), "01.08.2026")
        self.assertEqual(derived.effective_app_deadline_date(), date(2026, 8, 30))
        self.assertEqual(explicit.app_deadline_badge(today=today)["class"], "expiring")
        self.assertEqual(Apartment(app_deadline_date=today - timedelta(days=1)).app_deadline_badge(today=today)["class"], "expired")
        self.assertIsNone(Apartment(app_deadline_date=today + timedelta(days=16)).app_deadline_badge(today=today))

    def test_task_guarantee_contractors_require_same_apartment_and_work_point_and_sort_by_name(self):
        project = Project(name="Guarantee contractors QA")
        apartment = Apartment(project=project, apartment_number="1")
        other_apartment = Apartment(project=project, apartment_number="2")
        point = WorkPoint(point_number="10")
        other_point = WorkPoint(point_number="11")
        contractor_b = Contractor(project=project, name="Beta")
        contractor_a = Contractor(project=project, name="Alpha")
        contractor_other_apartment = Contractor(project=project, name="Other apartment")
        contractor_other_point = Contractor(project=project, name="Other point")
        apartment.contractors.extend([contractor_b, contractor_a, contractor_other_point])
        other_apartment.contractors.append(contractor_other_apartment)
        point.contractors.extend([contractor_b, contractor_a, contractor_other_apartment])
        other_point.contractors.append(contractor_other_point)
        task = Task(source_uid="guarantee-task", project=project, apartment=apartment, work_point=point, status=STATUS_GUARANTEE)
        db.session.add_all([project, apartment, other_apartment, point, other_point, task])
        db.session.commit()

        self.assertEqual([contractor.name for contractor in task.guarantee_contractors()], ["Alpha", "Beta"])
        self.assertEqual(task.status_label(), "Alpha, Beta")

        db.session.add(AppSetting(
            key=task_guarantee_contractor_setting_key(project.id, task.id),
            value=str(contractor_b.id),
        ))
        db.session.commit()

        self.assertEqual(task.selected_guarantee_contractor().name, "Beta")
        self.assertEqual(task.status_label(), "Beta")

    def test_task_status_label_and_class_cover_known_and_unknown_statuses(self):
        done = Task(status=STATUS_DONE)
        concession = Task(status=STATUS_CONCESSION)
        unknown = Task(status="custom")

        self.assertNotEqual(done.status_label(), STATUS_DONE)
        self.assertEqual(concession.status_class(), "secondary")
        self.assertEqual(unknown.status_label(), "custom")
        self.assertEqual(unknown.status_class(), "secondary")


if __name__ == "__main__":
    unittest.main()
