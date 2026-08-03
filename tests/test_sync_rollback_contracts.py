from datetime import datetime, timedelta
import json
import unittest

from config import Config
from app import create_app, db
from app.models import Apartment, ChangeLog, Project, SyncConflict, SyncLog, Task, WorkPoint
from app.services.sync_rollback import (
    build_project_rollback_data,
    _deserialize_value,
    _reserve_database_source_uid,
    _snapshot_payload,
    _source_uid_variant,
    apply_sync_rollback,
)
from app.time_utils import utc_now


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "sync-rollback-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class SyncRollbackContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.project = Project(name="Rollback contracts QA")
        self.apartment = Apartment(project=self.project, apartment_number="1")
        self.point = WorkPoint(point_number="10")
        self.task = Task(source_uid="rollback-contract-task", project=self.project, apartment=self.apartment, work_point=self.point)
        db.session.add_all([self.project, self.apartment, self.point, self.task])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_snapshot_payload_rejects_missing_invalid_and_non_object_json(self):
        self.assertEqual(_snapshot_payload(None), {})
        self.assertEqual(_snapshot_payload(SyncLog(rollback_data="not-json")), {})
        self.assertEqual(_snapshot_payload(SyncLog(rollback_data="[]")), {})
        self.assertEqual(_snapshot_payload(SyncLog(rollback_data='{"version":1}')), {"version": 1})

    def test_build_project_rollback_data_records_naive_utc_timestamp(self):
        payload = json.loads(build_project_rollback_data(self.project.id))

        self.assertIn("created_at_utc", payload)
        self.assertIsNone(datetime.fromisoformat(payload["created_at_utc"]).tzinfo)

    def test_deserialize_value_restores_dates_datetimes_and_handles_bad_values_safely(self):
        self.assertEqual(_deserialize_value("deadline_date", "2026-07-29"), datetime(2026, 7, 29).date())
        self.assertEqual(_deserialize_value("completed_date", "2026-07-29T12:30:00"), datetime(2026, 7, 29, 12, 30))
        self.assertIsNone(_deserialize_value("deadline_date", "not-a-date"))
        self.assertIsNone(_deserialize_value("completed_date", "not-a-datetime"))
        self.assertEqual(_deserialize_value("description", ""), "")

    def test_source_uid_helpers_preserve_length_and_avoid_database_collisions(self):
        long_uid = "x" * 100
        self.assertLessEqual(len(_source_uid_variant(long_uid, 3)), 64)

        reserved = set()
        reserved_uid = _reserve_database_source_uid(self.task.source_uid, reserved)

        self.assertNotEqual(reserved_uid, self.task.source_uid)
        self.assertIn(reserved_uid, reserved)
        self.assertLessEqual(len(reserved_uid), 64)

    def test_apply_sync_rollback_rejects_already_rolled_back_and_corrupt_snapshot_logs(self):
        already = SyncLog(
            project=self.project,
            source_type="excel",
            status="success",
            started_at=utc_now(),
            rolled_back_at=utc_now(),
            rollback_data=json.dumps({"version": 1, "project_id": self.project.id}),
        )
        corrupt = SyncLog(
            project=self.project,
            source_type="excel",
            status="success",
            started_at=utc_now(),
            rollback_data="not-json",
        )
        db.session.add_all([already, corrupt])
        db.session.commit()

        already_ok, already_message = apply_sync_rollback(already)
        corrupt_ok, corrupt_message = apply_sync_rollback(corrupt)

        self.assertFalse(already_ok)
        self.assertIn("уже", already_message)
        self.assertFalse(corrupt_ok)
        self.assertIn("повреждены", corrupt_message)

    def test_legacy_rollback_without_snapshot_reverts_missing_flags_and_deletes_created_tasks(self):
        started_at = utc_now()
        log = SyncLog(
            project=self.project,
            source_type="excel",
            status="success",
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=3),
        )
        created_task = Task(
            source_uid="legacy-created",
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            created_at=started_at + timedelta(seconds=1),
        )
        self.task.is_missing_in_latest_sync = True
        db.session.add_all([
            log,
            created_task,
            ChangeLog(task=created_task, action="created_from_sync", created_at=started_at + timedelta(seconds=1)),
            ChangeLog(
                task=self.task,
                action="missing_in_latest_sync",
                field_name="is_missing_in_latest_sync",
                old_value="False",
                new_value="True",
                created_at=started_at + timedelta(seconds=2),
            ),
        ])
        db.session.commit()
        created_task_id = created_task.id

        ok, message = apply_sync_rollback(log)

        self.assertTrue(ok, message)
        self.assertIsNone(db.session.get(Task, created_task_id))
        self.assertFalse(db.session.get(Task, self.task.id).is_missing_in_latest_sync)
        self.assertIsNotNone(log.rolled_back_at)

    def test_rollback_conflict_query_only_closes_conflicts_for_selected_project_window(self):
        rollback_data = json.dumps({
            "version": 1,
            "project_id": self.project.id,
            "apartments": [],
            "tasks": [],
        })
        started_at = utc_now()
        log = SyncLog(project=self.project, source_type="excel", status="success", started_at=started_at, rollback_data=rollback_data)
        in_window = SyncConflict(
            task=self.task,
            target_type="task",
            source_type="excel",
            status="pending",
            created_at=started_at + timedelta(seconds=1),
        )
        before_window = SyncConflict(
            task=self.task,
            target_type="task",
            source_type="excel",
            status="pending",
            created_at=started_at - timedelta(seconds=10),
        )
        db.session.add_all([log, in_window, before_window])
        db.session.commit()
        before_id = before_window.id

        ok, message = apply_sync_rollback(log)

        self.assertTrue(ok, message)
        self.assertIsNone(db.session.get(SyncConflict, in_window.id))
        self.assertIsNotNone(db.session.get(SyncConflict, before_id))


if __name__ == "__main__":
    unittest.main()
