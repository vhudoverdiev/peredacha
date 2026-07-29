from datetime import date, datetime, timedelta
import unittest

from config import Config
from app import create_app, db
from app.models import (
    Apartment,
    Project,
    STATUS_CONTRACTOR,
    STATUS_DONE,
    STATUS_FINISHERS,
    STATUS_NOT_STARTED,
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
    detect_search_mode,
    detect_status_marker,
    get_multi_param_values,
    is_apartment_unsold,
    is_auto_done_remark,
    looks_like_apartment_identifier,
    normalize_apartment_number_cell,
    normalize_finishing_type,
    parse_date,
    parse_multi_premise_search,
    premise_matches_search,
    select_primary_work_point_columns,
)


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
                completed_date=datetime.utcnow(),
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

    def test_build_task_query_filters_multiple_premises_and_keeps_user_order(self):
        tasks = build_task_query({"q": "к15/к2, кв 12"}, project_id=self.project.id).all()

        self.assertEqual([task.source_uid for task in tasks], [
            "query-commercial-open",
            "query-apartment-open",
            "query-apartment-done",
        ])

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
