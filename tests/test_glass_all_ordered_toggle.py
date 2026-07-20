import html
import re
import unittest
from urllib.parse import parse_qs, urlparse

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, GlassMeasurement, Project, ROLE_ADMIN, Task, User, WorkPoint


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "glass-all-ordered-toggle-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class GlassAllOrderedToggleTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Glass all toggle QA")
        self.user = User(username="glass-all-toggle-admin", password_hash="unused", role=ROLE_ADMIN)
        self.work_point = WorkPoint(point_number="16", source_sheet_name="qa")
        db.session.add_all([self.project, self.user, self.work_point])
        db.session.flush()

        self._add_task("1", "never-ordered", None)
        self._add_task("2", "moved-to-order", "measure_needed")
        self._add_task("3", "already-ordered", "ordered")
        self._add_task("4", "already-replaced", "replaced")
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

    def _add_task(self, apartment_number: str, description: str, measurement_status: str | None):
        apartment = Apartment(project=self.project, apartment_number=apartment_number)
        task = Task(
            source_uid=f"glass-all-toggle-{apartment_number}",
            project=self.project,
            apartment=apartment,
            work_point=self.work_point,
            description=description,
        )
        db.session.add(task)
        if measurement_status is not None:
            db.session.add(
                GlassMeasurement(
                    project=self.project,
                    apartment=apartment,
                    task=task,
                    status=measurement_status,
                )
            )

    def _desktop_get(self, query: str = ""):
        return self.client.get(
            f"/glass-measurements{query}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )

    def test_unchecked_toggle_shows_only_never_ordered_rows(self):
        response = self._desktop_get("?tab=all")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("never-ordered", page)
        self.assertNotIn("moved-to-order", page)
        self.assertNotIn("already-ordered", page)
        self.assertNotIn("already-replaced", page)
        self.assertRegex(page, r'name="include_ordered" value="1"(?![^>]* checked)')

    def test_checked_toggle_shows_every_status(self):
        response = self._desktop_get("?tab=all&include_ordered=1")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for description in ("never-ordered", "moved-to-order", "already-ordered", "already-replaced"):
            self.assertIn(description, page)
        self.assertRegex(page, r'name="include_ordered" value="1"[^>]* checked')

    def test_checked_toggle_survives_pagination(self):
        for number in range(5, 26):
            self._add_task(str(number), f"never-ordered-{number}", None)
        db.session.commit()

        page = self._desktop_get("?tab=all&include_ordered=1").get_data(as_text=True)
        next_link = re.search(r'<a class="page-link" href="([^"]+)">Далее</a>', page)

        self.assertIsNotNone(next_link)
        query = parse_qs(urlparse(html.unescape(next_link.group(1))).query)
        self.assertEqual(query.get("include_ordered"), ["1"])
        self.assertEqual(query.get("page"), ["2"])

    def test_mobile_layout_does_not_get_the_desktop_toggle(self):
        response = self.client.get(
            "/glass-measurements?tab=all&include_ordered=1",
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 15; Mobile)"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('name="include_ordered"', response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
