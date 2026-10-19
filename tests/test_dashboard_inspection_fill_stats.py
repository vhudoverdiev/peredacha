import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from openpyxl.styles import Color, PatternFill

from config import Config
from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, SyncLog, User
from app.services.task_service import dashboard_stats
from app.services.transfer_import import inspect_transfer_workbook, sync_transfer_statistics


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "dashboard-inspection-fill-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


GOOGLE_THEME = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Google">
  <a:themeElements>
    <a:clrScheme name="Google">
      <a:dk1><a:srgbClr val="000000"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="000000"/></a:dk2>
      <a:lt2><a:srgbClr val="FFFFFF"/></a:lt2>
      <a:accent1><a:srgbClr val="4285F4"/></a:accent1>
      <a:accent2><a:srgbClr val="EA4335"/></a:accent2>
      <a:accent3><a:srgbClr val="FBBC04"/></a:accent3>
      <a:accent4><a:srgbClr val="34A853"/></a:accent4>
      <a:accent5><a:srgbClr val="FF6D01"/></a:accent5>
      <a:accent6><a:srgbClr val="46BDC6"/></a:accent6>
      <a:hlink><a:srgbClr val="1155CC"/></a:hlink>
      <a:folHlink><a:srgbClr val="1155CC"/></a:folHlink>
    </a:clrScheme>
  </a:themeElements>
