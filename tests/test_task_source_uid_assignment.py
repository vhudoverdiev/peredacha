import unittest

from config import Config
from app import create_app, db
from app.models import Apartment, Project, STATUS_NOT_STARTED, Task, WorkCategory, WorkPoint
from app.services.task_service import _claim_or_reuse_source_uid, _try_assign_source_uid


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "task-source-uid-assignment-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class TaskSourceUidAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        project = Project(name="Source UID QA")
        category = WorkCategory(name="QA")
        point = WorkPoint(point_number="10", short_name="QA point")
        category.work_points.append(point)
        apartment = Apartment(project=project, apartment_number="1", construction_number="1")
        self.first_task = Task(
            source_uid="source-uid-first",
            project=project,
            apartment=apartment,
            work_point=point,
            status=STATUS_NOT_STARTED,
            title="First",
            description="First",
        )
        self.second_task = Task(
            source_uid="source-uid-second",
            project=project,
            apartment=apartment,
            work_point=point,
            status=STATUS_NOT_STARTED,
            title="Second",
            description="Second",
        )
        db.session.add_all([project, category, point, apartment, self.first_task, self.second_task])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_source_uid_assignment_respects_pending_session_owner(self):
        self.first_task.source_uid = "source-uid-shared"

        assigned = _try_assign_source_uid(self.second_task, "source-uid-shared")

        self.assertFalse(assigned)
        self.assertEqual(self.second_task.source_uid, "source-uid-second")
        db.session.flush()

    def test_claim_source_uid_reuses_existing_owner_when_uid_is_taken(self):
        owner = _claim_or_reuse_source_uid(self.second_task, self.first_task.source_uid)

        self.assertEqual(owner.id, self.first_task.id)
        self.assertEqual(self.first_task.source_uid, "source-uid-first")
        self.assertEqual(self.second_task.source_uid, "source-uid-second")
        db.session.flush()


if __name__ == "__main__":
    unittest.main()
