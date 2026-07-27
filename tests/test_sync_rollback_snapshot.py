from datetime import datetime, timedelta
import unittest

from config import Config
from app import create_app, db
from app.models import Apartment, Project, STATUS_DONE, STATUS_NOT_STARTED, SyncLog, Task, WorkPoint
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

    def test_snapshot_rollback_to_older_sync_uses_next_presync_snapshot(self):
        first_snapshot = build_project_rollback_data(self.project.id)
        first_started_at = datetime.utcnow()
        first_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="sync-1.xlsx",
            started_at=first_started_at,
            finished_at=first_started_at + timedelta(seconds=2),
            status="success",
            rollback_data=first_snapshot,
        )
        sync_one_task = Task(
            source_uid="rollback-sync-one-task",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Remark from sync one",
            source_cell_value="Remark from sync one",
        )
        db.session.add_all([first_log, sync_one_task])
        db.session.commit()

        sync_one_task.status = STATUS_DONE
        sync_one_task.is_done = True
        sync_one_task.comment = "Manual state before sync two"
        self.existing_task.comment = "Manual note before sync two"
        db.session.commit()

        second_snapshot = build_project_rollback_data(self.project.id)
        second_started_at = first_started_at + timedelta(days=2)
        second_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="sync-2.xlsx",
            started_at=second_started_at,
            finished_at=second_started_at + timedelta(seconds=2),
            status="success",
            rollback_data=second_snapshot,
        )
        sync_two_task = Task(
            source_uid="rollback-sync-two-task",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Remark from sync two",
            source_cell_value="Remark from sync two",
        )
        sync_one_task.status = STATUS_NOT_STARTED
        sync_one_task.is_done = False
        sync_one_task.comment = None
        self.existing_task.comment = None
        db.session.add_all([second_log, sync_two_task])
        db.session.commit()

        sync_one_task_id = sync_one_task.id
        sync_two_task_id = sync_two_task.id
        existing_task_id = self.existing_task.id

        ok, message = apply_sync_rollback(first_log)

        self.assertTrue(ok, message)
        restored_sync_one_task = db.session.get(Task, sync_one_task_id)
        self.assertIsNotNone(restored_sync_one_task)
        self.assertEqual(restored_sync_one_task.status, STATUS_DONE)
        self.assertTrue(restored_sync_one_task.is_done)
        self.assertEqual(restored_sync_one_task.comment, "Manual state before sync two")
        restored_existing_task = db.session.get(Task, existing_task_id)
        self.assertEqual(restored_existing_task.comment, "Manual note before sync two")
        self.assertIsNone(db.session.get(Task, sync_two_task_id))
        self.assertIsNotNone(first_log.rolled_back_at)

    def test_snapshot_rollback_restores_source_uid_after_same_project_uid_move(self):
        sibling = Task(
            source_uid="rollback-sibling-original",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Sibling before sync",
            source_cell_value="Sibling before sync",
        )
        db.session.add(sibling)
        db.session.commit()

        existing_task_id = self.existing_task.id
        sibling_id = sibling.id
        original_existing_uid = self.existing_task.source_uid
        original_sibling_uid = sibling.source_uid
        rollback_data = build_project_rollback_data(self.project.id)
        started_at = datetime.utcnow()

        self.existing_task.source_uid = "rollback-existing-moved-away"
        db.session.flush()
        sibling.source_uid = original_existing_uid
        sync_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="uid-move.xlsx",
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=2),
            status="success",
            rollback_data=rollback_data,
        )
        db.session.add(sync_log)
        db.session.commit()

        ok, message = apply_sync_rollback(sync_log)

        self.assertTrue(ok, message)
        restored_existing = db.session.get(Task, existing_task_id)
        restored_sibling = db.session.get(Task, sibling_id)
        self.assertEqual(restored_existing.source_uid, original_existing_uid)
        self.assertEqual(restored_sibling.source_uid, original_sibling_uid)

    def test_snapshot_rollback_does_not_crash_when_source_uid_is_used_by_other_project(self):
        original_existing_uid = self.existing_task.source_uid
        rollback_data = build_project_rollback_data(self.project.id)
        started_at = datetime.utcnow()

        other_project = Project(name="Other rollback QA")
        other_apartment = Apartment(project=other_project, apartment_number="999")
        self.existing_task.source_uid = "rollback-existing-cross-project-current"
        db.session.flush()
        other_task = Task(
            source_uid=original_existing_uid,
            project=other_project,
            apartment=other_apartment,
            work_point=self.work_point,
            description="Other project blocker",
            source_cell_value="Other project blocker",
        )
        db.session.add_all([other_project, other_apartment, other_task])
        sync_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="uid-cross-project.xlsx",
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=2),
            status="success",
            rollback_data=rollback_data,
        )
        db.session.add(sync_log)
        db.session.commit()

        ok, message = apply_sync_rollback(sync_log)

        self.assertTrue(ok, message)
        restored_existing = db.session.get(Task, self.existing_task.id)
        self.assertNotEqual(restored_existing.source_uid, original_existing_uid)
        self.assertTrue(restored_existing.source_uid.startswith("rbuid-"))
        self.assertEqual(db.session.get(Task, other_task.id).source_uid, original_existing_uid)

    def test_snapshot_rollback_resplits_restored_compound_tasks_but_not_dop_agreement(self):
        normal_point = WorkPoint(point_number="NORMAL", source_sheet_name="qa")
        dop_point = WorkPoint(
            point_number="DOP",
            original_column_name="Отступное ТМЦ",
            source_sheet_name="qa",
        )
        normal_task = Task(
            source_uid="rollback-compound-normal",
            project=self.project,
            apartment=self.apartment,
            work_point=normal_point,
            description="Первое длинное замечание. Второе длинное замечание",
            source_cell_value="Первое длинное замечание. Второе длинное замечание",
        )
        dop_task = Task(
            source_uid="rollback-compound-dop",
            project=self.project,
            apartment=self.apartment,
            work_point=dop_point,
            description="Отступное первое замечание. Отступное второе замечание",
            source_cell_value="Отступное первое замечание. Отступное второе замечание",
        )
        db.session.add_all([normal_point, dop_point, normal_task, dop_task])
        db.session.commit()

        rollback_data = build_project_rollback_data(self.project.id)
        started_at = datetime.utcnow()
        normal_task.description = "Changed by failed sync"
        normal_task.source_cell_value = "Changed by failed sync"
        dop_task.description = "Changed by failed sync"
        dop_task.source_cell_value = "Changed by failed sync"
        sync_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="compound-rollback.xlsx",
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=2),
            status="success",
            rollback_data=rollback_data,
        )
        db.session.add(sync_log)
        db.session.commit()

        ok, message = apply_sync_rollback(sync_log)

        self.assertTrue(ok, message)
        normal_descriptions = sorted(
            task.description
            for task in Task.query.filter_by(project_id=self.project.id, work_point_id=normal_point.id).all()
        )
        self.assertEqual(normal_descriptions, ["Второе длинное замечание", "Первое длинное замечание."])
        dop_tasks = Task.query.filter_by(project_id=self.project.id, work_point_id=dop_point.id).all()
        self.assertEqual(len(dop_tasks), 1)
        self.assertEqual(
            dop_tasks[0].description,
            "Отступное первое замечание. Отступное второе замечание",
        )


if __name__ == "__main__":
    unittest.main()
