from datetime import datetime, timedelta
import unittest

from config import Config
from app import create_app, db
from app.models import Apartment, Project, SyncLog, Task, WorkPoint
from app.services.sync_rollback import apply_sync_rollback, build_project_rollback_data


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "sync-rollback-snapshot-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class SyncRollbackSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.project = Project(name="Rollback QA")
        self.work_point = WorkPoint(point_number="QA", source_sheet_name="qa")
        self.apartment = Apartment(project=self.project, apartment_number="101")
        self.existing_task = Task(
            source_uid="rollback-existing-task",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Original remark",
            source_cell_value="Original remark",
        )
        db.session.add_all([self.project, self.work_point])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_snapshot_rollback_removes_records_added_after_sync_started(self):
        rollback_data = build_project_rollback_data(self.project.id)
        started_at = datetime.utcnow()

        self.existing_task.description = "Changed by sync"
        same_apartment_new_task = Task(
            source_uid="rollback-new-task-same-apartment",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="New remark in existing apartment",
            source_cell_value="New remark in existing apartment",
        )
        new_apartment = Apartment(project=self.project, apartment_number="202")
        new_apartment_task = Task(
            source_uid="rollback-new-task-new-apartment",
            project=self.project,
            apartment=new_apartment,
            work_point=self.work_point,
            description="New remark in new apartment",
            source_cell_value="New remark in new apartment",
        )
        sync_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="rollback-test.xlsx",
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=2),
            status="success",
            rollback_data=rollback_data,
            created_count=2,
            updated_count=1,
        )
        db.session.add_all([same_apartment_new_task, new_apartment, new_apartment_task, sync_log])
        db.session.commit()

        same_apartment_new_task_id = same_apartment_new_task.id
        new_apartment_id = new_apartment.id
        new_apartment_task_id = new_apartment_task.id
        existing_task_id = self.existing_task.id

        ok, message = apply_sync_rollback(sync_log)

        self.assertTrue(ok, message)
        restored_task = db.session.get(Task, existing_task_id)
        self.assertIsNotNone(restored_task)
        self.assertEqual(restored_task.description, "Original remark")
        self.assertEqual(restored_task.source_cell_value, "Original remark")
        self.assertIsNone(db.session.get(Task, same_apartment_new_task_id))
        self.assertIsNone(db.session.get(Task, new_apartment_task_id))
        self.assertIsNone(db.session.get(Apartment, new_apartment_id))
        self.assertIsNotNone(sync_log.rolled_back_at)


if __name__ == "__main__":
    unittest.main()
