from datetime import date, timedelta
import unittest

from config import Config
from app import create_app, db
from app.models import Apartment, Project, STATUS_DONE, STATUS_NOT_STARTED, Task, WorkPoint
from app.services.apartment_overview import (
    apartment_all_tasks,
    apartment_main_tasks,
    apartment_sort_key,
    apartment_stats,
    build_60kd_rows,
    build_po_rows,
    build_primary_rows,
    deadline_marker,
    notification_counts,
    task_sort_key,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "apartment-overview-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ApartmentOverviewContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.project = Project(name="Apartment overview QA")
        self.wall_point = WorkPoint(point_number="11", short_name="Wall")
        self.floor_point = WorkPoint(point_number="12", short_name="Floor")
        self.external_point = WorkPoint(point_number="30", short_name="External")
        db.session.add_all([self.project, self.wall_point, self.floor_point, self.external_point])
        db.session.flush()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _apartment(self, number: str, **kwargs) -> Apartment:
        apartment = Apartment(project=self.project, apartment_number=number, **kwargs)
        db.session.add(apartment)
        db.session.flush()
        return apartment

    def _task(self, apartment: Apartment, point: WorkPoint, uid: str, *, done: bool = False, description: str = "Task") -> Task:
        task = Task(
            source_uid=uid,
            project=self.project,
            apartment=apartment,
            work_point=point,
            description=description,
            status=STATUS_DONE if done else STATUS_NOT_STARTED,
            is_done=done,
        )
        db.session.add(task)
        db.session.flush()
        return task

    def test_sort_keys_order_numeric_apartments_and_done_tasks_last(self):
        self.assertLess(apartment_sort_key(Apartment(apartment_number="9")), apartment_sort_key(Apartment(apartment_number="10")))

        open_floor = Task(work_point=self.floor_point, description="B", is_done=False)
        done_wall = Task(work_point=self.wall_point, description="A", is_done=True)
        open_wall = Task(work_point=self.wall_point, description="A", is_done=False)

        self.assertEqual(sorted([open_floor, done_wall, open_wall], key=task_sort_key), [open_wall, open_floor, done_wall])

    def test_apartment_main_tasks_exclude_archived_external_and_empty_tasks(self):
        apartment = self._apartment("1")
        main = self._task(apartment, self.wall_point, "main", description="Main defect")
        self._task(apartment, self.external_point, "external", description="External defect")
        self._task(apartment, self.floor_point, "empty", description="")
        archived = self._task(apartment, self.floor_point, "archived", description="Archived")
        archived.is_archived = True
        db.session.commit()

        self.assertEqual(apartment_main_tasks(apartment), [main])
        self.assertEqual([task.source_uid for task in apartment_all_tasks(apartment)], ["main", "external"])

    def test_apartment_stats_reports_done_left_and_percent(self):
        apartment = self._apartment("2")
        tasks = [
            self._task(apartment, self.wall_point, "stats-done", done=True),
            self._task(apartment, self.floor_point, "stats-open", done=False),
        ]

        self.assertEqual(apartment_stats(apartment, tasks), {"total": 2, "done": 1, "left": 1, "percent": 50.0})
        self.assertEqual(apartment_stats(apartment, []), {"total": 0, "done": 0, "left": 0, "percent": 0})

    def test_deadline_marker_uses_deterministic_boundaries(self):
        today = date(2026, 7, 29)
        self.assertIsNone(deadline_marker(Apartment(deadline_date=None), today=today))
        self.assertEqual(deadline_marker(Apartment(deadline_date=today + timedelta(days=4)), today=today)["code"], "expired")
        self.assertEqual(deadline_marker(Apartment(deadline_date=today + timedelta(days=5)), today=today)["code"], "expiring")
        self.assertEqual(deadline_marker(Apartment(deadline_date=today + timedelta(days=15)), today=today)["code"], "expiring")
        self.assertIsNone(deadline_marker(Apartment(deadline_date=today + timedelta(days=16)), today=today))

    def test_po_rows_include_waiting_apartments_with_wall_done_or_more_than_60_percent_ready(self):
        wall_ready = self._apartment("3", deadline_date=None)
        self._task(wall_ready, self.wall_point, "po-wall", done=True)

        percent_ready = self._apartment("4", deadline_date=None)
        self._task(percent_ready, self.wall_point, "po-a", done=True)
        self._task(percent_ready, self.floor_point, "po-b", done=True)
        self._task(percent_ready, self.floor_point, "po-c", done=False)

        not_ready = self._apartment("5", deadline_date=None)
        self._task(not_ready, self.wall_point, "po-not-a", done=False)
        self._task(not_ready, self.floor_point, "po-not-b", done=True)

        accepted = self._apartment("6", deadline_date=date(2026, 8, 1))
        self._task(accepted, self.wall_point, "po-accepted", done=True)
        db.session.commit()

        rows = build_po_rows(self.project.id)

        self.assertEqual([row["apartment"].apartment_number for row in rows], ["3", "4"])
        self.assertEqual([row["stats"]["percent"] for row in rows], [100.0, 66.7])

    def test_primary_rows_exclude_unsold_and_split_active_from_archived(self):
        active = self._apartment("7", owner_name="Owner")
        accepted = self._apartment("8", owner_name="Owner", deadline_date=date(2026, 8, 1))
        with_tasks = self._apartment("9", owner_name="Owner")
        self._task(with_tasks, self.wall_point, "primary-task")
        unsold = self._apartment("10", owner_name="", is_unsold=True)
        db.session.commit()

        active_rows = build_primary_rows(self.project.id, archived=False)
        archived_rows = build_primary_rows(self.project.id, archived=True)

        self.assertEqual([row["apartment"] for row in active_rows], [active])
        self.assertEqual({row["apartment"] for row in archived_rows}, {accepted, with_tasks})
        self.assertNotIn(unsold, [row["apartment"] for row in active_rows + archived_rows])

    def test_kd60_rows_sort_by_deadline_and_notifications_count_visible_risks(self):
        soon = self._apartment("11", deadline_date=date.today() + timedelta(days=3), owner_name="Owner")
        later = self._apartment("12", deadline_date=date.today() + timedelta(days=20), owner_name="Owner")
        primary = self._apartment("13", owner_name="Owner")
        for apartment, uid in [(later, "kd-later"), (soon, "kd-soon")]:
            self._task(apartment, self.wall_point, uid)
        db.session.commit()

        kd_rows = build_60kd_rows(self.project.id)
        counts = notification_counts(self.project.id)

        self.assertEqual([row["apartment"] for row in kd_rows], [soon, later])
        self.assertEqual(counts, {"kd60": 1, "primary": 1})
        self.assertEqual(notification_counts(None), {"kd60": 0, "primary": 0})


if __name__ == "__main__":
    unittest.main()
