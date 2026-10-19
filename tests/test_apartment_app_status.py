import unittest
from datetime import date

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, STATUS_NOT_STARTED, Task, User, WorkPoint
from app.services.task_service import APP_DEADLINE_NORMAL, APP_DEADLINE_NO_REMARKS, AVR_STATUS_NEEDED, AVR_STATUS_SIGNED


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "apartment-app-status-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ApartmentAppStatusTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.project = Project(name="APP status project")
        self.user = User(username="app-status-admin", password_hash="unused", role=ROLE_ADMIN)
        self.apartment = Apartment(project=self.project, apartment_number="1", is_app_mode=True)
        db.session.add_all([self.project, self.user, self.apartment])
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

    def test_app_signed_date_sets_deadline_after_60_calendar_days(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/app-status",
            data={
                "app_status": APP_DEADLINE_NORMAL,
                "app_signed_date": "2026-09-16",
                "app_deadline_manual": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.deadline_date, date(2026, 9, 16))
        self.assertEqual(apartment.app_deadline_date, date(2026, 11, 15))
        self.assertEqual(apartment.remark_deadline_date, date(2026, 11, 15))
        self.assertEqual(apartment.app_deadline_status, APP_DEADLINE_NORMAL)
        self.assertEqual(apartment.avr_status, AVR_STATUS_NEEDED)

        page = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        self.assertIn("15 ноября 2026", page)

    def test_manual_deadline_overrides_calculated_deadline(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/app-status",
            data={
                "app_status": APP_DEADLINE_NORMAL,
                "app_signed_date": "2026-09-16",
                "app_deadline_date": "2026-12-01",
                "app_deadline_manual": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.deadline_date, date(2026, 9, 16))
        self.assertEqual(apartment.app_deadline_date, date(2026, 12, 1))
        self.assertEqual(apartment.remark_deadline_date, date(2026, 12, 1))

    def test_changed_deadline_is_manual_even_without_hidden_flag(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/app-status",
            data={
                "app_status": APP_DEADLINE_NORMAL,
                "app_signed_date": "2026-09-16",
                "app_deadline_date": "2026-12-01",
                "app_deadline_manual": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.app_deadline_date, date(2026, 12, 1))
        self.assertEqual(apartment.remark_deadline_date, date(2026, 12, 1))

    def test_no_remarks_hides_avr_section(self):
        self.apartment.avr_status = AVR_STATUS_SIGNED
        self.apartment.avr_signed_date = date(2026, 10, 1)
        db.session.commit()

        response = self.client.post(
            f"/apartments/{self.apartment.id}/app-status",
            data={
                "app_status": APP_DEADLINE_NO_REMARKS,
                "app_signed_date": "2026-09-16",
                "app_deadline_manual": "0",
            },
        )

        self.assertEqual(response.status_code, 302)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.app_deadline_status, APP_DEADLINE_NO_REMARKS)
        self.assertIsNone(apartment.app_deadline_date)
        self.assertIsNone(apartment.remark_deadline_date)
        self.assertEqual(apartment.avr_status, AVR_STATUS_NEEDED)
        self.assertIsNone(apartment.avr_signed_date)

        page = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        self.assertIn("Без замечаний", page)
        self.assertNotIn("Изменить АВР", page)

    def test_dop_agreement_point_auto_marks_addendum_as_not_signed(self):
        point = WorkPoint(point_number="26", short_name="Отступное (ТМЦ)")
        task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=point,
            source_uid="dop-auto",
            description="Выдать ТМЦ",
            status=STATUS_NOT_STARTED,
        )
        db.session.add_all([point, task])
        db.session.commit()

        page = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)

        self.assertIn("Соглашение", page)
        self.assertIn("Не подписано", page)
        self.assertNotIn("Дата подписания доп. соглашения", page)

    def test_manual_addendum_none_overrides_dop_agreement_auto_status(self):
        point = WorkPoint(point_number="26", short_name="Отступное (ТМЦ)")
        task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=point,
            source_uid="dop-manual-none",
            description="Выдать ТМЦ",
            status=STATUS_NOT_STARTED,
        )
        db.session.add_all([point, task])
        db.session.commit()

        response = self.client.post(
            f"/apartments/{self.apartment.id}/addendum-status",
            data={"addendum_status": "none"},
        )

        self.assertEqual(response.status_code, 302)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.addendum_status, "none")
        self.assertTrue(apartment.addendum_status_manual)
        page = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        self.assertIn("Соглашение", page)
        self.assertIn("Не подписано", page)
        self.assertNotIn(">Нет<", page)

    def test_manual_addendum_signed_is_saved(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/addendum-status",
            data={"addendum_status": "signed", "addendum_signed_date": "2026-09-24"},
        )

        self.assertEqual(response.status_code, 302)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.addendum_status, "signed")
        self.assertEqual(apartment.addendum_signed_date, date(2026, 9, 24))
        self.assertTrue(apartment.addendum_status_manual)

        page = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        self.assertNotIn("Соглашение", page)

    def test_addendum_date_is_cleared_when_not_signed(self):
        self.apartment.addendum_status = "signed"
        self.apartment.addendum_signed_date = date(2026, 9, 24)
        self.apartment.addendum_status_manual = True
        db.session.commit()

        response = self.client.post(
            f"/apartments/{self.apartment.id}/addendum-status",
            data={"addendum_status": "needed", "addendum_signed_date": "2026-09-24"},
        )

        self.assertEqual(response.status_code, 302)
        apartment = db.session.get(Apartment, self.apartment.id)
        self.assertEqual(apartment.addendum_status, "needed")
        self.assertIsNone(apartment.addendum_signed_date)

    def test_non_app_apartment_cannot_have_addendum(self):
        self.apartment.is_app_mode = False
        point = WorkPoint(point_number="26", short_name="Отступное (ТМЦ)")
        task = Task(
            project=self.project,
            apartment=self.apartment,
            work_point=point,
            source_uid="dop-non-app",
            description="Выдать ТМЦ",
            status=STATUS_NOT_STARTED,
        )
        db.session.add_all([point, task])
        db.session.commit()

        page = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        self.assertNotIn("Соглашение", page)

        response = self.client.post(
            f"/apartments/{self.apartment.id}/addendum-status",
            data={"addendum_status": "signed"},
        )

        self.assertEqual(response.status_code, 400)

    def test_apartments_filter_uses_app_and_avr_status_labels(self):
        self.apartment.apartment_number = "1"
        self.apartment.is_app_mode = True
        self.apartment.app_deadline_status = APP_DEADLINE_NORMAL
        self.apartment.avr_status = AVR_STATUS_NEEDED
        no_remarks = Apartment(
            project=self.project,
            apartment_number="2",
            is_app_mode=True,
            app_deadline_status=APP_DEADLINE_NO_REMARKS,
            avr_status=AVR_STATUS_NEEDED,
        )
        signed_avr = Apartment(
            project=self.project,
            apartment_number="3",
            is_app_mode=True,
            app_deadline_status=APP_DEADLINE_NORMAL,
            avr_status=AVR_STATUS_SIGNED,
            avr_signed_date=date(2026, 9, 24),
        )
        not_accepted = Apartment(project=self.project, apartment_number="4", is_app_mode=False)
        db.session.add_all([no_remarks, signed_avr, not_accepted])
        db.session.commit()

        page = self.client.get("/apartments").get_data().decode("utf-8")
        self.assertIn('name="avr_status"', page)
        self.assertIn('value="with_remarks"', page)
        self.assertIn(f'value="{APP_DEADLINE_NO_REMARKS}"', page)
        self.assertIn(f'value="{AVR_STATUS_NEEDED}"', page)
        self.assertIn(f'value="{AVR_STATUS_SIGNED}"', page)
        self.assertIn('value="addendum"', page)

        with_remarks_page = self.client.get("/apartments?avr_status=with_remarks").get_data().decode("utf-8")
        self.assertIn("/apartments/1?back=", with_remarks_page)
        self.assertIn("/apartments/3?back=", with_remarks_page)
        self.assertNotIn("/apartments/2?back=", with_remarks_page)
        self.assertNotIn("/apartments/4?back=", with_remarks_page)

        no_remarks_page = self.client.get(f"/apartments?avr_status={APP_DEADLINE_NO_REMARKS}").get_data().decode("utf-8")
        self.assertIn("/apartments/2?back=", no_remarks_page)
        self.assertNotIn("/apartments/1?back=", no_remarks_page)
        self.assertNotIn("/apartments/3?back=", no_remarks_page)

        needed_page = self.client.get(f"/apartments?avr_status={AVR_STATUS_NEEDED}").get_data().decode("utf-8")
        self.assertIn("/apartments/1?back=", needed_page)
        self.assertNotIn("/apartments/2?back=", needed_page)
        self.assertNotIn("/apartments/3?back=", needed_page)

        signed_page = self.client.get(f"/apartments?avr_status={AVR_STATUS_SIGNED}").get_data().decode("utf-8")
        self.assertIn("/apartments/3?back=", signed_page)
        self.assertNotIn("/apartments/1?back=", signed_page)
        self.assertNotIn("/apartments/2?back=", signed_page)

    def test_apartments_filter_can_show_addendum_rows(self):
        point = WorkPoint(point_number="26", short_name="Отступное (ТМЦ)")
        addendum_apartment = Apartment(project=self.project, apartment_number="5", is_app_mode=True)
        task = Task(
            project=self.project,
            apartment=addendum_apartment,
            work_point=point,
            source_uid="filter-addendum",
            description="Выдать ТМЦ",
            status=STATUS_NOT_STARTED,
        )
        ordinary_app = Apartment(project=self.project, apartment_number="6", is_app_mode=True)
        db.session.add_all([point, addendum_apartment, task, ordinary_app])
        db.session.commit()

        page = self.client.get("/apartments?avr_status=addendum").get_data(as_text=True)

        self.assertIn(f"/apartments/{addendum_apartment.id}?back=", page)
        self.assertNotIn(f"/apartments/{ordinary_app.id}?back=", page)

    def test_apartments_filter_can_split_signed_and_unsigned_addendum_rows(self):
        point = WorkPoint(point_number="26", short_name="Отступное (ТМЦ)")
        signed = Apartment(
            project=self.project,
            apartment_number="7",
            is_app_mode=True,
            addendum_status="signed",
            addendum_signed_date=date(2026, 9, 24),
            addendum_status_manual=True,
        )
        unsigned = Apartment(
            project=self.project,
            apartment_number="8",
            is_app_mode=True,
            addendum_status="needed",
            addendum_status_manual=True,
        )
        signed_task = Task(project=self.project, apartment=signed, work_point=point, source_uid="signed-addendum", description="ДC", status=STATUS_NOT_STARTED)
        unsigned_task = Task(project=self.project, apartment=unsigned, work_point=point, source_uid="unsigned-addendum", description="ДC", status=STATUS_NOT_STARTED)
        db.session.add_all([point, signed, unsigned, signed_task, unsigned_task])
        db.session.commit()

        signed_page = self.client.get("/apartments?avr_status=addendum_signed").get_data(as_text=True)
        unsigned_page = self.client.get("/apartments?avr_status=addendum_not_signed").get_data(as_text=True)

        self.assertIn(f"/apartments/{signed.id}?back=", signed_page)
        self.assertNotIn(f"/apartments/{unsigned.id}?back=", signed_page)
        self.assertIn(f"/apartments/{unsigned.id}?back=", unsigned_page)
        self.assertNotIn(f"/apartments/{signed.id}?back=", unsigned_page)


if __name__ == "__main__":
    unittest.main()
