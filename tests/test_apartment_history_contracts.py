import unittest
from datetime import date, datetime, timedelta

from app import create_app, db, login_manager
from app.models import Apartment, ChangeLog, Project, ROLE_ADMIN, User
from app.routes import (
    _apartment_inspection_displays,
    _build_change_history_entry,
    _format_inspection_display_value,
)
from config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "apartment-history-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ApartmentHistoryContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Apartment history QA")
        self.user = User(
            username="apartment-history-admin",
            password_hash="unused",
            role=ROLE_ADMIN,
            all_projects_access=True,
        )
        self.apartment = Apartment(
            project=self.project,
            apartment_number="1",
            owner_name="Старый собственник",
            phone="+7 900 000-00-00",
            finishing_type="Черновая",
        )
        db.session.add_all([self.project, self.user, self.apartment])
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

    def _change_field_names(self):
        return {
            change.field_name
            for change in ChangeLog.query.filter_by(action="apartment_field_update").all()
        }

    def test_past_inspection_datetime_hides_time_but_future_keeps_it(self):
        past = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=1)
        future = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)

        self.assertEqual(_format_inspection_display_value(date(2026, 10, 13)), "13.10.2026")
        self.assertEqual(_format_inspection_display_value(past), past.strftime("%d.%m.%Y"))
        self.assertEqual(_format_inspection_display_value(future), future.strftime("%d.%m.%Y %H:%M"))

    def test_detail_fields_are_logged_and_rendered_with_specific_history_labels(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/details",
            data={
                "owner_name": "Новый собственник",
                "phone": "+7 900 111-22-33",
                "finishing_type": "Белая",
                "mode": "app",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {"owner_name", "phone", "finishing_type", "apartment_mode"},
            self._change_field_names(),
        )

        page = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        self.assertIn("ФИО собственника изменено", page)
        self.assertIn("Номер телефона изменён", page)
        self.assertIn("Отделка изменена", page)
        self.assertIn("Режим помещения изменён", page)
        self.assertNotIn("Комментарий помещения изменён: было «Старый собственник»", page)

    def test_inspection_status_and_date_are_logged_and_return_history_entries(self):
        status_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-status",
            data={"inspection_status": "was"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(status_response.status_code, 200)
        status_summary = status_response.get_json()["history_entry"]["summary"]
        self.assertIn("Статус осмотра помещения изменён", status_summary)
        self.assertIn("был «Не был»", status_summary)
        old_date_label = status_response.get_json()["inspection_date_label"]

        date_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date",
            data={"inspection_date": "2026-09-15"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(date_response.status_code, 200)
        summary = date_response.get_json()["history_entry"]["summary"].replace("15 сентября 2026", "15.09.2026")
        self.assertIn("Дата осмотра помещения изменена", summary)
        self.assertIn("была «%s»" % old_date_label, summary)
        self.assertIn("15.09.2026", summary)
        self.assertIn("apartment_inspection_status", self._change_field_names())
        self.assertIn("apartment_inspection_date", self._change_field_names())

    def test_inspection_dates_are_added_and_deleted_individually(self):
        first_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date",
            data={"inspection_date": "2026-09-15"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )
        second_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date",
            data={"inspection_date": "2026-09-20"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        second_payload = second_response.get_json()
        self.assertEqual(second_payload["inspection_date_labels"], ["15.09.2026", "20.09.2026"])
        self.assertEqual(
            second_payload["inspection_items"],
            [
                {"label": "15.09.2026", "value": "2026-09-15"},
                {"label": "20.09.2026", "value": "2026-09-20"},
            ],
        )
        self.assertEqual(second_payload["inspection_max"], 5)
        self.assertEqual(second_payload["inspection_delete_url"], f"/apartments/{self.apartment.id}/inspection-date/delete")
        detail_html = self.client.get(f"/apartments/{self.apartment.id}").get_data(as_text=True)
        date_picker_position = detail_html.index('name="inspection_date"')
        add_button_position = detail_html.index(">Добавить</button>", date_picker_position)
        reset_button_position = detail_html.index(">Не был</button>", add_button_position)
        self.assertLess(date_picker_position, add_button_position)
        self.assertLess(add_button_position, reset_button_position)
        self.assertIn('class="apartment-inline-form apartment-inspection-date-form"', detail_html)
        self.assertNotIn('class="apartment-inline-form apartment-inspection-date-form" data-apartment-async="1"', detail_html)
        self.assertIn("apartment-inspection-action-btn apartment-inspection-reset-btn", detail_html)

        delete_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date/delete",
            data={"inspection_date": "2026-09-15"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.get_json()["inspection_date_labels"], ["20.09.2026"])

    def test_inspection_date_form_uses_full_page_post(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date",
            data={"inspection_date": "2026-09-15"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(_apartment_inspection_displays([self.apartment]), ["15.09.2026"])

    def test_inspection_dates_allow_five_and_reject_the_sixth(self):
        for day in range(1, 6):
            response = self.client.post(
                f"/apartments/{self.apartment.id}/inspection-date",
                data={"inspection_date": f"2026-09-{day:02d}"},
                headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            )
            self.assertEqual(response.status_code, 200)

        overflow = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date",
            data={"inspection_date": "2026-09-06"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(overflow.status_code, 400)
        self.assertIn("не более 5", overflow.get_json()["message"])
        self.assertEqual(len(_apartment_inspection_displays([self.apartment])), 5)

    def test_schedule_and_additional_dates_display_and_can_be_deleted(self):
        self.apartment.inspection_note = "__inspection_schedule__:2026-09-15T10:30:00"
        db.session.commit()

        add_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date",
            data={"inspection_date": "2026-09-20"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(add_response.get_json()["inspection_date_labels"], ["15.09.2026", "20.09.2026"])
        delete_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date/delete",
            data={"inspection_date": "2026-09-15"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.get_json()["inspection_date_labels"], ["20.09.2026"])

    def test_not_was_clears_all_inspection_dates_and_schedule_marker(self):
        self.apartment.inspection_date = date(2026, 9, 15)
        self.apartment.first_inspection_date = date(2026, 9, 15)
        self.apartment.reinspection_date = date(2026, 9, 20)
        self.apartment.inspection_note = "__inspection_schedule__:2026-09-25T10:30:00\nДополнительный осмотр: 30.09.2026"
        self.apartment.first_inspection_present = True
        db.session.commit()

        response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-status",
            data={"inspection_status": "not_was"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["inspection_status"], "Не был")
        self.assertEqual(_apartment_inspection_displays([self.apartment]), [])
        self.assertIn("__inspection_dates_backup__:", self.apartment.inspection_note)

        restore_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-status",
            data={"inspection_status": "was"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(restore_response.get_json()["inspection_status"], "Был")
        self.assertEqual(
            _apartment_inspection_displays([self.apartment]),
            ["15.09.2026", "20.09.2026", "25.09.2026", "30.09.2026"],
        )
        delete_response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date/delete",
            data={"inspection_date": "2026-09-20"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(
            delete_response.get_json()["inspection_date_labels"],
            ["15.09.2026", "25.09.2026", "30.09.2026"],
        )

    def test_future_inspection_date_returns_planned_status(self):
        future_date = date.today() + timedelta(days=7)

        response = self.client.post(
            f"/apartments/{self.apartment.id}/inspection-date",
            data={"inspection_date": future_date.isoformat()},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["inspection_status"], "Будет")
        self.assertEqual(payload["inspection_status_class"], "status-pill-warning")

    def test_new_apartment_history_fields_are_rendered_in_russian(self):
        cases = [
            (
                "addendum_status",
                "needed",
                "signed",
                "Статус доп. соглашения изменён: был «Не подписано», стал «Подписано».",
            ),
            (
                "app_deadline_status",
                "normal",
                "no_remarks",
                "Статус АПП изменён: был «Есть замечания», стал «Без замечаний».",
            ),
            (
                "deadline_date",
                "2026-09-16",
                "2026-09-25",
                "Дата подписания АПП изменена: была «16 сентября 2026», стала «25 сентября 2026».",
            ),
            (
                "app_deadline_date",
                "2026-11-15",
                "2026-12-01",
                "Срок устранения замечаний изменён: был «15 ноября 2026», стал «1 декабря 2026».",
            ),
            (
                "addendum_signed_date",
                "",
                "2026-09-24",
                "Дата подписания доп. соглашения изменена: была «не задана», стала «24 сентября 2026».",
            ),
        ]

        for field_name, old_value, new_value, expected_summary in cases:
            with self.subTest(field_name=field_name):
                change = ChangeLog(
                    action="apartment_field_update",
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    user=self.user,
                )
                entry = _build_change_history_entry(change)
                self.assertEqual(entry["summary"], expected_summary)
                self.assertNotIn(field_name, entry["summary"])
                if old_value:
                    self.assertNotIn(old_value, entry["summary"])
                self.assertNotIn(new_value, entry["summary"])


if __name__ == "__main__":
    unittest.main()
