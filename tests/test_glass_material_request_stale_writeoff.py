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
from app.routes import _material_key


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
        self.assertNotIn("кв 101", MaterialRequestItem.query.one().name)
        self.assertNotIn("кв 101", self.writeoff.items[0].name)

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


if __name__ == "__main__":
    unittest.main()
