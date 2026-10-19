from datetime import date, datetime, timedelta
import unittest
from unittest.mock import patch

from config import Config
from app import create_app, db
from app.models import (
    Apartment,
    Project,
    STATUS_CONTRACTOR,
    STATUS_DONE,
    STATUS_FINISHERS,
    STATUS_NOT_STARTED,
    STATUS_PROBLEM,
    Task,
    WorkPoint,
)
from app.services.task_service import (
    APP_DEADLINE_NO_REMARKS,
    APP_DEADLINE_NORMAL,
    AVR_STATUS_NEEDED,
    AVR_STATUS_SIGNED,
    apply_app_deadline_logic,
    apartment_number_from_construction,
    build_task_query,
    change_task_status,
    contract_number_from_premise_identity,
    detect_search_mode,
    detect_status_marker,
    get_multi_param_values,
    is_apartment_unsold,
    is_auto_done_remark,
    looks_like_apartment_identifier,
    normalize_apartment_number_cell,
    normalize_finishing_type,
    normalize_parking_number,
    normalize_storeroom_number,
    parse_date,
    parse_multi_premise_search,
    premise_matches_search,
    repair_completed_source_marker_statuses,
    select_primary_work_point_columns,
    sync_rows,
    upsert_task_from_cell,
    dashboard_stats,
)
from app.time_utils import utc_now


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "task-service-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class TaskServicePureContractsTests(unittest.TestCase):
    def test_parse_date_accepts_supported_formats_and_rejects_ambiguous_values(self):
        self.assertEqual(parse_date("05.07.2026"), date(2026, 7, 5))
        self.assertEqual(parse_date("2026-07-05"), date(2026, 7, 5))
        self.assertEqual(parse_date("05/07/2026"), date(2026, 7, 5))
        self.assertEqual(parse_date("05.07.26"), date(2026, 7, 5))
        self.assertEqual(parse_date(datetime(2026, 7, 5, 14, 30)), date(2026, 7, 5))
        self.assertIsNone(parse_date("07-05-2026"))
        self.assertIsNone(parse_date("not a date"))

    def test_normalizers_discard_shifted_dates_numbers_and_service_rows(self):
        self.assertEqual(normalize_apartment_number_cell("10 (11)"), "10")
        self.assertEqual(normalize_apartment_number_cell(12.0), "12")
        self.assertIsNone(normalize_finishing_type(date(2026, 7, 5)))
        self.assertIsNone(normalize_finishing_type(42))
        self.assertIsNone(normalize_finishing_type("2026-07-05T12:00:00"))
        self.assertEqual(normalize_finishing_type("White box"), "White box")
        self.assertTrue(looks_like_apartment_identifier("12/3"))
        self.assertFalse(looks_like_apartment_identifier("Building 3, total"))

    def test_premise_search_detects_precise_business_identifiers(self):
        self.assertEqual(detect_search_mode("1-2-345"), ("construction_number", "1-2-345"))
        self.assertEqual(detect_search_mode("15"), ("premise_number", "15"))
        self.assertEqual(detect_search_mode("кв 15"), ("premise_number", "15"))
        self.assertEqual(detect_search_mode("к15/к2"), ("commercial_pair", "15|2"))
        self.assertEqual(detect_search_mode("к 2"), ("premise_number_or_building", "2"))
        self.assertEqual(detect_search_mode("кл"), ("premise_type", "storeroom"))
        self.assertEqual(detect_search_mode("кл1"), ("typed_premise_number", "storeroom|1"))
        self.assertEqual(detect_search_mode("п"), ("premise_type", "parking"))
        self.assertEqual(detect_search_mode("п 1"), ("typed_premise_number", "parking|1"))
        self.assertEqual(detect_search_mode("owner text"), ("text", "owner text"))

    def test_multi_premise_search_preserves_order_deduplicates_and_returns_tail(self):
        selectors, tail = parse_multi_premise_search("кв 12, 1-2-13; к15/к2; 12 urgent")

        self.assertEqual(selectors, [
            ("premise_number", "12"),
            ("construction_number", "1-2-13"),
            ("commercial_pair", "15|2"),
        ])
        self.assertEqual(tail, "urgent")

    def test_get_multi_param_values_supports_lists_repeated_values_and_csv(self):
        class Args:
            def __init__(self, values):
                self.values = values

            def getlist(self, key):
                return self.values

        self.assertEqual(get_multi_param_values(Args(["white, clean", "", "none"]), "finishing_group"), ["white", "clean", "none"])
        self.assertEqual(get_multi_param_values({"finishing_group": ["white", "clean,none"]}, "finishing_group"), ["white", "clean", "none"])
        self.assertEqual(get_multi_param_values({"finishing_group": "white, clean"}, "finishing_group"), ["white", "clean"])

    def test_status_markers_map_excel_annotations_to_terminal_statuses(self):
        self.assertTrue(is_auto_done_remark("- fixed during inspection"))
        self.assertEqual(detect_status_marker("замечание (ЛБ)"), STATUS_DONE)
        self.assertEqual(detect_status_marker("передать (чистовики)"), STATUS_FINISHERS)
        self.assertEqual(detect_status_marker("передать (подрядчик)"), STATUS_CONTRACTOR)
        self.assertIsNone(detect_status_marker("plain issue"))

    def test_app_deadline_logic_keeps_no_remarks_as_accepted_without_alarm_date(self):
        apartment = Apartment(deadline_date=date(2026, 7, 10), avr_status=AVR_STATUS_NEEDED)

        apply_app_deadline_logic(apartment, "без замечаний")

        self.assertTrue(apartment.is_app_mode)
        self.assertIsNone(apartment.app_deadline_date)
        self.assertIsNone(apartment.remark_deadline_date)
        self.assertEqual(apartment.app_deadline_status, APP_DEADLINE_NO_REMARKS)
        self.assertEqual(apartment.avr_status, AVR_STATUS_SIGNED)
        self.assertEqual(apartment.avr_signed_date, date(2026, 7, 10))

    def test_app_deadline_logic_sets_real_deadline_and_does_not_downgrade_signed_avr(self):
        apartment = Apartment(avr_status=AVR_STATUS_SIGNED, avr_signed_date=date(2026, 7, 1))

        apply_app_deadline_logic(apartment, "15.08.2026")

        self.assertTrue(apartment.is_app_mode)
        self.assertEqual(apartment.app_deadline_date, date(2026, 8, 15))
        self.assertEqual(apartment.remark_deadline_date, date(2026, 8, 15))
        self.assertEqual(apartment.app_deadline_status, APP_DEADLINE_NORMAL)
        self.assertEqual(apartment.avr_status, AVR_STATUS_SIGNED)
        self.assertEqual(apartment.avr_signed_date, date(2026, 7, 1))

    def test_app_deadline_logic_preserves_unknown_text_as_raw_without_deadline(self):
        apartment = Apartment(is_app_mode=True, avr_status="archived")

        apply_app_deadline_logic(apartment, "waiting for owner")

        self.assertEqual(apartment.app_deadline_raw, "waiting for owner")
        self.assertIsNone(apartment.app_deadline_date)
        self.assertIsNone(apartment.remark_deadline_date)
        self.assertEqual(apartment.avr_status, AVR_STATUS_NEEDED)

    def test_unsold_requires_explicit_marker_or_empty_flagged_owner(self):
        self.assertTrue(is_apartment_unsold(Apartment(owner_name="не продано")))
        self.assertTrue(is_apartment_unsold(Apartment(owner_name="", is_unsold=True)))
        self.assertFalse(is_apartment_unsold(Apartment(owner_name="Ivan Petrov", is_unsold=True)))
        self.assertFalse(is_apartment_unsold(Apartment(owner_name="", is_unsold=False)))

    def test_select_primary_work_points_keeps_best_group_and_dop_column(self):
        headers = ["apt", "point 10", "point 11", "other", "point 10", "point 11", "Доп соглашение ТМЦ"]
        point_columns = {1: "10", 2: "11", 4: "10", 5: "11", 6: "Доп соглашение ТМЦ"}

        selected = select_primary_work_point_columns(headers, point_columns)

        self.assertEqual(selected, {1: "10", 2: "11", 6: "Доп соглашение ТМЦ"})

    def test_apartment_number_from_construction_uses_last_numeric_segment(self):
        self.assertEqual(apartment_number_from_construction("1-2-345"), "345")
        self.assertIsNone(apartment_number_from_construction("1-2-A"))

    def test_storeroom_numbers_are_prefixed_with_kl(self):
        self.assertEqual(normalize_storeroom_number("1"), "КЛ1")
        self.assertEqual(normalize_storeroom_number("КЛ2"), "КЛ2")
        self.assertEqual(normalize_storeroom_number("1.0"), "КЛ1")
        self.assertEqual(normalize_storeroom_number("КЛ2.0"), "КЛ2")

    def test_parking_numbers_are_prefixed_with_p(self):
        self.assertEqual(normalize_parking_number("1"), "П1")
        self.assertEqual(normalize_parking_number("П2"), "П2")
        self.assertEqual(normalize_parking_number("2.0"), "П2")
        self.assertEqual(normalize_parking_number("П2.0"), "П2")

    def test_contract_number_prefers_parentheses_or_slash_and_falls_back_to_plain_number(self):
        self.assertEqual(contract_number_from_premise_identity("1(10)"), "10")
        self.assertEqual(contract_number_from_premise_identity("10/1"), "1")
        self.assertEqual(contract_number_from_premise_identity("330", "330/1"), "1")
        self.assertEqual(contract_number_from_premise_identity("330"), "330")
        self.assertEqual(contract_number_from_premise_identity("1.0"), "1")


class TaskServiceDatabaseContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.project = Project(name="Task service query QA")
        self.work_point = WorkPoint(point_number="10", source_sheet_name="query")
        self.second_point = WorkPoint(point_number="11", source_sheet_name="query")
        self.apartment = Apartment(project=self.project, apartment_number="12", construction_number="1-2-12")
        self.commercial = Apartment(project=self.project, apartment_number="15", building="2", premise_type="commercial")
        db.session.add_all([self.project, self.work_point, self.second_point, self.apartment, self.commercial])
        db.session.flush()
        db.session.add_all([
            Task(
                source_uid="query-apartment-open",
                project=self.project,
                apartment=self.apartment,
                work_point=self.work_point,
                description="Open apartment defect",
                status=STATUS_NOT_STARTED,
                is_done=False,
            ),
            Task(
                source_uid="query-apartment-done",
                project=self.project,
                apartment=self.apartment,
                work_point=self.second_point,
                description="Done apartment defect",
                status=STATUS_DONE,
                is_done=True,
                completed_date=utc_now(),
            ),
            Task(
                source_uid="query-commercial-open",
                project=self.project,
                apartment=self.commercial,
                work_point=self.work_point,
                description="Commercial defect",
                status=STATUS_NOT_STARTED,
                is_done=False,
            ),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_premise_matches_search_distinguishes_apartment_and_commercial_pair(self):
        self.assertTrue(premise_matches_search(self.apartment, "premise_number", "12"))
        self.assertTrue(premise_matches_search(self.apartment, "construction_number", "1-2-12"))
        self.assertFalse(premise_matches_search(self.apartment, "commercial_pair", "12|2"))
        self.assertTrue(premise_matches_search(self.commercial, "commercial_pair", "15|2"))
        self.assertTrue(premise_matches_search(self.commercial, "premise_number_or_building", "2"))
        storeroom = Apartment(project=self.project, apartment_number="КЛ1", premise_type="storeroom")
        parking = Apartment(project=self.project, apartment_number="П1", premise_type="parking")
        self.assertTrue(premise_matches_search(storeroom, "premise_type", "storeroom"))
        self.assertTrue(premise_matches_search(storeroom, "typed_premise_number", "storeroom|1"))
        self.assertFalse(premise_matches_search(self.apartment, "premise_type", "storeroom"))
        self.assertTrue(premise_matches_search(parking, "premise_type", "parking"))
        self.assertTrue(premise_matches_search(parking, "typed_premise_number", "parking|1"))
        self.assertFalse(premise_matches_search(storeroom, "premise_type", "parking"))

    def test_sync_rows_imports_storeroom_sheet_when_enabled(self):
        self.project.has_storerooms = True
        db.session.commit()
        rows = [
            ["Кв/№ пом", "Ф.И.О. собственника", "Телефон", "Отделка", "Пункт 10"],
            ["1 корпус", None, None, None, None],
            [1, "Иванов Иван", "7 900 000-00-01", None, "Замечание по кладовке"],
        ]

        result = sync_rows(rows, "Кладовки", project_name=self.project.name)

        self.assertEqual(result["created_count"], 1)
        storeroom = Apartment.query.filter_by(project_id=self.project.id, premise_type="storeroom").one()
        self.assertEqual(storeroom.apartment_number, "КЛ1")
        self.assertEqual(storeroom.construction_number, "КЛ1")
        self.assertEqual(storeroom.label(), "кл 1")
        self.assertEqual(storeroom.detail_label(), "Кладовка 1")
        self.assertEqual(storeroom.tasks[0].description, "Замечание по кладовке")

    def test_sync_rows_imports_storeroom_registry_without_remarks(self):
        self.project.has_storerooms = True
        db.session.commit()
        rows = [
            ["Факт/№ ДДУ", "Ф.И.О. Дольщиков", "Телефон", "Дата первичного осмотра"],
            ["1 корпус", None, None, None],
            [1, "Петров Пётр", "7 900 000-00-02", None],
        ]

        result = sync_rows(rows, "Кладовые", project_name=self.project.name)

        self.assertEqual(result["created_count"], 0)
        storeroom = Apartment.query.filter_by(project_id=self.project.id, premise_type="storeroom").one()
        self.assertEqual(storeroom.apartment_number, "КЛ1")
        self.assertEqual(storeroom.owner_name, "Петров Пётр")
        self.assertEqual(storeroom.phone, "7 900 000-00-02")
        self.assertEqual(storeroom.tasks, [])

    def test_sync_rows_skips_storeroom_sheet_when_disabled(self):
        self.project.has_storerooms = False
        db.session.commit()
        rows = [
            ["Кв/№ пом", "Ф.И.О. собственника", "Телефон", "Отделка", "Пункт 10"],
            [1, "Иванов Иван", "7 900 000-00-01", None, "Замечание по кладовке"],
        ]

        result = sync_rows(rows, "Кладовки", project_name=self.project.name)

        self.assertEqual(result["created_count"], 0)
        self.assertEqual(Apartment.query.filter_by(project_id=self.project.id, premise_type="storeroom").count(), 0)

    def test_sync_rows_imports_parking_sheet_when_enabled(self):
        self.project.has_parking = True
        db.session.commit()
        rows = [
            ["№ паркинг", "Ф.И.О. Дольщиков", "Телефон", "Дата первичного осмотра"],
            [1, "Сидоров Семён", "7 900 000-00-03", None],
        ]

        result = sync_rows(rows, "Паркинг", project_name=self.project.name)

        self.assertEqual(result["created_count"], 0)
        parking = Apartment.query.filter_by(project_id=self.project.id, premise_type="parking").one()
        self.assertEqual(parking.apartment_number, "П1")
        self.assertEqual(parking.construction_number, "П1")
        self.assertEqual(parking.label(), "П1")
        self.assertEqual(parking.detail_label(), "Парковка П1")
        self.assertEqual(parking.owner_name, "Сидоров Семён")
        self.assertEqual(parking.phone, "7 900 000-00-03")
        self.assertEqual(parking.tasks, [])

    def test_sync_rows_skips_parking_sheet_when_disabled(self):
        self.project.has_parking = False
        db.session.commit()
        rows = [
            ["№ паркинг", "Ф.И.О. Дольщиков", "Телефон"],
            [1, "Сидоров Семён", "7 900 000-00-03"],
        ]

        result = sync_rows(rows, "Паркинг", project_name=self.project.name)

        self.assertEqual(result["created_count"], 0)
        self.assertEqual(Apartment.query.filter_by(project_id=self.project.id, premise_type="parking").count(), 0)

    def test_dashboard_stats_counts_storerooms_with_apartment_flow(self):
        storeroom = Apartment(
            project=self.project,
            apartment_number="КЛ1",
            construction_number="КЛ1",
            premise_type="storeroom",
            is_app_mode=True,
            first_inspection_present=True,
        )
        unsold_storeroom = Apartment(
            project=self.project,
            apartment_number="КЛ2",
            construction_number="КЛ2",
            premise_type="storeroom",
            owner_name="не продано",
            is_unsold=True,
        )
        db.session.add_all([storeroom, unsold_storeroom])
        db.session.commit()

        stats = dashboard_stats(self.project.id)

        self.assertEqual(stats["storeroom_count"], 2)
        self.assertEqual(stats["accepted"], 1)
        self.assertEqual(stats["unsold_storeroom_count"], 1)
        self.assertGreaterEqual(stats["apartments"], 4)

    def test_dashboard_stats_counts_parking_with_apartment_flow(self):
        parking = Apartment(
            project=self.project,
            apartment_number="П1",
            construction_number="П1",
            premise_type="parking",
            is_app_mode=True,
            first_inspection_present=True,
        )
        unsold_parking = Apartment(
            project=self.project,
            apartment_number="П2",
            construction_number="П2",
            premise_type="parking",
            owner_name="не продано",
            is_unsold=True,
        )
        db.session.add_all([parking, unsold_parking])
        db.session.commit()

        stats = dashboard_stats(self.project.id)

        self.assertEqual(stats["parking_count"], 2)
        self.assertEqual(stats["accepted"], 1)
        self.assertEqual(stats["unsold_parking_count"], 1)
        self.assertGreaterEqual(stats["apartments"], 4)

    def test_dashboard_accepted_remark_split_is_separate_for_each_premise_type(self):
        rows = [
            Apartment(project=self.project, apartment_number="101", premise_type="apartment", is_app_mode=True, app_deadline_status=APP_DEADLINE_NORMAL),
            Apartment(project=self.project, apartment_number="102", premise_type="apartment", is_app_mode=True, app_deadline_status=APP_DEADLINE_NO_REMARKS),
            Apartment(project=self.project, apartment_number="КЛ1", premise_type="storeroom", is_app_mode=True, app_deadline_status=APP_DEADLINE_NORMAL),
            Apartment(project=self.project, apartment_number="КЛ2", premise_type="storeroom", is_app_mode=True, app_deadline_status=APP_DEADLINE_NO_REMARKS),
            Apartment(project=self.project, apartment_number="П1", premise_type="parking", is_app_mode=True, app_deadline_status=APP_DEADLINE_NORMAL),
            Apartment(project=self.project, apartment_number="П2", premise_type="parking", is_app_mode=True, app_deadline_status=APP_DEADLINE_NO_REMARKS),
            Apartment(project=self.project, apartment_number="К1", premise_type="commercial", is_app_mode=True, app_deadline_status=APP_DEADLINE_NORMAL),
            Apartment(project=self.project, apartment_number="К2", premise_type="commercial", is_app_mode=True, app_deadline_status=APP_DEADLINE_NO_REMARKS),
        ]
        db.session.add_all(rows)
        db.session.commit()

        stats = dashboard_stats(self.project.id)

        self.assertEqual(stats["accepted_with_remarks"], 1)
        self.assertEqual(stats["accepted_no_remarks"], 1)
        self.assertEqual(stats["accepted_with_remarks_apartment"], 1)
        self.assertEqual(stats["accepted_no_remarks_apartment"], 1)
        self.assertEqual(stats["accepted_with_remarks_storeroom"], 1)
        self.assertEqual(stats["accepted_no_remarks_storeroom"], 1)
        self.assertEqual(stats["accepted_with_remarks_parking"], 1)
        self.assertEqual(stats["accepted_no_remarks_parking"], 1)
        self.assertEqual(stats["accepted_with_remarks_commercial"], 1)
        self.assertEqual(stats["accepted_no_remarks_commercial"], 1)

    def test_change_task_status_sets_and_clears_completed_date_contract(self):
        task = Task(
            source_uid="status-date-contract",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Status date contract",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        db.session.add(task)
        db.session.commit()
        finished_at = datetime(2026, 8, 3, 12, 0, 0)

        with patch("app.services.task_service.utc_now", return_value=finished_at):
            change_task_status(task, STATUS_DONE)

        self.assertTrue(task.is_done)
        self.assertEqual(task.completed_date, finished_at)

        change_task_status(task, STATUS_NOT_STARTED)

        self.assertFalse(task.is_done)
        self.assertIsNone(task.completed_date)

    def test_repair_marks_legacy_struck_remark_text_as_done(self):
        task = Task(
            source_uid="legacy-struck-open",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description='"Требуется восстановить стяжку пола."',
            source_cell_value='"Требуется восстановить стяжку пола."',
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        db.session.add(task)
        db.session.commit()

        changed = repair_completed_source_marker_statuses(project_id=self.project.id)

        db.session.refresh(task)
        self.assertEqual(changed, 1)
        self.assertEqual(task.status, STATUS_DONE)
        self.assertTrue(task.is_done)
        self.assertIsNotNone(task.completed_date)

    def test_repair_marks_legacy_struck_non_done_status_as_done(self):
        task = Task(
            source_uid="legacy-struck-problem",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description='"Требуется очистка от строительных смесей."',
            status=STATUS_PROBLEM,
            is_done=False,
        )
        db.session.add(task)
        db.session.commit()

        changed = repair_completed_source_marker_statuses(project_id=self.project.id)

        db.session.refresh(task)
        self.assertEqual(changed, 1)
        self.assertEqual(task.status, STATUS_DONE)
        self.assertTrue(task.is_done)

    def test_upsert_marks_fully_quoted_excel_remark_as_done(self):
        task, created = upsert_task_from_cell(
            project=self.project,
            apartment=self.apartment,
            legacy_construction_number="",
            legacy_apartment_number="",
            work_point=self.work_point,
            remark_text='"Требуется восстановить стяжку пола."',
            source_cell_value='"Требуется восстановить стяжку пола."',
            sheet_name="Таблица",
            row_index=12,
            column_index=10,
            source_cell_address="J12",
            sync_time=utc_now(),
        )
        db.session.commit()

        self.assertTrue(created)
        self.assertEqual(task.status, STATUS_DONE)
        self.assertTrue(task.is_done)
        self.assertIsNotNone(task.completed_date)

    def test_upsert_keeps_partial_quoted_remark_open(self):
        task, created = upsert_task_from_cell(
            project=self.project,
            apartment=self.apartment,
            legacy_construction_number="",
            legacy_apartment_number="",
            work_point=self.work_point,
            remark_text='Заменить "ручку"',
            source_cell_value='Заменить "ручку"',
            sheet_name="Таблица",
            row_index=13,
            column_index=10,
            source_cell_address="J13",
            sync_time=utc_now(),
        )
        db.session.commit()

        self.assertTrue(created)
        self.assertEqual(task.status, STATUS_NOT_STARTED)
        self.assertFalse(task.is_done)

    def test_build_task_query_filters_multiple_premises_and_uses_project_premise_order(self):
        tasks = build_task_query({"q": "к15/к2, кв 12"}, project_id=self.project.id).all()

        self.assertEqual([task.source_uid for task in tasks], [
            "query-apartment-open",
            "query-apartment-done",
            "query-commercial-open",
        ])

    def test_build_task_query_places_each_premise_type_in_the_shared_order(self):
        storeroom = Apartment(project=self.project, apartment_number="КЛ1", premise_type="storeroom")
        parking = Apartment(project=self.project, apartment_number="П1", premise_type="parking")
        db.session.add_all([storeroom, parking])
        db.session.flush()
        for uid, apartment in (("query-storeroom", storeroom), ("query-parking", parking)):
            db.session.add(Task(
                source_uid=uid,
                project=self.project,
                apartment=apartment,
                work_point=self.work_point,
                description=uid,
                status=STATUS_NOT_STARTED,
                is_done=False,
            ))
        db.session.commit()

        tasks = build_task_query({"sort": "priority"}, project_id=self.project.id).all()

        self.assertEqual(
            list(dict.fromkeys((task.apartment.premise_type or "apartment") for task in tasks)),
            ["apartment", "commercial", "storeroom", "parking"],
        )

    def test_build_task_query_text_search_filters_individual_remark_rows(self):
        matching = Task(
            source_uid="query-apartment-scratch",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Царапины на стеклопакете оконной створки.",
            source_cell_value="Царапины на стеклопакете оконной створки.",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        same_premise_non_matching = Task(
            source_uid="query-apartment-adjustment",
            project=self.project,
            apartment=self.apartment,
            work_point=self.second_point,
            description="Требуется регулировка и очистка от строительных смесей ПВХ конструкций.",
            source_cell_value="Царапины в другой строке этой квартиры.",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        other_premise_matching = Task(
            source_uid="query-commercial-scratch",
            project=self.project,
            apartment=self.commercial,
            work_point=self.work_point,
            description="Царапины на витражном остеклении.",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        db.session.add_all([matching, same_premise_non_matching, other_premise_matching])
        db.session.commit()

        tasks = build_task_query({"q": "царапины"}, project_id=self.project.id).all()

        self.assertEqual({task.source_uid for task in tasks}, {
            "query-apartment-scratch",
            "query-commercial-scratch",
        })

    def test_build_task_query_premise_tail_search_filters_individual_remark_rows(self):
        matching = Task(
            source_uid="query-tail-scratch",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Царапины на стеклопакете оконной створки.",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        same_premise_non_matching = Task(
            source_uid="query-tail-adjustment",
            project=self.project,
            apartment=self.apartment,
            work_point=self.second_point,
            description="Требуется регулировка и очистка от строительных смесей ПВХ конструкций.",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        db.session.add_all([matching, same_premise_non_matching])
        db.session.commit()

        tasks = build_task_query({"q": "кв 12 царапины"}, project_id=self.project.id).all()

        self.assertEqual([task.source_uid for task in tasks], ["query-tail-scratch"])

    def test_build_task_query_status_filters_default_exclude_archived_and_missing(self):
        archived = Task(
            source_uid="query-archived",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Archived",
            status=STATUS_NOT_STARTED,
            is_archived=True,
        )
        missing = Task(
            source_uid="query-missing",
            project=self.project,
            apartment=self.apartment,
            work_point=self.work_point,
            description="Missing",
            status=STATUS_NOT_STARTED,
            is_missing_in_latest_sync=True,
        )
        db.session.add_all([archived, missing])
        db.session.commit()

        default_uids = {task.source_uid for task in build_task_query({}, project_id=self.project.id).all()}
        archived_uids = {task.source_uid for task in build_task_query({"status": "archived"}, project_id=self.project.id).all()}
        missing_uids = {task.source_uid for task in build_task_query({"status": "missing"}, project_id=self.project.id).all()}

        self.assertNotIn("query-archived", default_uids)
        self.assertNotIn("query-missing", default_uids)
        self.assertEqual(archived_uids, {"query-archived"})
        self.assertEqual(missing_uids, {"query-missing"})

    def test_build_task_query_deadline_filters_use_current_date_window(self):
        expired = Apartment(project=self.project, apartment_number="20", app_deadline_date=date.today() - timedelta(days=1))
        expiring = Apartment(project=self.project, apartment_number="21", app_deadline_date=date.today() + timedelta(days=15))
        future = Apartment(project=self.project, apartment_number="22", app_deadline_date=date.today() + timedelta(days=16))
        db.session.add_all([expired, expiring, future])
        db.session.flush()
        for uid, apartment in [("expired", expired), ("expiring", expiring), ("future", future)]:
            db.session.add(Task(
                source_uid=f"deadline-{uid}",
                project=self.project,
                apartment=apartment,
                work_point=self.work_point,
                description=uid,
                status=STATUS_NOT_STARTED,
            ))
        db.session.commit()

        expired_uids = {task.source_uid for task in build_task_query({"status": "deadline_expired"}, project_id=self.project.id).all()}
        expiring_uids = {task.source_uid for task in build_task_query({"status": "deadline_expiring"}, project_id=self.project.id).all()}

        self.assertEqual(expired_uids, {"deadline-expired"})
        self.assertEqual(expiring_uids, {"deadline-expiring"})


if __name__ == "__main__":
    unittest.main()
