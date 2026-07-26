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
    WorkCategory,
    WorkPoint,
)
from app.services.excel_import import sync_excel_file
from app.services.mapping_service import ensure_default_categories
from app.services.remark_entities import migrate_existing_compound_tasks, split_task_into_entities
from app.services.task_service import build_task_query, dop_agreement_work_point_clause, map_work_point_columns
from app.services.uid_service import build_source_fragment_uid, cell_hash, split_cell_remarks


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
        self.assertEqual(split_cell_remarks("МДФ;ХГВС"), ["МДФ;ХГВС"])
        self.assertEqual(
            split_cell_remarks("Длинная первая часть;Вторая часть"),
            ["Длинная первая часть;", "Вторая часть"],
        )

    def test_period_without_space_before_uppercase_is_a_boundary(self):
        self.assertEqual(
            split_cell_remarks("Первая длинная часть.Вторая часть."),
            ["Первая длинная часть.", "Вторая часть."],
        )

    def test_dates_decimals_abbreviations_and_numbered_prefixes_stay_intact(self):
        source = (
            "В т.ч. нужен профиль 1.5 мм. Дата осмотра 01.08.2026. "
            "Следующая работа. 1. Отдельная работа."
        )

        self.assertEqual(
            split_cell_remarks(source),
            [
                "В т.ч. нужен профиль 1.5 мм.",
                "Дата осмотра 01.08.2026.",
                "Следующая работа. 1. Отдельная работа.",
            ],
        )

    def test_exclamation_and_question_marks_do_not_create_entities(self):
        source = "Проверить! Новая фраза? Ещё фраза."
        self.assertEqual(split_cell_remarks(source), [source])

    def test_known_work_abbreviation_before_acronym_stays_in_one_remark(self):
        self.assertEqual(split_cell_remarks("отст.ХГВС"), ["отст.ХГВС"])
        self.assertEqual(split_cell_remarks("отст. ХГВС"), ["отст. ХГВС"])
        self.assertEqual(split_cell_remarks("отсут. ХГВС"), ["отсут. ХГВС"])
        self.assertEqual(split_cell_remarks("Повреж.МДФ"), ["Повреж.МДФ"])
        self.assertEqual(split_cell_remarks("Повреж. МДФ"), ["Повреж. МДФ"])
        self.assertEqual(
            split_cell_remarks("Усадочная трещина. Требуется регулировка"),
            ["Усадочная трещина.", "Требуется регулировка"],
        )


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
        source_text = "Первое замечание. Второе замечание; третье замечание"
        path = self._workbook(source_text)

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
        self.assertEqual(
            {task.source_cell_value for task in tasks},
            {source_text},
        )

        tasks[1].status = STATUS_DONE
        tasks[1].is_done = True
        db.session.commit()

        retry_result = sync_excel_file(path, project_name="Sentence entities import QA")
        self.assertEqual(retry_result["created_count"], 0)
        self.assertEqual(retry_result["updated_count"], 3)
        self.assertEqual(Task.query.count(), 3)
        self.assertEqual(Task.query.order_by(Task.id.asc()).all()[1].status, STATUS_DONE)
        self.assertEqual(SyncConflict.query.count(), 0)

    def test_resync_adopts_full_excel_cell_for_existing_split_fragments_without_conflict(self):
        source_text = "First longer issue text. Second issue;third issue"
        path = self._workbook(source_text)
        sync_excel_file(path, project_name="Sentence entities stable source QA")

        tasks = Task.query.order_by(Task.id.asc()).all()
        self.assertEqual([task.description for task in tasks], ["First longer issue text.", "Second issue;", "third issue"])
        for task in tasks:
            task.source_cell_value = task.description
            task.source_hash = cell_hash(task.description)
        db.session.add(
            SyncConflict(
                task=tasks[1],
                target_type="task",
                field_name="source_cell_value",
                source_type="excel",
                sheet_name=tasks[1].source_sheet_name,
                row_index=tasks[1].source_row_index,
                column_index=tasks[1].source_column_index,
                old_value=tasks[1].description,
                new_value=source_text,
                old_hash=cell_hash(tasks[1].description),
                new_hash=cell_hash(source_text),
                status="pending",
            )
        )
        db.session.commit()

        retry_result = sync_excel_file(path, project_name="Sentence entities stable source QA")

        self.assertEqual(retry_result["created_count"], 0)
        self.assertEqual(retry_result["updated_count"], 3)
        self.assertEqual(SyncConflict.query.count(), 0)
        refreshed = Task.query.order_by(Task.id.asc()).all()
        self.assertEqual({task.source_cell_value for task in refreshed}, {source_text})
        self.assertEqual({task.source_hash for task in refreshed}, {cell_hash(source_text)})

    def test_resync_consolidates_rows_split_by_old_abbreviation_rule(self):
        source_text = "отсут.ХГВС"
        project_name = "Abbreviation healing QA"
        path = self._workbook(source_text)

        project = Project(name=project_name)
        apartment = Apartment(project=project, apartment_number="1", construction_number="1-1-1")
        point = WorkPoint(
            point_number="10",
            source_sheet_name="Замечания",
            original_column_name="10. Маляры",
            short_name="10. Маляры",
            source_column_index=3,
            is_active=True,
        )
        db.session.add_all([project, apartment, point])
        db.session.flush()
        old_first = Task(
            source_uid=build_source_fragment_uid(project_name, "Замечания", 2, 3, 0),
            project=project,
            apartment=apartment,
            work_point=point,
            description="отсут.",
            source_cell_value="отсут.",
            source_hash=cell_hash("отсут."),
            source_sheet_name="Замечания",
            source_row_index=2,
            source_column_index=3,
            source_cell_address="C2",
        )
        old_extra = Task(
            source_uid=build_source_fragment_uid(project_name, "Замечания", 2, 3, 1),
            project=project,
            apartment=apartment,
            work_point=point,
            description="ХГВС",
            source_cell_value="ХГВС",
            source_hash=cell_hash("ХГВС"),
            source_sheet_name="Замечания",
            source_row_index=2,
            source_column_index=3,
            source_cell_address="C2",
        )
        db.session.add_all([old_first, old_extra])
        db.session.flush()
        db.session.add(
            SyncConflict(
                task=old_extra,
                target_type="task",
                field_name="source_cell_value",
                source_type="excel",
                sheet_name="Замечания",
                row_index=2,
                column_index=3,
                old_value="ХГВС",
                new_value=source_text,
                old_hash=cell_hash("ХГВС"),
                new_hash=cell_hash(source_text),
                status="pending",
            )
        )
        db.session.commit()

        result = sync_excel_file(path, project_name=project_name)

        self.assertEqual(result["created_count"], 0)
        self.assertEqual(SyncConflict.query.count(), 0)
        active_tasks = Task.query.filter_by(is_archived=False).order_by(Task.id.asc()).all()
        archived_tasks = Task.query.filter_by(is_archived=True).all()
        self.assertEqual([task.description for task in active_tasks], [source_text])
        self.assertEqual(active_tasks[0].source_cell_value, source_text)
        self.assertEqual(active_tasks[0].source_hash, cell_hash(source_text))
        self.assertEqual([task.id for task in archived_tasks], [old_extra.id])

    def test_dop_agreement_category_uses_header_name_when_column_number_shifts(self):
        project = Project(name="Dop agreement shifted column QA")
        apartment = Apartment(project=project, apartment_number="34")
        shifted_point = WorkPoint(
            point_number="26",
            source_sheet_name="Квартал 100-5",
            original_column_name="Отступное ТМЦ",
            short_name="Отступное ТМЦ",
            source_column_index=26,
            is_active=True,
        )
        ordinary_point = WorkPoint(
            point_number="26",
            source_sheet_name="Другой лист",
            original_column_name="Дата устранения",
            short_name="Дата устранения",
            source_column_index=26,
            is_active=True,
        )
        db.session.add_all([project, apartment, shifted_point, ordinary_point])
        db.session.flush()
        dop_task = Task(
            source_uid="dop-shifted-column",
            project=project,
            apartment=apartment,
            work_point=shifted_point,
            description="отступное ТМЦ",
        )
        ordinary_task = Task(
            source_uid="ordinary-column-26",
            project=project,
            apartment=apartment,
            work_point=ordinary_point,
            description="не доп. соглашение",
        )
        db.session.add_all([dop_task, ordinary_task])
        db.session.commit()

        ensure_default_categories()
        dop_category = WorkCategory.query.filter_by(name="Доп.Соглашение").one()

        self.assertIn(shifted_point.id, {point.id for point in dop_category.work_points})
        self.assertNotIn(ordinary_point.id, {point.id for point in dop_category.work_points})
        self.assertEqual(
            [task.id for task in build_task_query({}, category_id=dop_category.id, project_id=project.id).all()],
            [dop_task.id],
        )
        self.assertEqual(
            [task.id for task in Task.query.join(WorkPoint).filter(dop_agreement_work_point_clause()).all()],
            [dop_task.id],
        )

    def test_dop_agreement_header_is_imported_even_without_fixed_point_number(self):
        headers = ["№ кв", "Строительный номер", "Отступное ТМЦ"]
        self.assertEqual(
            map_work_point_columns(headers, {"apartment_number": 0, "construction_number": 1}),
            {2: "Отступное ТМЦ"},
        )

    def test_shifted_dop_agreement_column_imports_and_appears_in_category(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Квартал 100-5"
        headers = ["№ кв", "Строительный номер"] + [f"Служебный {idx}" for idx in range(3, 26)] + ["Отступное ТМЦ"]
        dop_text = "Отступное ТМЦ к выдаче. Отст. ХГВС; дополнительная часть"
        row = ["34", "1-1-34"] + ["" for _ in range(3, 26)] + [dop_text]
        sheet.append(headers)
        sheet.append(row)
        path = Path(self.tempdir.name) / "shifted-dop-column.xlsx"
        workbook.save(path)

        sync_excel_file(path, project_name="Dop agreement imported shifted column QA")
        ensure_default_categories()

        dop_category = WorkCategory.query.filter_by(name="Доп.Соглашение").one()
        tasks = build_task_query({}, category_id=dop_category.id).all()

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].apartment.apartment_number, "34")
        self.assertEqual(tasks[0].work_point.point_number, "26")
        self.assertEqual(tasks[0].work_point.original_column_name, "Отступное ТМЦ")
        self.assertEqual(tasks[0].description, dop_text)

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
            description="Первая большая проблема. Вторая большая проблема.",
            source_cell_value="Первая большая проблема. Вторая большая проблема.",
            status=STATUS_NOT_STARTED,
        )
        conflict = SyncConflict(
            task=task,
            target_type="task",
            field_name="description",
            source_type="excel",
            old_value=task.description,
            new_value="Первая новая большая проблема. Вторая новая большая проблема.",
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
