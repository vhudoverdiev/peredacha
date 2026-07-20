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
from app.routes import _material_request_display_rows


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "glass-request-desktop-sort-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class GlassMaterialRequestDesktopSortTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Glass request desktop sort QA")
        self.user = User(username="glass-sort-admin", password_hash="unused", role=ROLE_ADMIN)
        self.work_point = WorkPoint(point_number="QA-SORT", source_sheet_name="qa")
        db.session.add_all([self.project, self.user, self.work_point])
        db.session.flush()
        self.measurements = [self._add_measurement(number) for number in ("10", "2", "1")]
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

    def _add_measurement(self, apartment_number: str) -> GlassMeasurement:
        apartment = Apartment(project=self.project, apartment_number=apartment_number)
        task = Task(
            source_uid=f"glass-request-sort-{apartment_number}",
            project=self.project,
            apartment=apartment,
            work_point=self.work_point,
            description=f"Glass {apartment_number}",
        )
        measurement = GlassMeasurement(
            project=self.project,
            apartment=apartment,
            task=task,
            status="ordered",
            ordered_at=date(2026, 7, 20),
        )
        measurement.items.append(
            GlassMeasurementItem(
                item_type="Стеклопакет",
                width=600,
                height=1200,
                quantity=1,
                size="600×1200",
            )
        )
        db.session.add(measurement)
        return measurement

    def _create_request(self, user_agent: str):
        response = self.client.post(
            "/glass/ordered/create-material-request",
            data={"measurement_ids": [str(item.id) for item in self.measurements]},
            headers={"User-Agent": user_agent},
        )
        self.assertEqual(response.status_code, 302)
        return _material_request_display_rows(MaterialRequest.query.one())

    def test_desktop_request_items_are_sorted_numerically_by_apartment(self):
        rows = self._create_request("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

        self.assertEqual([row["apartment_number"] for row in rows], ["1", "2", "10"])

    def test_mobile_request_item_order_is_unchanged(self):
        rows = self._create_request("Mozilla/5.0 (Linux; Android 15; Mobile)")

        self.assertEqual([row["apartment_number"] for row in rows], ["10", "2", "1"])


if __name__ == "__main__":
    unittest.main()
