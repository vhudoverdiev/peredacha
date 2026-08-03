from datetime import timedelta
import unittest

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, SyncConflict, SyncLog, Task, User, WorkPoint
from app.services.sync_rollback import build_project_rollback_data
from app.time_utils import utc_now


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "sync-conflicts-cancel-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class SyncConflictsCancelTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

        self.project = Project(name="Квартал 100-7")
        self.user = User(
            username="sync-admin",
            password_hash="unused",
            role=ROLE_ADMIN,
            all_projects_access=True,
        )
        self.work_point = WorkPoint(point_number="1", source_sheet_name="Замечания")
        self.apartment = Apartment(project=self.project, apartment_number="145")
        self.task = Task(
            source_uid="sync-conflict-cancel-original",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Старое замечание",
            source_cell_value="Старое замечание",
        )
        db.session.add_all([self.project, self.user, self.work_point])
        db.session.commit()

        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
            session["_id"] = "sync-conflicts-cancel-session"
            session["session_version"] = int(self.user.session_version or 0)
            session["current_project_id"] = self.project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_conflicts_page_has_cancel_sync_button(self):
        started_at = utc_now()
        conflict = SyncConflict(
            task=self.task,
            target_type="task",
            field_name="description",
            source_type="excel",
            old_value="Старое замечание",
            new_value="Новое замечание",
            status="pending",
            created_at=started_at + timedelta(seconds=1),
        )
        db.session.add(conflict)
        db.session.commit()

        response = self.client.get("/conflicts")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("/conflicts/cancel-sync", body)
        self.assertIn("Отменить синхронизацию", body)

    def test_cancel_sync_from_conflicts_rolls_back_snapshot_and_closes_pending_conflicts(self):
        rollback_data = build_project_rollback_data(self.project.id)
        started_at = utc_now()
        sync_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="100_7.xlsx",
            status="success",
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=2),
            rollback_data=rollback_data,
        )
        self.task.description = "Новое замечание из синхронизации"
        self.task.source_cell_value = "Новое замечание из синхронизации"
        new_task = Task(
            source_uid="sync-conflict-cancel-new",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Новая строка из синхронизации",
            source_cell_value="Новая строка из синхронизации",
        )
        conflict = SyncConflict(
            task=self.task,
            target_type="task",
            field_name="description",
            source_type="excel",
            old_value="Старое замечание",
            new_value="Новое замечание из синхронизации",
            status="pending",
            created_at=started_at + timedelta(seconds=1),
        )
        db.session.add_all([sync_log, new_task, conflict])
        db.session.commit()
        new_task_id = new_task.id

        response = self.client.post("/conflicts/cancel-sync", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        restored_task = db.session.get(Task, self.task.id)
        self.assertEqual(restored_task.description, "Старое замечание")
        self.assertEqual(restored_task.source_cell_value, "Старое замечание")
        self.assertIsNone(db.session.get(Task, new_task_id))
        self.assertIsNotNone(db.session.get(SyncLog, sync_log.id).rolled_back_at)
        self.assertEqual(
            SyncConflict.query.filter_by(status="pending").count(),
            0,
        )

    def test_upload_excel_does_not_start_second_sync_when_one_is_running(self):
        running_log = SyncLog(
            project=self.project,
            source_type="excel",
            source_name="already-running.xlsx",
            status="running",
            started_at=utc_now(),
            rollback_data=build_project_rollback_data(self.project.id),
        )
        db.session.add(running_log)
        db.session.commit()

        response = self.client.post("/upload-excel", data={"upload_kind": "remarks"}, follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertIn("/sync-logs", response.headers["Location"])
        self.assertEqual(SyncLog.query.filter_by(status="running").count(), 1)


if __name__ == "__main__":
    unittest.main()
