import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from config import Config
from app import create_app, db
from app.models import (
    AppSetting,
    Apartment,
    GlassMeasurement,
    Project,
    STATUS_DONE,
    STATUS_NOT_STARTED,
    SyncConflict,
    Task,
    WorkPoint,
)
from app.services.excel_import import sync_excel_file
from app.services.remark_entities import migrate_existing_compound_tasks, split_task_into_entities
from app.services.uid_service import split_cell_remarks


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "remark-sentence-entities-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class RemarkSentenceSplitRuleTests(unittest.TestCase):
    def test_period_requires_uppercase_and_semicolon_always_splits(self):
        source = (
            "Первое замечание. Второе замечание; третье замечание. "
            "продолжение с маленькой буквы"
        )

        self.assertEqual(
            split_cell_remarks(source),
            [
                "Первое замечание.",
                "Второе замечание;",
                "третье замечание. продолжение с маленькой буквы",
            ],
        )

    def test_period_without_space_before_uppercase_is_a_boundary(self):
        self.assertEqual(
            split_cell_remarks("Первая часть.Вторая часть."),
            ["Первая часть.", "Вторая часть."],
        )

    def test_dates_decimals_abbreviations_and_numbered_prefixes_stay_intact(self):
        source = (
            "В т.ч. нужен профиль 1.5 мм. Дата 01.08.2026. "
            "Следующая работа. 1. Отдельная работа."
        )

        self.assertEqual(
            split_cell_remarks(source),
            [
                "В т.ч. нужен профиль 1.5 мм.",
                "Дата 01.08.2026.",
                "Следующая работа. 1. Отдельная работа.",
            ],
        )

    def test_exclamation_and_question_marks_do_not_create_entities(self):
        source = "Проверить! Новая фраза? Ещё фраза."
        self.assertEqual(split_cell_remarks(source), [source])


class RemarkSentenceEntityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.tempdir.cleanup()

    def _workbook(self, text: str) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Замечания"
        sheet.append(["№ кв", "Строительный номер", "10. Маляры"])
        sheet.append(["1", "1-1-1", text])
        path = Path(self.tempdir.name) / "sentence-entities.xlsx"
        workbook.save(path)
        return path

    def test_excel_sync_creates_independent_rows_and_is_idempotent(self):
        path = self._workbook("Первое замечание. Второе замечание; третье замечание")

        first_result = sync_excel_file(path, project_name="Sentence entities import QA")
        tasks = Task.query.order_by(Task.id.asc()).all()

        self.assertEqual(first_result["created_count"], 3)
        self.assertEqual(
            [task.description for task in tasks],
            ["Первое замечание.", "Второе замечание;", "третье замечание"],
        )
        self.assertEqual(len({task.source_uid for task in tasks}), 3)
        self.assertEqual(len({task.source_row_index for task in tasks}), 1)
        self.assertEqual(len({task.source_column_index for task in tasks}), 1)

        tasks[1].status = STATUS_DONE
        tasks[1].is_done = True
        db.session.commit()

        retry_result = sync_excel_file(path, project_name="Sentence entities import QA")
        self.assertEqual(retry_result["created_count"], 0)
        self.assertEqual(retry_result["updated_count"], 3)
        self.assertEqual(Task.query.count(), 3)
        self.assertEqual(Task.query.order_by(Task.id.asc()).all()[1].status, STATUS_DONE)

    def test_legacy_row_is_split_while_original_relations_stay_on_first_entity(self):
        project = Project(name="Sentence entities migration QA")
        apartment = Apartment(project=project, apartment_number="7")
        point = WorkPoint(point_number="16", source_sheet_name="legacy")
        task = Task(
            source_uid="legacy-compound-task",
            project=project,
            apartment=apartment,
            work_point=point,
            description="Стеклопакет повреждён. Отрегулировать створку; очистить раму",
            source_cell_value="Стеклопакет повреждён. Отрегулировать створку; очистить раму",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        measurement = GlassMeasurement(
            project=project,
            task=task,
            apartment=apartment,
            status="ordered",
        )
        db.session.add_all([project, apartment, point, task, measurement])
        db.session.commit()
        original_task_id = task.id
        original_measurement_id = measurement.id

        split_rows = split_task_into_entities(task)
        db.session.commit()

        self.assertEqual(len(split_rows), 3)
        self.assertEqual(Task.query.count(), 3)
        self.assertEqual(
            [item.description for item in Task.query.order_by(Task.id.asc()).all()],
            ["Стеклопакет повреждён.", "Отрегулировать створку;", "очистить раму"],
        )
        preserved_task = db.session.get(Task, original_task_id)
        self.assertEqual(preserved_task.glass_measurement.id, original_measurement_id)
        self.assertTrue(all(item.status == STATUS_NOT_STARTED for item in split_rows))

    def test_pending_sync_conflict_does_not_block_legacy_split(self):
        project = Project(name="Sentence entities pending conflict QA")
        apartment = Apartment(project=project, apartment_number="9")
        point = WorkPoint(point_number="16", source_sheet_name="legacy-conflict")
        task = Task(
            source_uid="legacy-conflict-compound-task",
            project=project,
            apartment=apartment,
            work_point=point,
            description="Первая проблема. Вторая проблема.",
            source_cell_value="Первая проблема. Вторая проблема.",
            status=STATUS_NOT_STARTED,
        )
        conflict = SyncConflict(
            task=task,
            target_type="task",
            field_name="description",
            source_type="excel",
            old_value=task.description,
            new_value="Первая новая проблема. Вторая новая проблема.",
            status="pending",
        )
        db.session.add_all([project, apartment, point, task, conflict])
        db.session.commit()

        result = migrate_existing_compound_tasks(force=True)

        self.assertEqual(result["split_tasks"], 1)
        self.assertEqual(result["created_tasks"], 1)
        self.assertEqual(Task.query.filter_by(project_id=project.id).count(), 2)
        self.assertEqual(db.session.get(SyncConflict, conflict.id).status, "pending")

    def test_new_migration_version_rescans_after_old_marker(self):
        AppSetting.query.filter_by(key="remark_sentence_entities_v2").delete()
        db.session.add(AppSetting(key="remark_sentence_entities_v1", value="already-ran"))
        project = Project(name="Sentence entities migration version QA")
        apartment = Apartment(project=project, apartment_number="11")
        point = WorkPoint(point_number="16", source_sheet_name="legacy-version")
        task = Task(
            source_uid="legacy-version-compound-task",
            project=project,
            apartment=apartment,
            work_point=point,
            description="First separate remark. Second separate remark;third separate remark. lowercase continuation",
            source_cell_value="First separate remark. Second separate remark;third separate remark. lowercase continuation",
            status=STATUS_NOT_STARTED,
        )
        db.session.add_all([project, apartment, point, task])
        db.session.commit()

        result = migrate_existing_compound_tasks()

        self.assertEqual(result["split_tasks"], 1)
        self.assertEqual(result["created_tasks"], 2)
        self.assertEqual(
            [item.description for item in Task.query.order_by(Task.id.asc()).all()],
            [
                "First separate remark.",
                "Second separate remark;",
                "third separate remark. lowercase continuation",
            ],
        )
        self.assertIsNotNone(AppSetting.query.filter_by(key="remark_sentence_entities_v2").first())


if __name__ == "__main__":
    unittest.main()