</a:theme>
"""


class DashboardInspectionFillStatsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.tempdir = tempfile.TemporaryDirectory()

        self.project = Project(name="Inspection fill QA")
        self.user = User(username="inspection-fill-admin", password_hash="unused", role=ROLE_ADMIN)
        db.session.add_all([self.project, self.user])
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
            session["session_version"] = int(self.user.session_version or 0)
            session["current_project_id"] = self.project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.tempdir.cleanup()
        login_manager.session_protection = self.previous_session_protection

    def _statistics_workbook(self) -> Path:
        workbook = Workbook()
        workbook.loaded_theme = GOOGLE_THEME
        sheet = workbook.active
        sheet.title = "Статистика"
        sheet.append([
            "№ кв",
            "Ф.И.О. дольщиков",
            "Телефон",
            "Вид отделки",
            "Дата осмотра",
            "Дата первичного осмотра",
        ])
        rows = [
            ["1", "Owner 1", "+1", "Белая", datetime(2026, 7, 1, 10, 0), datetime(2026, 7, 1)],
            ["2", "Owner 2", "+2", "Белая", datetime(2026, 7, 2, 10, 0), datetime(2026, 7, 2)],
            ["3", "Owner 3", "+3", "Белая", datetime(2099, 7, 3, 10, 0), None],
            ["4", "Owner 4", "+4", "Белая", None, None],
            ["5", "Owner 5", "+5", "Белая", None, None],
        ]
        for row in rows:
            sheet.append(row)

        # Theme accent2 is red, accent3 is yellow and accent4 is green.
        sheet["E2"].fill = PatternFill(patternType="solid", fgColor=Color(theme=5))
        sheet["E3"].fill = PatternFill(patternType="solid", fgColor=Color(theme=6))
        sheet["E4"].fill = PatternFill(patternType="solid", fgColor=Color(theme=7))
        sheet["E5"].fill = PatternFill(patternType="solid", fgColor="FFFFFFFF")

        path = Path(self.tempdir.name) / "transfer-statistics.xlsx"
        workbook.save(path)
        return path

    def _duplicated_transfer_workbook(self) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Статистика"
        sheet.append([
            "№ кв",
            "Ф.И.О. дольщиков",
            "Телефон",
            "Вид отделки",
            "Дата осмотра",
            "Дата первичного осмотра",
        ])
        rows = [
            ["1", "Owner 1", "+1", "Белая", None, None],
            ["1", "Owner 1", "+1", "Белая", None, None],
            ["2", "Owner 2", "+2", "Белая", None, None],
            ["2", "Owner 2", "+2", "Белая", None, None],
            ["3", "не продано", None, "Белая", None, None],
            ["3", "не продано", None, "Белая", None, None],
        ]
        for row in rows:
            sheet.append(row)
        for cell_address in ("A2", "A3"):
            sheet[cell_address].fill = PatternFill(patternType="solid", fgColor="FF70AD47")

        path = Path(self.tempdir.name) / "duplicated-transfer-statistics.xlsx"
        workbook.save(path)
        return path

    def _workbook_with_extra_premise_sheets(self) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Квартиры"
        sheet.append([
            "Факт/№ ДДУ",
            "Ф.И.О. Дольщиков",
            "Телефон",
            "Вид отделки",
            "Запись",
            "Дата первичного осмотра",
            "Дата подписания АПП",
        ])
        sheet.append(["310/1", "Owner 310", "+7999", "Белая", None, None, None])

        parking = workbook.create_sheet("Паркинг")
        parking.append([
            "№ паркинга",
            "Ф.И.О. Дольщиков",
            "Телефон",
            "Вид отделки",
            "Запись",
            "Дата первичного осмотра",
            "Дата подписания АПП",
        ])
        parking.append([1, "Parking Owner", "+7998", "Без отделки", None, None, None])

        storerooms = workbook.create_sheet("Кладовки")
        storerooms.append([
            "№ кладовки",
            "Ф.И.О. Дольщиков",
            "Телефон",
            "Вид отделки",
            "Запись",
            "Дата первичного осмотра",
            "Дата подписания АПП",
        ])
        storerooms.append([2, "Storeroom Owner", "+7997", "Без отделки", None, None, None])

        path = Path(self.tempdir.name) / "transfer-with-extra-premises.xlsx"
        workbook.save(path)
        return path

    def test_only_date_in_inspection_column_marks_apartment_as_inspected(self):
        path = self._statistics_workbook()
        self.assertTrue(inspect_transfer_workbook(path)["ok"])

        result = sync_transfer_statistics(path, project_name=self.project.name)

        self.assertEqual(result["created_count"], 5)
        sync_log = SyncLog.query.one()
        self.assertEqual(sync_log.status, "success")
        self.assertIsNotNone(sync_log.started_at)
        self.assertIsNotNone(sync_log.finished_at)
        flags = {
            apartment.apartment_number: apartment.first_inspection_present
            for apartment in Apartment.query.order_by(Apartment.id.asc()).all()
        }
        self.assertEqual(
            flags,
            {"1": True, "2": True, "3": True, "4": False, "5": False},
        )
        stats = dashboard_stats(self.project.id)
        self.assertEqual(stats["inspected"], 3)
        self.assertEqual(stats["not_inspected"], 2)

    def test_transfer_sync_does_not_mark_free_form_record_text_as_inspected(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Статистика"
        sheet.append([
            "№ кв",
            "Ф.И.О. дольщиков",
            "Телефон",
            "Вид отделки",
            "Запись",
            "Дата первичного осмотра",
            "Дата подписания АПП",
        ])
        sheet.append(["10", "Owner 10", "+10", "Белая", "позвонить позже", None, None])
        sheet.append(["11", "Owner 11", "+11", "Белая", "25.09.2026", None, None])
        path = Path(self.tempdir.name) / "transfer-record-text.xlsx"
        workbook.save(path)

        sync_transfer_statistics(path, project_name=self.project.name)

        flags = {
            apartment.apartment_number: apartment.first_inspection_present
            for apartment in Apartment.query.order_by(Apartment.apartment_number.asc()).all()
        }
        self.assertEqual(flags, {"10": False, "11": True})

    def test_desktop_and_mobile_dashboard_render_the_same_fill_based_counts(self):
        sync_transfer_statistics(self._statistics_workbook(), project_name=self.project.name)

        for user_agent in (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Mozilla/5.0 (Linux; Android 15; Mobile)",
        ):
            with self.subTest(user_agent=user_agent):
                response = self.client.get("/", headers={"User-Agent": user_agent})
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                inspection_card = re.search(
                    r'<article class="dashboard-info-card">\s*'
                    r'<div class="dashboard-info-title[^"]*"><i class="bi bi-eye"></i>.*?</article>',
                    html,
                    re.DOTALL,
                )
                self.assertIsNotNone(inspection_card)
                self.assertIn("<b>3</b>", inspection_card.group(0))
                self.assertIn("<b>2</b>", inspection_card.group(0))

    def test_transfer_upload_notification_uses_grouped_dashboard_counts(self):
        path = self._duplicated_transfer_workbook()

        with path.open("rb") as upload, patch("app.routes.save_upload", return_value=path):
            response = self.client.post(
                "/upload-excel",
                data={
                    "upload_kind": "transfers",
                    "transfer-file": (upload, path.name),
                    "transfer-submit": "Загрузить статистику",
                },
                content_type="multipart/form-data",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("принято - 1, ждёт - 1, не продано - 1", html)
        self.assertNotIn("принято - 2, ждёт - 2, не продано - 2", html)

    def test_dashboard_hides_disabled_extra_premise_type_blocks(self):
        self.project.has_storerooms = False
        self.project.has_parking = False
        db.session.commit()

        response = self.client.get("/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Не принятых всего", html)
        self.assertNotIn("Кладовок", html)
        self.assertNotIn("Кладовки не продано", html)
        self.assertNotIn("Парковок", html)
        self.assertNotIn("Парковки не продано", html)

    def test_transfer_sync_imports_parking_storerooms_and_uses_first_slash_number(self):
        self.project.has_parking = True
        self.project.has_storerooms = True
        db.session.commit()

        result = sync_transfer_statistics(self._workbook_with_extra_premise_sheets(), project_name=self.project.name)

        self.assertEqual(result["created_count"], 3)
        apartment = Apartment.query.filter_by(premise_type="apartment").one()
        self.assertEqual(apartment.apartment_number, "310")
        parking = Apartment.query.filter_by(premise_type="parking").one()
        self.assertEqual(parking.apartment_number, "П1")
        self.assertEqual(parking.construction_number, "П1")
        self.assertEqual(parking.owner_name, "Parking Owner")
        storeroom = Apartment.query.filter_by(premise_type="storeroom").one()
        self.assertEqual(storeroom.apartment_number, "КЛ2")
        self.assertEqual(storeroom.construction_number, "КЛ2")
        self.assertEqual(storeroom.owner_name, "Storeroom Owner")
        stats = dashboard_stats(self.project.id)
        self.assertEqual(stats["apartment_count"], 1)
        self.assertEqual(stats["parking_count"], 1)
        self.assertEqual(stats["storeroom_count"], 1)


if __name__ == "__main__":
    unittest.main()
