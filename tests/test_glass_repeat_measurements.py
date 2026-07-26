import unittest
from datetime import date

from config import Config
from app import create_app, db, login_manager
from app.models import (
    Apartment,
    GlassMeasurement,
    GlassMeasurementItem,
    MaterialRequest,
    Project,
    ROLE_ADMIN,
    Task,
    User,
    WorkPoint,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "glass-repeat-measurements-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class GlassRepeatMeasurementsTests(unittest.TestCase):
    desktop_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    mobile_headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 15; Mobile)",
    }

    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Glass repeat measurements QA")
        self.user = User(
            username="glass-repeat-admin",
            password_hash="unused",
            role=ROLE_ADMIN,
            all_projects_access=True,
        )
        self.apartment = Apartment(project=self.project, apartment_number="160")
        self.work_point = WorkPoint(
            point_number="16",
            original_column_name="Окна",
            source_sheet_name="qa",
        )
        self.task = Task(
            source_uid="glass-repeat-root-task",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Несколько независимых заказов по одному замечанию",
            source_sheet_name="qa",
        )
        self.measurement = GlassMeasurement(
            project=self.project,
            apartment=self.apartment,
            task=self.task,
            status="ordered",
            ordered_at=date(2026, 7, 25),
        )
        self.measurement.items.extend(
            [
                GlassMeasurementItem(
                    item_type="Стеклопакет",
                    width=600,
                    height=1200,
                    quantity=2,
                    size="600×1200",
                ),
                GlassMeasurementItem(
                    item_type="Стекло",
                    width=400,
                    height=800,
                    quantity=2,
                    size="400×800",
                ),
                GlassMeasurementItem(
                    item_type="Рама/Створка",
                    width=700,
                    height=1300,
                    quantity=1,
                    size="700×1300",
                ),
            ]
        )
        db.session.add_all(
            [
                self.project,
                self.user,
                self.apartment,
                self.work_point,
                self.task,
                self.measurement,
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

    def _all_page(self) -> str:
        response = self.client.get(
            "/glass-measurements?tab=all&include_ordered=1&q=160",
            headers=self.desktop_headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def _add_repeat(self) -> Task:
        response = self.client.post(
            f"/glass/{self.task.id}/add-measurement",
            data={"q": "160", "page": "1"},
            headers=self.desktop_headers,
        )
        self.assertEqual(response.status_code, 302)
        repeat_task = Task.query.filter_by(glass_parent_task_id=self.task.id).one()
        self.assertEqual(repeat_task.source_sheet_name, "manual_glass_repeat")
        self.assertTrue(repeat_task.is_archived)
        self.assertTrue(repeat_task.is_missing_in_latest_sync)
        self.assertEqual(repeat_task.glass_measurement.status, "measure_needed")
        return repeat_task

    def test_desktop_plus_creates_independent_measurement_and_groups_the_row(self):
        initial_page = self._all_page()
        self.assertIn(
            f'action="/glass/{self.task.id}/add-measurement"',
            initial_page,
        )
        self.assertIn('aria-label="Добавить ещё замер"', initial_page)

        repeat_task = self._add_repeat()
        page = self._all_page()

        self.assertEqual(
            page.count(f'action="/glass/{self.task.id}/add-measurement"'),
            1,
        )
        self.assertIn(
            f'action="/glass/{repeat_task.glass_measurement.id}/return-to-all"',
            page,
        )
        self.assertIn(">В заказе</span>", page)
        self.assertEqual(
            page.count("Несколько независимых заказов по одному замечанию"),
            1,
        )

        before_mobile_post = Task.query.filter_by(
            glass_parent_task_id=self.task.id
        ).count()
        mobile_response = self.client.post(
            f"/glass/{self.task.id}/add-measurement",
            headers=self.mobile_headers,
        )
        self.assertEqual(mobile_response.status_code, 403)
        self.assertEqual(
            Task.query.filter_by(glass_parent_task_id=self.task.id).count(),
            before_mobile_post,
        )

    def test_ordered_item_types_are_rendered_as_separate_badges(self):
        page = self._all_page()

        self.assertIn(">Заказаны стеклопакеты</span>", page)
        self.assertIn(">Заказаны стекла</span>", page)
        self.assertIn(">Заказана рама/створка</span>", page)
        self.assertNotIn("Заказано: стеклопакеты, стекла", page)

    def test_repeat_can_be_saved_and_linked_to_its_own_material_request(self):
        repeat_task = self._add_repeat()
        repeat_measurement_id = repeat_task.glass_measurement.id

        save_response = self.client.post(
            f"/glass/{repeat_task.id}/save",
            data={
                "item_type[]": ["Стекло"],
                "size[]": ["500×900"],
                "item_comment[]": ["повторный заказ"],
                "quantity[]": ["1"],
                "ordered_at": "2026-07-25",
            },
            headers={
                **self.desktop_headers,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertTrue(save_response.get_json()["ok"])

        db.session.refresh(self.measurement)
        repeat_measurement = db.session.get(
            GlassMeasurement,
            repeat_measurement_id,
        )
        self.assertEqual(self.measurement.status, "ordered")
        self.assertEqual(repeat_measurement.status, "ordered")
        self.assertNotEqual(self.measurement.id, repeat_measurement.id)
        self.assertEqual(repeat_measurement.items[0].item_type, "Стекло")

        first_request_response = self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": [str(self.measurement.id)]},
            headers=self.desktop_headers,
        )
        second_request_response = self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": [str(repeat_measurement.id)]},
            headers=self.desktop_headers,
        )
        self.assertEqual(first_request_response.status_code, 302)
        self.assertEqual(second_request_response.status_code, 302)
        self.assertEqual(MaterialRequest.query.count(), 2)

        db.session.refresh(self.measurement)
        db.session.refresh(repeat_measurement)
        root_request_id = self.measurement.material_request_item.request_id
        repeat_request_id = repeat_measurement.material_request_item.request_id
        self.assertNotEqual(root_request_id, repeat_request_id)

        page = self._all_page()
        self.assertIn(">Заказаны стеклопакеты</span>", page)
        self.assertIn(">Заказаны стекла</span>", page)
        self.assertIn(">Заказано стекло</span>", page)
        self.assertEqual(
            page.count("Несколько независимых заказов по одному замечанию"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
