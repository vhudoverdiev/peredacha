from datetime import date, datetime, timedelta
import unittest

from config import Config
from app import create_app, db, login_manager
from flask_login import login_user

from app.models import DeletionActionLog, Project, ROLE_ADMIN, SiteErrorReport, SiteVisit, User
from app.routes import _build_developer_statistics_context, _build_site_visit_visitor_groups


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "developer-statistics-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class DeveloperStatisticsContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_statistics_totals_include_guest_request_ips_and_unique_visits_are_unique_ips(self):
        user = User(username="stats-admin", role=ROLE_ADMIN, password_hash="unused")
        db.session.add(user)
        db.session.flush()
        visits = [
            SiteVisit(
                user=user,
                ip_address="203.0.113.10",
                endpoint="main.dashboard",
                path="/",
                method="GET",
                status_code=200,
                is_authenticated=True,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 10, 0),
            ),
            SiteVisit(
                user=user,
                ip_address="203.0.113.10",
                endpoint="main.apartments",
                path="/apartments",
                method="GET",
                status_code=200,
                is_authenticated=True,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 10, 5),
            ),
            SiteVisit(
                ip_address="198.51.100.25",
                endpoint="auth.login",
                path="/login",
                method="GET",
                status_code=200,
                is_authenticated=False,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 10, 10),
            ),
            SiteVisit(
                ip_address="198.51.100.25",
                endpoint="auth.login",
                path="/login",
                method="GET",
                status_code=200,
                is_authenticated=False,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 10, 15),
            ),
            SiteVisit(
                ip_address="192.0.2.77",
                endpoint="analytics_tab_open",
                path="/",
                method="TAB",
                status_code=204,
                is_authenticated=False,
                visit_kind="tab_open",
                tab_id="tab-not-counted-as-request",
                created_at=datetime(2026, 8, 4, 10, 20),
            ),
        ]
        db.session.add_all(visits)
        db.session.commit()

        with self.app.test_request_context("/developer/statistics?start_date=2026-08-04&end_date=2026-08-04"):
            context = _build_developer_statistics_context()

        self.assertEqual(context["total_visits"], 4)
        self.assertEqual(context["unique_visitors"], 2)
        self.assertEqual(context["unique_ips"], 2)
        self.assertEqual(
            {item["ip_address"]: item["hits"] for item in context["top_ips"]},
            {"203.0.113.10": 2, "198.51.100.25": 2},
        )

    def test_statistics_include_visits_from_every_project_even_when_one_is_selected(self):
        admin = User(username="global-stats-admin", role=ROLE_ADMIN, password_hash="unused")
        projects = [Project(name="Object A"), Project(name="Object B")]
        db.session.add_all([admin, *projects])
        db.session.flush()
        for index, project in enumerate(projects):
            db.session.add(SiteVisit(
                project_id=project.id,
                ip_address=f"203.0.113.{index + 1}",
                endpoint="main.dashboard",
                path="/",
                method="GET",
                status_code=200,
                is_authenticated=True,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 10, index),
            ))
        db.session.commit()

        with self.app.test_request_context("/developer/statistics?start_date=2026-08-04&end_date=2026-08-04"):
            login_user(admin)
            from flask import session
            session["current_project_id"] = projects[0].id
            context = _build_developer_statistics_context()

        self.assertEqual(context["total_visits"], 2)
        self.assertEqual({item["ip_address"] for item in context["top_ips"]}, {"203.0.113.1", "203.0.113.2"})

    def test_statistics_default_to_last_30_days(self):
        with self.app.test_request_context("/developer/statistics"):
            from app.routes import _developer_statistics_filters
            filters = _developer_statistics_filters()

        self.assertEqual(filters["days"], 30)
        self.assertEqual(filters["period_start_date"], filters["today"] - timedelta(days=29))
        self.assertEqual(filters["period_end_date"], filters["today"])

    def test_developer_pages_show_reports_and_deletion_logs_from_all_projects(self):
        admin = User(username="global-pages-admin", role=ROLE_ADMIN, password_hash="unused")
        projects = [Project(name="Object A"), Project(name="Object B")]
        db.session.add_all([admin, *projects])
        db.session.flush()
        reports = [
            SiteErrorReport(project_id=project.id, message=f"Issue {index}", kind="user", status="new")
            for index, project in enumerate(projects)
        ]
        logs = [
            DeletionActionLog(project_id=project.id, action_key="delete", entity_type="task", entity_title=f"Task {index}")
            for index, project in enumerate(projects)
        ]
        db.session.add_all([*reports, *logs])
        db.session.commit()
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(admin.id)
            session["_fresh"] = True
            session["session_version"] = admin.session_version
            session["current_project_id"] = projects[0].id

        reports_response = client.get("/site-errors")
        logs_response = client.get("/developer/delete-logs")

        self.assertEqual(reports_response.status_code, 200)
        self.assertIn(b"Issue 0", reports_response.data)
        self.assertIn(b"Issue 1", reports_response.data)
        self.assertEqual(logs_response.status_code, 200)
        self.assertIn(b"Task 0", logs_response.data)
        self.assertIn(b"Task 1", logs_response.data)

    def test_user_guest_groups_are_built_from_whole_period_not_only_recent_visits(self):
        active_user = User(username="active", full_name="Активный Пользователь", role=ROLE_ADMIN, password_hash="unused")
        older_user = User(username="older", full_name="Старый Пользователь", role=ROLE_ADMIN, password_hash="unused")
        db.session.add_all([active_user, older_user])
        db.session.flush()

        visits = [
            SiteVisit(
                user=older_user,
                ip_address="203.0.113.50",
                endpoint="main.dashboard",
                path="/",
                method="GET",
                status_code=200,
                is_authenticated=True,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 8, 0),
            )
        ]
        visits.extend(
            SiteVisit(
                user=active_user,
                ip_address="203.0.113.10",
                endpoint="main.dashboard",
                path="/",
                method="GET",
                status_code=200,
                is_authenticated=True,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 10, minute % 60),
            )
            for minute in range(260)
        )
        db.session.add_all(visits)
        db.session.commit()

        with self.app.test_request_context("/developer/statistics/visits?start_date=2026-08-04&end_date=2026-08-04"):
            context = _build_developer_statistics_context()

        labels = [group["label"] for group in context["visitor_groups"]]
        self.assertIn("Активный Пользователь", labels)
        self.assertIn("Старый Пользователь", labels)

    def test_user_guest_groups_and_sources_are_sorted_by_latest_visit_first(self):
        frequent_user = User(username="frequent", full_name="Частый Пользователь", role=ROLE_ADMIN, password_hash="unused")
        fresh_user = User(username="fresh", full_name="Свежий Пользователь", role=ROLE_ADMIN, password_hash="unused")
        db.session.add_all([frequent_user, fresh_user])
        db.session.flush()

        visits = [
            SiteVisit(
                user=frequent_user,
                ip_address="203.0.113.20",
                endpoint="main.dashboard",
                path="/",
                method="GET",
                status_code=200,
                is_authenticated=True,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 9, minute),
            )
            for minute in range(10)
        ]
        visits.append(
            SiteVisit(
                user=fresh_user,
                ip_address="203.0.113.99",
                endpoint="main.dashboard",
                path="/",
                method="GET",
                status_code=200,
                is_authenticated=True,
                visit_kind="request",
                created_at=datetime(2026, 8, 4, 11, 0),
            )
        )
        db.session.add_all(visits)
        db.session.commit()

        with self.app.test_request_context("/developer/statistics/visits?start_date=2026-08-04&end_date=2026-08-04"):
            context = _build_developer_statistics_context()

        self.assertEqual(context["visitor_groups"][0]["label"], "Свежий Пользователь")
        self.assertEqual(context["top_ips"][0]["ip_address"], "203.0.113.99")

    def test_authorized_badge_is_used_only_for_current_account_activity(self):
        user = User(username="badge-user", full_name="Пользователь", role=ROLE_ADMIN, password_hash="unused")
        db.session.add(user)
        db.session.flush()
        now = datetime(2026, 8, 4, 12, 0)
        old_visit = SiteVisit(
            user=user,
            user_id=user.id,
            ip_address="203.0.113.10",
            endpoint="main.dashboard",
            path="/",
            method="GET",
            status_code=200,
            is_authenticated=True,
            visit_kind="request",
            created_at=datetime(2026, 8, 4, 10, 0),
        )
        fresh_visit = SiteVisit(
            user=user,
            user_id=user.id,
            ip_address="203.0.113.10",
            endpoint="main.dashboard",
            path="/",
            method="GET",
            status_code=200,
            is_authenticated=True,
            visit_kind="request",
            created_at=datetime(2026, 8, 4, 11, 55),
        )

        old_group = _build_site_visit_visitor_groups([old_visit], now=now)[0]
        fresh_group = _build_site_visit_visitor_groups([fresh_visit], now=now)[0]

        self.assertEqual(old_group["kind_label"], "Не авторизован")
        self.assertEqual(fresh_group["kind_label"], "Авторизован")

    def test_request_visit_is_persisted_before_response_returns(self):
        client = self.app.test_client()

        response = client.get(
            "/login",
            environ_base={"REMOTE_ADDR": "198.51.100.44"},
            headers={"User-Agent": "StatsPersistenceTest/1.0"},
        )

        self.assertEqual(response.status_code, 200)
        visit = SiteVisit.query.filter_by(ip_address="198.51.100.44", visit_kind="request").one()
        self.assertEqual(visit.path, "/login")
        self.assertFalse(visit.is_authenticated)


if __name__ == "__main__":
    unittest.main()
