import unittest
from datetime import date

from config import Config
from app import create_app, db, login_manager
from app.models import (
    Apartment,
    GlassMeasurement,
    GlassMeasurementItem,
    MaterialRequest,
    MaterialRequestItem,
    MaterialWriteOff,
    MaterialWriteOffItem,
    Project,
    ROLE_ADMIN,
    Task,
    User,
    WorkPoint,
)
from app.routes import _material_key, _material_request_display_rows


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "glass-request-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class GlassMaterialRequestStaleWriteoffTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Glass request QA")
        self.user = User(username="glass-request-admin", password_hash="unused", role=ROLE_ADMIN)
        self.apartment = Apartment(project=self.project, apartment_number="101")
        self.work_point = WorkPoint(point_number="QA", source_sheet_name="qa")
        self.task = Task(
            source_uid="glass-request-stale-writeoff",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Stale writeoff QA",
        )
        self.writeoff = MaterialWriteOff(
            project=self.project,
            author=self.user,
            writeoff_date=date(2026, 7, 1),
            comment="Old measurement request writeoff",
        )
        self.writeoff.tasks.append(self.task)
        self.writeoff.items.append(MaterialWriteOffItem(name="Old glass", quantity=1, unit="шт"))
        self.measurement = GlassMeasurement(
            project=self.project,
            task=self.task,
            apartment=self.apartment,
            status="ordered",
            ordered_at=date(2026, 7, 20),
            material_writeoff=self.writeoff,
        )
        self.measurement.items.append(
            GlassMeasurementItem(
                item_type="Стеклопакет",
                width=600,
                height=1200,
                quantity=1,
                size="600×1200",
            )
        )
        db.session.add_all([self.project, self.user, self.work_point])
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

    def test_request_reuses_stale_writeoff_without_blocking_or_double_spending(self):
        response = self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": str(self.measurement.id)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/materials/request/", response.headers["Location"])
        self.assertEqual(MaterialRequest.query.count(), 1)
        self.assertEqual(MaterialRequestItem.query.count(), 1)
        self.assertEqual(MaterialWriteOff.query.count(), 1)

        db.session.refresh(self.measurement)
        self.assertIsNotNone(self.measurement.material_request_item_id)
        self.assertEqual(self.measurement.material_writeoff_id, self.writeoff.id)
        self.assertEqual(len(self.writeoff.items), 1)
        self.assertIn("600", self.writeoff.items[0].name)
        stored_item = MaterialRequestItem.query.one()
        self.assertIn("кв 101", stored_item.name)
        self.assertIn("кв 101", self.writeoff.items[0].name)

        material_request = MaterialRequest.query.one()
        display_rows = _material_request_display_rows(material_request)
        self.assertEqual(display_rows[0]["apartment_number"], "101")
        self.assertNotIn("кв 101", display_rows[0]["display_name"])

        mobile_response = self.client.get(
            response.headers["Location"],
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 15; Mobile)"},
        )
        self.assertEqual(mobile_response.status_code, 200)
        mobile_html = mobile_response.get_data(as_text=True)
        self.assertNotIn("№ квартиры", mobile_html)
        self.assertIn(stored_item.name, mobile_html)

    def test_balance_deletion_clears_both_measurement_links(self):
        self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": str(self.measurement.id)},
        )
        request_item = MaterialRequestItem.query.one()

        response = self.client.post(
            "/materials/balance/delete",
            data={"material_keys": _material_key(request_item.name, request_item.unit)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MaterialRequest.query.count(), 0)
        self.assertEqual(MaterialWriteOff.query.count(), 0)
        db.session.refresh(self.measurement)
        self.assertIsNone(self.measurement.material_request_item_id)
        self.assertIsNone(self.measurement.material_writeoff_id)

    def test_transferred_request_can_add_item_during_edit(self):
        create_response = self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": str(self.measurement.id)},
        )
        self.assertEqual(create_response.status_code, 302)

        material_request = MaterialRequest.query.one()
        original_item = MaterialRequestItem.query.one()
        original_display_name = _material_request_display_rows(material_request)[0]["display_name"]

        update_response = self.client.post(
            f"/materials/request/{material_request.id}/update",
            data={
                "title": material_request.title,
                "request_date": "2026-07-21",
                "name[]": [original_display_name, "Новый материал"],
                "quantity[]": ["2", "3"],
                "unit[]": ["шт", "меш"],
                "item_id[]": [str(original_item.id), ""],
            },
        )

        self.assertEqual(update_response.status_code, 302)
        self.assertEqual(update_response.headers["Location"], f"/materials/request/{material_request.id}")
        db.session.refresh(self.measurement)
        self.assertIsNotNone(self.measurement.material_request_item_id)
        self.assertEqual(
            {item.name for item in material_request.items},
            {original_display_name, "Новый материал"},
        )
        self.assertEqual(
            {item.name for item in self.writeoff.items},
            {original_display_name, "Новый материал"},
        )

    def test_new_item_stays_with_the_last_measurement_group(self):
        second_apartment = Apartment(project=self.project, apartment_number="202")
        second_task = Task(
            source_uid="glass-request-second-group",
            project=self.project,
            apartment=second_apartment,
            work_point=self.work_point,
            description="Second group QA",
        )
        second_writeoff = MaterialWriteOff(
            project=self.project,
            author=self.user,
            writeoff_date=date(2026, 7, 1),
        )
        second_writeoff.tasks.append(second_task)
        second_measurement = GlassMeasurement(
            project=self.project,
            task=second_task,
            apartment=second_apartment,
            status="ordered",
            ordered_at=date(2026, 7, 20),
            material_writeoff=second_writeoff,
        )
        second_measurement.items.append(
            GlassMeasurementItem(
                item_type="Стеклопакет",
                width=700,
                height=1300,
                quantity=1,
                size="700×1300",
            )
        )
        db.session.add_all([second_apartment, second_task, second_writeoff, second_measurement])
        db.session.commit()

        create_response = self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": [str(self.measurement.id), str(second_measurement.id)]},
        )
        self.assertEqual(create_response.status_code, 302)

        material_request = MaterialRequest.query.one()
        display_rows = _material_request_display_rows(material_request)
        self.assertEqual([row["apartment_number"] for row in display_rows], ["101", "202"])

        update_response = self.client.post(
            f"/materials/request/{material_request.id}/update",
            data={
                "title": material_request.title,
                "request_date": "2026-07-21",
                "name[]": [
                    display_rows[0]["display_name"],
                    display_rows[1]["display_name"],
                    "Добавленная к квартире 202",
                ],
                "quantity[]": ["1", "1", "4"],
                "unit[]": ["шт", "шт", "меш"],
                "item_id[]": [
                    str(display_rows[0]["item"].id),
                    str(display_rows[1]["item"].id),
                    "",
                ],
            },
        )

        self.assertEqual(update_response.status_code, 302)
        self.assertEqual(len(material_request.items), 3)
        self.assertNotIn(
            "Добавленная к квартире 202",
            {item.name for item in self.writeoff.items},
        )
        self.assertIn(
            "Добавленная к квартире 202",
            {item.name for item in second_writeoff.items},
        )

    def test_transferred_request_edit_has_no_desktop_row_limit(self):
        for index in range(54):
            self.measurement.items.append(
                GlassMeasurementItem(
                    item_type="Стеклопакет",
                    width=601 + index,
                    height=1200,
                    quantity=1,
                    size=f"{601 + index}×1200",
                )
            )
        db.session.commit()

        create_response = self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": str(self.measurement.id)},
        )
        self.assertEqual(create_response.status_code, 302)

        material_request = MaterialRequest.query.one()
        display_rows = _material_request_display_rows(material_request)
        self.assertEqual(len(display_rows), 55)

        desktop_detail = self.client.get(
            f"/materials/request/{material_request.id}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        mobile_detail = self.client.get(
            f"/materials/request/{material_request.id}",
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 15; Mobile)"},
        )
        self.assertIn('data-unlimited-rows="1"', desktop_detail.get_data(as_text=True))
        self.assertNotIn('data-unlimited-rows="1"', mobile_detail.get_data(as_text=True))

        update_response = self.client.post(
            f"/materials/request/{material_request.id}/update",
            data={
                "title": material_request.title,
                "request_date": "2026-07-21",
                "name[]": [row["display_name"] for row in display_rows] + ["Позиция без лимита"],
                "quantity[]": ["1"] * 55 + ["2"],
                "unit[]": ["шт"] * 56,
                "item_id[]": [str(row["item"].id) for row in display_rows] + [""],
            },
        )

        self.assertEqual(update_response.status_code, 302)
        self.assertEqual(len(material_request.items), 56)
        self.assertEqual(len(self.writeoff.items), 56)
        self.assertIn("Позиция без лимита", {item.name for item in self.writeoff.items})


if __name__ == "__main__":
    unittest.main()
