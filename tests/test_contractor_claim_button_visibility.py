import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
import re

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, Contractor, Project, ROLE_ADMIN, ROLE_OFFICE, STATUS_NOT_STARTED, Task, User, WorkPoint


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "contractor-claim-button-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ContractorClaimButtonVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        TestConfig.EXPORT_FOLDER = self.tempdir.name
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

        self.project = Project(name='ЖК "Квартал 100" - 5 очередь')
        self.user = User(username="claim-button-admin", password_hash="unused", role=ROLE_ADMIN)
        self.contractor = Contractor(project=self.project, name='ООО "Коробка"')
        self.apartment = Apartment(project=self.project, apartment_number="1", owner_name="Иванов И.И.")
        self.point = WorkPoint(point_number="12", short_name="Возведение коробки здания")
        self.contractor.work_points.append(self.point)
        self.contractor.apartments.append(self.apartment)
        self.task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            source_uid="claim-button-task",
            description="Сбить наплывы строительных смесей.",
            status=STATUS_NOT_STARTED,
        )
        db.session.add_all([self.project, self.user, self.contractor, self.apartment, self.point, self.task])
        db.session.commit()

        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
            session["session_version"] = int(self.user.session_version or 0)
            session["current_project_id"] = self.project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection
        self.tempdir.cleanup()

    def test_claim_word_button_requires_selected_contractor(self):
        response = self.client.get("/contractors")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Претензия Word", response.get_data(as_text=True))

        response = self.client.get(f"/contractors?contractor_id={self.contractor.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Претензия Word", response.get_data(as_text=True))

    def test_claim_word_button_is_visible_on_excel_selection_without_contractor(self):
        response = self.client.get("/contractors/excel-selection")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Претензия Word", response.get_data(as_text=True))

        response = self.client.get(f"/contractors/excel-selection?contractor_id={self.contractor.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Претензия Word", response.get_data(as_text=True))

    def test_docx_export_without_contractor_redirects_to_list(self):
        response = self.client.get("/contractors/export?format=docx", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Прежде чем скачать, выберите подрядчика.", html)
        self.assertIn("Претензия Word", html)

    def test_docx_export_uses_office_contacts_when_current_user_is_not_office(self):
        self.user.full_name = "Инженер Тестовый"
        self.user.email = "engineer@example.test"
        self.user.phone = "8 900 111-11-11"
        office = User(
            username="office-claim-author",
            full_name="Офис Передачи",
            email="office@example.test",
            phone="8 900 222-22-22",
            role=ROLE_OFFICE,
            is_active=True,
            project_id=self.project.id,
            password_hash="unused",
        )
        db.session.add(office)
        db.session.commit()

        response = self.client.get(f"/contractors/export?format=docx&contractor_id={self.contractor.id}")

        self.assertEqual(response.status_code, 200)
        exported = sorted(Path(self.tempdir.name).glob("*.docx"))
        self.assertTrue(exported)
        with ZipFile(exported[-1]) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", document_xml))
        self.assertIn("Исп.: Офис Передачи", text)
        self.assertIn("8 900 222-22-22", text)
        self.assertIn("office@example.test", text)
        self.assertNotIn("Инженер Тестовый", text)
        self.assertNotIn("engineer@example.test", text)

    def test_contractor_form_saves_director_and_contract_date(self):
        response = self.client.post(
            "/contractors/new",
            data={
                "name": 'ООО "Фасад"',
                "legal_address": "164520, Архангельская обл.",
                "director_full_name": "Елена Петровна",
                "contract_number": "07-04/2025",
                "contract_date": "07.04.2025",
                "email": "facade@example.test",
                "work_points": [self.point.point_number],
                "apartment_groups": [str(self.apartment.id)],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        contractor = Contractor.query.filter_by(name='ООО "Фасад"').one()
        self.assertEqual(contractor.director_full_name, "Елена Петровна")
        self.assertEqual(contractor.contract_number, "07-04/2025")
        self.assertEqual(contractor.contract_date, "07.04.2025")

    def test_new_contractor_contract_date_is_not_prefilled_or_autocomplete_hint(self):
        response = self.client.get("/contractors/new")
        html = response.get_data(as_text=True)

        start = html.index('id="contractorContractDate"')
        field = html[start:html.index(">", start)]
        self.assertIn('name="contract_date"', field)
        self.assertIn('value=""', field)
        self.assertIn('autocomplete="off"', field)
        self.assertNotIn("07.04.2025", field)
        self.assertNotIn("placeholder=", field)

    def test_directory_hides_claim_fields_but_edit_form_keeps_them(self):
        self.contractor.legal_address = "164520, Архангельская обл."
        self.contractor.director_full_name = "Елена Петровна"
        self.contractor.contract_number = "07-04/2025"
        self.contractor.contract_date = "07.04.2025"
        self.contractor.email = "a-tarkov@bk.ru"
        db.session.commit()

        directory = self.client.get("/contractors/directory").get_data(as_text=True)
        self.assertIn("164520, Архангельская обл.", directory)
        self.assertNotIn("Елена Петровна", directory)
        self.assertNotIn("07-04/2025", directory)
        self.assertNotIn("a-tarkov@bk.ru", directory)

        edit_form = self.client.get(f"/contractors/{self.contractor.id}/edit").get_data(as_text=True)
        self.assertIn('name="director_full_name"', edit_form)
        self.assertIn('value="Елена Петровна"', edit_form)
        self.assertIn('name="contract_number"', edit_form)
        self.assertIn('value="07-04/2025"', edit_form)
        self.assertIn('name="contract_date"', edit_form)
        self.assertIn('value="07.04.2025"', edit_form)
        self.assertIn('name="email"', edit_form)
        self.assertIn('value="a-tarkov@bk.ru"', edit_form)


if __name__ == "__main__":
    unittest.main()
