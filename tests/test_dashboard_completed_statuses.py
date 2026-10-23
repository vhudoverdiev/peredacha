import re
import unittest
from datetime import date

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
from app.services.task_service import APP_DEADLINE_NO_REMARKS
from app.routes import _apartment_inspection_status


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
                description=f"Terminal report task {status}",
                status=status,
                is_done=status in {
                    STATUS_DONE,
                    STATUS_FINISHERS,
                    STATUS_CONTRACTOR,
                    STATUS_GUARANTEE,
                    STATUS_CONCESSION,
                },
                completed_date=date.today() if status in {
                    STATUS_DONE,
                    STATUS_FINISHERS,
                    STATUS_CONTRACTOR,
                    STATUS_GUARANTEE,
                    STATUS_CONCESSION,
                } else None,
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

    def test_dashboard_accepted_heading_matches_inspections_and_completed_storeroom_feature_is_removed(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertEqual(
            html.count('class="dashboard-info-title dashboard-soft-section-title"'),
            3,
        )
        self.assertRegex(
            html,
            r'class="dashboard-info-title dashboard-soft-section-title"><i class="bi bi-eye"></i>\s*Осмотры</div>',
        )
        self.assertRegex(
            html,
            r'class="dashboard-info-title dashboard-soft-section-title">\s*<i class="bi bi-check2-circle"></i>\s*Принято',
        )
        accepted_card = re.search(
            r'<article class="dashboard-info-card">\s*<div class="dashboard-info-title dashboard-soft-section-title">\s*<i class="bi bi-check2-circle"></i>\s*Принято.*?</article>',
            html,
            re.DOTALL,
        )
        inspections_card = re.search(
            r'<article class="dashboard-info-card">\s*<div class="dashboard-info-title dashboard-soft-section-title"><i class="bi bi-eye"></i>\s*Осмотры</div>.*?</article>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(accepted_card)
        self.assertIsNotNone(inspections_card)
        self.assertNotIn("Принято", inspections_card.group(0))
        self.assertEqual(accepted_card.group(0).count("dashboard-info-card"), 1)
        self.assertNotIn("Добавление объектов с кладовками", html)
        self.assertNotIn("Что скоро станет доступно?", html)
        self.assertNotIn("dashboardRoadmapModal", html)
        self.assertNotIn("dashboard-roadmap-mini-card", html)

    def test_accepted_apartment_count_excludes_other_premises(self):
        self.apartment.is_app_mode=True
        for premise_type in ('storeroom','parking','commercial'):
            db.session.add(Apartment(project=self.project,apartment_number=f'{premise_type}-1',premise_type=premise_type,is_app_mode=True))
        db.session.add(Apartment(project=self.project,apartment_number='2',premise_type='apartment',is_app_mode=True,app_deadline_status=APP_DEADLINE_NO_REMARKS))
        db.session.commit()
        stats=dashboard_stats(self.project.id)
        self.assertEqual(stats['accepted_apartment_count'],2)
        self.assertGreater(stats['accepted'],2)
        from app.routes import project_stats
        self.assertEqual(project_stats(self.project)['transferred'],2)

    def test_dashboard_shows_unaccepted_storerooms_separately_from_unsold_ones(self):
        self.project.has_storerooms = True
        accepted = Apartment(
            project=self.project,
            apartment_number="КЛ1",
            premise_type="storeroom",
            is_app_mode=True,
            app_deadline_status="normal",
        )
        waiting = Apartment(project=self.project, apartment_number="КЛ2", premise_type="storeroom")
        unsold = Apartment(project=self.project, apartment_number="КЛ3", premise_type="storeroom", is_unsold=True)
        db.session.add_all([accepted, waiting, unsold])
        db.session.commit()

        stats = dashboard_stats(self.project.id)
        response = self.client.get("/")

        self.assertEqual(stats["not_accepted_storeroom_count"], 1)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Кладовок не принято</span><b>1</b>", response.get_data(as_text=True))

    def test_dashboard_breaks_inspection_counts_down_by_premise_type(self):
        self.project.has_storerooms = True
        self.project.has_parking = True
        self.project.has_commercial = True
        visited_apartment = Apartment(
            project=self.project,
            apartment_number="2",
            first_inspection_present=True,
        )
        visited_storeroom = Apartment(
            project=self.project,
            apartment_number="КЛ1",
            premise_type="storeroom",
            first_inspection_present=True,
        )
        unvisited_parking = Apartment(
            project=self.project,
            apartment_number="М1",
            premise_type="parking",
            first_inspection_present=False,
        )
        unvisited_commercial = Apartment(
            project=self.project,
            apartment_number="К1",
            premise_type="commercial",
            first_inspection_present=False,
        )
        unsold_visited_commercial = Apartment(
            project=self.project,
            apartment_number="К2",
            premise_type="commercial",
            is_unsold=True,
            first_inspection_present=True,
        )
        db.session.add_all([
            visited_apartment,
            visited_storeroom,
            unvisited_parking,
            unvisited_commercial,
            unsold_visited_commercial,
        ])
        db.session.commit()

        stats = dashboard_stats(self.project.id)
        self.assertEqual(stats["inspection_by_type"]["apartment"], {"inspected": 1, "not_inspected": 1})
        self.assertEqual(stats["inspection_by_type"]["storeroom"], {"inspected": 1, "not_inspected": 0})
        self.assertEqual(stats["inspection_by_type"]["parking"], {"inspected": 0, "not_inspected": 1})
        self.assertEqual(stats["inspection_by_type"]["commercial"], {"inspected": 0, "not_inspected": 1})

        response = self.client.get("/")
        html = response.get_data(as_text=True)
        inspections_card = re.search(
            r'<article class="dashboard-info-card">\s*<div class="dashboard-info-title dashboard-soft-section-title"><i class="bi bi-eye"></i>\s*Осмотры</div>.*?</article>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(inspections_card)
        self.assertIn("Квартир были на осмотре", inspections_card.group(0))
        self.assertIn("Кладовок не были на осмотре", inspections_card.group(0))
        self.assertIn("Парковок были на осмотре", inspections_card.group(0))
        self.assertIn("Коммерций не были на осмотре", inspections_card.group(0))

    def test_apartment_detail_mode_change_updates_dashboard_transfer_stats(self):
        before = dashboard_stats(self.project.id)
        self.assertEqual(before["accepted"], 0)
        self.assertEqual(before["not_accepted"], 1)

        response = self.client.post(
            f"/apartments/{self.apartment.id}/details",
            data={
                "owner_name": self.apartment.owner_name or "",
                "phone": self.apartment.phone or "",
                "finishing_type": self.apartment.finishing_type or "",
                "mode": "app",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.apartment)
        self.assertTrue(self.apartment.is_app_mode)
        self.assertFalse(self.apartment.is_unsold)

        after = dashboard_stats(self.project.id)
        self.assertEqual(after["accepted"], 1)
        self.assertEqual(after["not_accepted"], 0)
        self.assertEqual(after["accepted_with_remarks"], 1)
        self.assertEqual(after["accepted_no_remarks"], 0)

        self.apartment.app_deadline_status = APP_DEADLINE_NO_REMARKS
        db.session.commit()

        no_remarks = dashboard_stats(self.project.id)
        self.assertEqual(no_remarks["accepted_with_remarks"], 0)
        self.assertEqual(no_remarks["accepted_no_remarks"], 1)

    def test_apartment_detail_autosave_returns_json_without_redirect(self):
        response = self.client.post(
            f"/apartments/{self.apartment.id}/details",
            data={
                "owner_name": "Иванов Иван",
                "phone": "8 900 000-00-00",
                "finishing_type": "Белая",
                "mode": "not_accepted",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["owner_name"], "Иванов Иван")
        self.assertEqual(payload["phone"], "8 900 000-00-00")
        self.assertEqual(payload["finishing_type"], "Белая")
        db.session.refresh(self.apartment)
        self.assertEqual(self.apartment.owner_name, "Иванов Иван")
        self.assertEqual(self.apartment.phone, "8 900 000-00-00")
        self.assertEqual(self.apartment.finishing_type, "Белая")

    def test_unsold_apartments_do_not_count_as_not_inspected_or_not_accepted(self):
        unsold = Apartment(
            project=self.project,
            apartment_number="2",
            owner_name="не продано",
            is_unsold=True,
            first_inspection_present=False,
        )
        db.session.add(unsold)
        db.session.commit()

        stats = dashboard_stats(self.project.id)

        self.assertEqual(stats["apartments"], 2)
        self.assertEqual(stats["unsold"], 1)
        self.assertEqual(stats["not_accepted"], 1)
        self.assertEqual(stats["not_inspected"], 1)

    def test_accepted_and_remarks_inspection_dates_count_as_inspected_by_type(self):
        self.project.has_storerooms = True
        accepted_storeroom = Apartment(
            project=self.project,
            apartment_number="КЛ1",
            premise_type="storeroom",
            is_app_mode=True,
        )
        dated_storeroom = Apartment(
            project=self.project,
            apartment_number="КЛ2",
            premise_type="storeroom",
            inspection_date=date(2026, 9, 15),
        )
        waiting_storeroom = Apartment(
            project=self.project,
            apartment_number="КЛ3",
            premise_type="storeroom",
        )
        db.session.add_all([accepted_storeroom, dated_storeroom, waiting_storeroom])
        db.session.commit()

        stats = dashboard_stats(self.project.id)

        self.assertEqual(stats["inspection_by_type"]["storeroom"], {"inspected": 2, "not_inspected": 1})

    def test_dashboard_stats_refresh_from_latest_persisted_crm_fields(self):
        initial = dashboard_stats(self.project.id)
        self.assertEqual(initial["accepted"], 0)
        self.assertEqual(initial["inspection_by_type"]["apartment"], {"inspected": 0, "not_inspected": 1})

        self.apartment.is_app_mode = True
        self.apartment.first_inspection_present = True
        db.session.commit()

        updated = dashboard_stats(self.project.id)
        self.assertEqual(updated["accepted"], 1)
        self.assertEqual(updated["accepted_with_remarks_apartment"], 1)
        self.assertEqual(updated["inspection_by_type"]["apartment"], {"inspected": 1, "not_inspected": 0})

        self.apartment.is_app_mode = False
        self.apartment.first_inspection_present = False
        self.apartment.inspection_date = None
        self.apartment.first_inspection_date = None
        db.session.commit()

        current = dashboard_stats(self.project.id)
        self.assertEqual(current["accepted"], 0)
        self.assertEqual(current["accepted_with_remarks_apartment"], 0)
        self.assertEqual(current["inspection_by_type"]["apartment"], {"inspected": 0, "not_inspected": 1})

    def test_unsold_apartment_inspection_status_is_unsold_label(self):
        unsold = Apartment(
            project=self.project,
            apartment_number="2",
            owner_name="не продано",
            is_unsold=True,
            first_inspection_present=False,
        )

        self.assertEqual(_apartment_inspection_status([unsold]), "не продана")

    def test_unsold_marker_is_cleared_when_mode_changes_to_not_accepted(self):
        self.apartment.owner_name = "не продано"
        self.apartment.is_unsold = True
        db.session.commit()

        response = self.client.post(
            f"/apartments/{self.apartment.id}/details",
            data={
                "owner_name": "не продано",
                "phone": "",
                "finishing_type": self.apartment.finishing_type or "",
                "mode": "not_accepted",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.apartment)
        self.assertFalse(self.apartment.is_unsold)
        self.assertFalse(self.apartment.is_app_mode)
        self.assertIsNone(self.apartment.owner_name)

    def test_work_report_includes_all_terminal_workflow_statuses(self):
        response = self.client.get("/report")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<span class="stat-badge stat-badge-white">5</span>', html)
        self.assertIn("Terminal report task finishers", html)
        self.assertIn("Terminal report task contractor", html)
        self.assertIn("Terminal report task guarantee", html)


if __name__ == "__main__":
    unittest.main()
