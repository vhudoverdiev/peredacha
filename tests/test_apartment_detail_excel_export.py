import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, STATUS_DONE, Task, User, WorkPoint
from config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "apartment-detail-export-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ApartmentDetailExcelExportTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

        class RuntimeConfig(TestConfig):
            EXPORT_FOLDER = str(Path(self.tempdir.name) / "exports")

        self.app = create_app(RuntimeConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Apartment Export QA")
        self.user = User(
            username="apartment-export-admin",
            password_hash="unused",
            role=ROLE_ADMIN,
            all_projects_access=True,
        )
        self.apartment = Apartment(
            project=self.project,
            apartment_number="42",
            finishing_type="Белая",
            owner_name="Иванов Иван Иванович",
            phone="+7 900 123-45-67",
        )
        open_point = WorkPoint(point_number="1", short_name="Пункт 1", source_sheet_name="qa")
        done_point = WorkPoint(point_number="2", short_name="Пункт 2", source_sheet_name="qa")
        self.open_task = Task(
            source_uid="apartment-export-open",
            project=self.project,
            apartment=self.apartment,
            work_point=open_point,
            description="Открытое замечание",
        )
        self.done_task = Task(
            source_uid="apartment-export-done",
            project=self.project,
            apartment=self.apartment,
            work_point=done_point,
            description="Выполненное замечание",
            status=STATUS_DONE,
            is_done=True,
        )
        db.session.add_all(
            [
                self.project,
                self.user,
                self.apartment,
                open_point,
                done_point,
                self.open_task,
                self.done_task,
            ]
        )
        db.session.commit()

        self.client = self.app.test_client()
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

    def test_desktop_apartment_card_has_excel_download_link(self):
        response = self.client.get(
            f"/apartments/{self.apartment.id}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"/apartments/{self.apartment.id}/remarks/export", html)
        self.assertIn("apartment-detail-export-btn", html)
        self.assertIn("d-none d-md-inline-flex", html)
        self.assertIn("<span>Скачать Excel</span>", html)

    def test_apartment_export_download_contains_all_apartment_remarks(self):
        response = self.client.get(f"/apartments/{self.apartment.id}/remarks/export")

        try:
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
            self.assertIn(".xlsx", response.headers.get("Content-Disposition", ""))

            workbook = load_workbook(BytesIO(response.data))
            try:
                self.assertIn("Не выполненные", workbook.sheetnames)
                self.assertIn("Выполненные", workbook.sheetnames)

                open_rows = list(workbook["Не выполненные"].iter_rows(values_only=True))
                done_rows = list(workbook["Выполненные"].iter_rows(values_only=True))

                self.assertEqual(open_rows[0][0], "Карточка помещения: кв 42")
                self.assertEqual(open_rows[1][:3], ("Помещение", "Отделка", "Замечания"))
                self.assertEqual(open_rows[2][:3], ("Кв 42", "Белая", "Открытое замечание"))

                self.assertEqual(done_rows[0][0], "Карточка помещения: кв 42")
                self.assertEqual(done_rows[1][:4], ("Помещение", "Отделка", "Замечания", "Кем выполнено"))
                self.assertEqual(done_rows[2][:4], ("Кв 42", "Белая", "Выполненное замечание", "Личная бригада"))
            finally:
                workbook.close()
        finally:
            response.close()

    def test_apartment_detail_renders_owner_and_phone_on_desktop_and_mobile(self):
        for user_agent in (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Mozilla/5.0 (Linux; Android 15; Mobile)",
        ):
            with self.subTest(user_agent=user_agent):
                response = self.client.get(
                    f"/apartments/{self.apartment.id}",
                    headers={"User-Agent": user_agent},
                )

                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn("ФИО собственника", html)
                self.assertIn("Иванов Иван Иванович", html)
                self.assertIn("Номер телефона", html)
                self.assertIn("+7 900 123-45-67", html)

    def test_apartment_detail_renders_contract_number_for_every_premise_type(self):
        slash_number = Apartment(project=self.project, apartment_number="330", construction_number="330/1")
        parenthesized_number = Apartment(project=self.project, apartment_number="10", construction_number="10(30)")
        duplicated_number = Apartment(project=self.project, apartment_number="44")
        manual_number = Apartment(project=self.project, apartment_number="45", contract_number="77")
        float_number = Apartment(project=self.project, apartment_number="1", construction_number="1", contract_number="1.0")
        parking = Apartment(project=self.project, apartment_number="П2", construction_number="П2", premise_type="parking", contract_number="П2.0")
        storeroom = Apartment(project=self.project, apartment_number="КЛ154", construction_number="КЛ154", premise_type="storeroom", contract_number="КЛ1")
        commercial = Apartment(
            project=self.project,
            apartment_number="331",
            construction_number="331/1",
            premise_type="commercial",
        )
        db.session.add_all([slash_number, parenthesized_number, duplicated_number, manual_number, float_number, parking, storeroom, commercial])
        db.session.commit()

        slash_html = self.client.get(f"/apartments/{slash_number.id}").get_data(as_text=True)
        parenthesized_html = self.client.get(f"/apartments/{parenthesized_number.id}").get_data(as_text=True)
        duplicated_html = self.client.get(f"/apartments/{duplicated_number.id}").get_data(as_text=True)
        manual_html = self.client.get(f"/apartments/{manual_number.id}").get_data(as_text=True)
        float_html = self.client.get(f"/apartments/{float_number.id}").get_data(as_text=True)
        parking_html = self.client.get(f"/apartments/{parking.id}").get_data(as_text=True)
        storeroom_html = self.client.get(f"/apartments/{storeroom.id}").get_data(as_text=True)
        commercial_html = self.client.get(f"/apartments/{commercial.id}").get_data(as_text=True)

        self.assertIn('name="contract_number"', slash_html)
        self.assertIn('value="Квартира 1"', slash_html)
        self.assertIn('name="contract_number"', parenthesized_html)
        self.assertIn('value="Квартира 30"', parenthesized_html)
        self.assertIn('name="contract_number"', duplicated_html)
        self.assertIn('value="Квартира 44"', duplicated_html)
        self.assertIn('name="contract_number"', duplicated_html)
        self.assertIn('value="Квартира 77"', manual_html)
        self.assertIn('value="Квартира 1"', float_html)
        self.assertNotIn('value="1.0"', float_html)
        self.assertIn('value="Парковка 2"', parking_html)
        self.assertNotIn('value="2.0"', parking_html)
        self.assertNotIn("П2.0", parking_html)
        self.assertIn("<h1 class=\"page-title\">Кладовка 154</h1>", storeroom_html)
        self.assertIn('value="Кладовка 1"', storeroom_html)
        self.assertNotIn("Кладовка КЛ", storeroom_html)
        self.assertIn('name="contract_number"', commercial_html)
        self.assertIn('value="331"', commercial_html)

    def test_apartments_list_orders_apartments_before_storerooms(self):
        apartment = Apartment(project=self.project, apartment_number="330", premise_type="apartment")
        storeroom = Apartment(project=self.project, apartment_number="КЛ154", premise_type="storeroom")
        db.session.add_all([storeroom, apartment])
        db.session.commit()

        html = self.client.get("/apartments").get_data(as_text=True)

        self.assertIn("кл 154", html)
        self.assertNotIn("Кладовка 154", html)
        self.assertNotIn("КЛ154</div>", html)
        self.assertLess(html.index("кв 42"), html.index("кл 154"))
        self.assertLess(html.index("кв 330"), html.index("кл 154"))

    def test_apartment_owner_names_are_saved_and_rendered_by_lines(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/details",
            data={
                "owner_name": "Иванов Иван\nПетров Пётр",
                "phone": "+7 900 123-45-67",
                "contract_number": "Квартира 88",
                "finishing_type": "Белая",
                "mode": "not_accepted",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.owner_name, "Иванов Иван\nПетров Пётр")
        self.assertEqual(apartment.contract_number, "88")
        html = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        self.assertIn('class="form-control form-control-sm apartment-owner-names-control"', html)
        self.assertIn("Иванов Иван\nПетров Пётр", html)
        self.assertIn('name="contract_number"', html)
        self.assertIn('value="Квартира 88"', html)


if __name__ == "__main__":
    unittest.main()
