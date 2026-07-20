import re
import unittest
from pathlib import Path

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, Task, User, WorkCategory, WorkPoint


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
SHARED_CSS = PROJECT_ROOT / "app" / "static" / "style.css"
MOBILE_CSS = PROJECT_ROOT / "app" / "static" / "mobile-only.css"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "task-detail-dop-agreement-style-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class TaskDetailDopAgreementStyleTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        project = Project(name="Dop agreement style QA")
        user = User(username="dop-agreement-admin", password_hash="unused", role=ROLE_ADMIN)
        apartment = Apartment(project=project, apartment_number="1")
        work_point = WorkPoint(
            point_number="21",
            source_sheet_name="qa",
            original_column_name="Отступное (ТМЦ)",
        )
        work_point.categories.extend(
            [
                WorkCategory(name="Доп.Соглашение", color="#6c757d"),
                WorkCategory(name="Прочее", color="#6c757d"),
            ]
        )
        task = Task(
            source_uid="dop-agreement-style-task",
            project=project,
            apartment=apartment,
            work_point=work_point,
            description="Проверка оформления дополнительного соглашения",
        )
        db.session.add_all([project, user, apartment, work_point, task])
        db.session.commit()
        self.task_id = task.id

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
            session["session_version"] = int(user.session_version or 0)
            session["current_project_id"] = project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_only_dop_agreement_category_gets_the_visual_hook(self):
        response = self.client.get(
            f"/tasks/{self.task_id}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(page.count("task-detail-dop-agreement-badge"), 1)
        self.assertIn('class="task-detail-dop-agreement-label-default">Доп.Соглашение</span>', page)
        self.assertIn(
            'class="task-detail-dop-agreement-label-desktop" aria-hidden="true" hidden>Доп. соглашение</span>',
            page,
        )
        self.assertRegex(
            page,
            r'class="section-outline-badge"[^>]*>Прочее</span>',
        )

    def test_new_rules_are_strictly_desktop_scoped(self):
        desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        shared_css = SHARED_CSS.read_text(encoding="utf-8")
        mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        selectors = re.findall(
            r"([^{}]*task-detail-dop-agreement-badge[^{}]*)\{",
            desktop_css,
        )

        self.assertGreaterEqual(len(selectors), 4)
        self.assertTrue(all("html.desktop-like-pointer" in selector for selector in selectors))
        self.assertIn('content: "\\f38b"', desktop_css)
        self.assertNotIn("task-detail-dop-agreement-badge", shared_css)
        self.assertNotIn("task-detail-dop-agreement-badge", mobile_css)


if __name__ == "__main__":
    unittest.main()
