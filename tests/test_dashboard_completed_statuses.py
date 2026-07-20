import re
import unittest

from config import Config
from app import create_app, db, login_manager
from app.models import (
    Apartment,
    Project,
    ROLE_ADMIN,
    STATUS_CONCESSION,
    STATUS_CONTRACTOR,
    STATUS_DONE,
    STATUS_FINISHERS,
    STATUS_GUARANTEE,
    STATUS_NOT_STARTED,
    STATUS_PROBLEM,
    Task,
    User,
    WorkCategory,
    WorkPoint,
)
from app.services.task_service import category_stats, dashboard_stats


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "dashboard-completed-statuses-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class DashboardCompletedStatusesTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Dashboard completed statuses QA")
        self.user = User(username="dashboard-status-admin", password_hash="unused", role=ROLE_ADMIN)
        self.apartment = Apartment(project=self.project, apartment_number="1")
        self.work_point = WorkPoint(point_number="10", source_sheet_name="dashboard-status-qa")
        self.category = WorkCategory(name="Dashboard status category", color="#75bd18")
        self.category.work_points.append(self.work_point)
        db.session.add_all([
            self.project,
            self.user,
            self.apartment,
            self.work_point,
            self.category,
        ])
        db.session.flush()

        statuses = (
            STATUS_DONE,
            STATUS_FINISHERS,
            STATUS_CONTRACTOR,
            STATUS_GUARANTEE,
            STATUS_CONCESSION,
            STATUS_NOT_STARTED,
            STATUS_PROBLEM,
        )
        for index, status in enumerate(statuses, start=1):
            db.session.add(Task(
                source_uid=f"dashboard-status-{index}",
                project=self.project,
                apartment=self.apartment,
                work_point=self.work_point,
                status=status,
                is_done=status in {
                    STATUS_DONE,
                    STATUS_FINISHERS,
                    STATUS_CONTRACTOR,
                    STATUS_GUARANTEE,
                    STATUS_CONCESSION,
                },
            ))
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

    def test_desktop_stats_count_every_terminal_workflow_status_as_completed(self):
        stats = dashboard_stats(self.project.id, include_all_completed_statuses=True)

        self.assertEqual(stats["tasks"], 7)
        self.assertEqual(stats["done"], 5)
        self.assertEqual(stats["not_done"], 2)
        self.assertEqual(stats["problem"], 1)
        self.assertEqual(stats["percent"], 71.4)

        category = next(
            row
            for row in category_stats(self.project.id, include_all_completed_statuses=True)
            if row["category"].id == self.category.id
        )
        self.assertEqual(category["total"], 7)
        self.assertEqual(category["done"], 5)
        self.assertEqual(category["left"], 2)

    def test_mobile_dashboard_keeps_the_previous_completed_count(self):
        response = self.client.get(
            "/",
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 15; Mobile)"},
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertRegex(html, r'<div class="dashboard-progress-meta">1 .*? 5 .*?</div>')

    def test_desktop_dashboard_renders_the_expanded_completed_count(self):
        response = self.client.get(
            "/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertRegex(html, r'<div class="dashboard-progress-meta">5 .*? 7 .*?</div>')
        main_card = re.search(
            r'<article class="dashboard-focus-card dashboard-focus-primary">.*?</article>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(main_card)
        self.assertIn("<b>5</b>", main_card.group(0))
        self.assertIn("<b>2</b>", main_card.group(0))


if __name__ == "__main__":
    unittest.main()
