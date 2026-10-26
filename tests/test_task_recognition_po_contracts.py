from io import BytesIO
from unittest.mock import patch

import hashlib
import unittest

from config import Config
from app import create_app, db, login_manager
from app.models import (
    Apartment,
    Project,
    ROLE_ADMIN,
    STATUS_DONE,
    STATUS_CONCESSION,
    STATUS_NOT_STARTED,
    Task,
    User,
    WorkPoint,
)
from app.services.task_service import APP_DEADLINE_NO_REMARKS


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "task-recognition-po-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class TaskRecognitionPoContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        if self._testMethodName.startswith("test_pdf_only_"):
            octet = int(hashlib.sha1(self._testMethodName.encode()).hexdigest()[:2], 16)
            self.client.environ_base["REMOTE_ADDR"] = f"198.18.{octet}.1"
        self.project = Project(name="Recognition PO project")
        db.session.add(self.project)
        db.session.flush()
        self.apartment = Apartment(project=self.project, apartment_number="59")
        self.point_1 = WorkPoint(point_number="1", short_name="Пункт 1", source_sheet_name="manual")
        self.point_10 = WorkPoint(point_number="10", short_name="Вентиляция", source_sheet_name="manual")
        self.point = WorkPoint(point_number="13", short_name="Работы по устройству подстилающего слоя", source_sheet_name="manual")
        self.point_25 = WorkPoint(point_number="25", short_name="Прочее", source_sheet_name="manual")
        self.old_task = Task(
            source_uid="recognition-po-old",
            project=self.project,
            apartment=self.apartment,
            work_point=self.point,
            description="Старое замечание",
            source_cell_value="Старое замечание",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        username_suffix = hashlib.sha1(self._testMethodName.encode("utf-8")).hexdigest()[:10]
        self.admin = User(username=f"admin-{username_suffix}", role=ROLE_ADMIN, is_active=True, captcha_disabled=True)
        self.admin.set_password("correct-password")
        self.admin.set_project_access([self.project.id], all_projects=False)
        db.session.add_all([self.apartment, self.point_1, self.point_10, self.point, self.point_25, self.old_task, self.admin])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def _login(self):
        response = self.client.post(
            "/login",
            data={"username": self.admin.username, "password": "correct-password"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as sess:
            sess["current_project_id"] = self.project.id

    def test_pdf_only_recognition_is_unavailable_on_phones(self):
        self._login()
        before = Task.query.count()
        for agent in (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile Safari/604.1",
            "Mozilla/5.0 (Linux; Android 14) Chrome/132.0 Mobile YaBrowser/25.2",
        ):
            headers = {"User-Agent": agent}
            with patch("app.routes.recognize_pdf_act") as pdf:
                for method in ("get", "post"):
                    response = getattr(self.client, method)("/tasks/recognition", headers=headers)
                    self.assertEqual(response.status_code, 302)
                    self.assertIn("mode=manual", response.location)
                pdf.assert_not_called()
            for mode in ("manual", "auto"):
                response = self.client.get("/tasks/new?mode=" + mode, headers=headers)
                self.assertNotIn('/tasks/recognition', response.get_data(as_text=True))
        self.assertEqual(Task.query.count(), before)

    def test_pdf_only_upload_has_no_mode_selector(self):
        self._login()
        html = self.client.get("/tasks/recognition").get_data(as_text=True)
        self.assertIn('accept=".pdf,application/pdf"', html)
        self.assertIn('multiple required', html)
        self.assertNotIn('recognition_mode', html)
        self.assertNotIn('Рукописный', html)

    def test_pdf_only_rejects_images_even_with_legacy_mode_parameter(self):
        self._login()
        before = Task.query.count()
        with patch("app.routes.recognize_pdf_act") as recognize:
            response = self.client.post("/tasks/recognition", data={
                "action": "preview", "recognition_mode": "handwriting",
                "pdf_files": (BytesIO(b"not a PDF"), "act.jpg"),
            }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        recognize.assert_not_called()
        self.assertEqual(Task.query.count(), before)

    def test_pdf_only_preview_still_uses_pdf_recognizer(self):
        from app.services.pdf_recognition import PdfActPreview
        self._login()
        before = Task.query.count()
        preview = PdfActPreview(filename="act.pdf", template_ok=True, project_ok=True, project_prefix="",
                                apartment_number="59")
        with patch("app.routes.recognize_pdf_act", return_value=preview) as recognize:
            response = self.client.post("/tasks/recognition", data={
                "action": "preview", "pdf_files": (BytesIO(b"%PDF-1.4\n"), "act.pdf"),
            }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        recognize.assert_called_once()
        self.assertIn("Квартира из PDF: 59", response.get_data(as_text=True))
        self.assertEqual(Task.query.count(), before)

    def test_manual_single_form_requires_and_uses_selected_point(self):
        self._login()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "single",
                "apartment_id": str(self.apartment.id),
                "description": "Новое одиночное замечание",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Task.query.filter_by(description="Новое одиночное замечание").first())

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "single",
                "apartment_id": str(self.apartment.id),
                "point_number": "10",
                "description": "Новое одиночное замечание",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        task = Task.query.filter_by(description="Новое одиночное замечание").one()
        self.assertEqual(task.work_point.point_number, "10")

    def test_po_mode_saves_all_rows_and_completes_previous_open_tasks(self):
        self._login()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "po_mode": "1",
                "act_count": "1",
                "act_0_filename": "po.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_inspection_date": "2026-09-17",
                "act_0_row_count": "1",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "13",
                "act_0_row_0_description": "Новое замечание после ПО",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        db.session.refresh(self.old_task)
        self.assertEqual(self.old_task.status, STATUS_DONE)
        new_task = Task.query.filter(Task.description == "Новое замечание после ПО").one()
        self.assertEqual(new_task.status, STATUS_NOT_STARTED)
        self.assertEqual(new_task.work_point.point_number, "13")

    def test_pdf_act_date_is_saved_even_when_act_has_no_remark_rows(self):
        self._login()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "po_mode": "0",
                "act_count": "1",
                "act_0_filename": "act-no-remarks.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_inspection_date": "2026-09-18",
                "act_0_row_count": "0",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        db.session.refresh(self.apartment)
        self.assertEqual(self.apartment.inspection_date.isoformat(), "2026-09-18")

    def test_manual_single_concession_marks_selected_existing_tasks_as_concession(self):
        self._login()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "single",
                "apartment_id": str(self.apartment.id),
                "point_number": "26",
                "description": "Выданы отступные ТМЦ",
                "concession_task_ids": [str(self.old_task.id)],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.old_task)
        self.assertEqual(self.old_task.status, STATUS_CONCESSION)
        concession_task = Task.query.filter(Task.description == "Выданы отступные ТМЦ").one()
        self.assertEqual(concession_task.work_point.point_number, "26")

    def test_manual_act_concession_marks_selected_point_tasks_as_concession(self):
        self._login()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "act",
                "apartment_id": str(self.apartment.id),
                "description_26": "Выданы отступные по акту",
                "concession_point_numbers": ["13"],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.old_task)
        self.assertEqual(self.old_task.status, STATUS_CONCESSION)
        concession_task = Task.query.filter(Task.description == "Выданы отступные по акту").one()
        self.assertEqual(concession_task.work_point.point_number, "26")

    def test_manual_act_concession_can_mark_completed_tasks_as_concession(self):
        self.old_task.status = STATUS_DONE
        self.old_task.is_done = True
        db.session.commit()
        self._login()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "act",
                "apartment_id": str(self.apartment.id),
                "description_26": "Выданы отступные по выполненному",
                "concession_point_numbers": ["13"],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.old_task)
        self.assertEqual(self.old_task.status, STATUS_CONCESSION)

    def test_po_mode_keeps_identical_existing_remark_open(self):
        self._login()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "po_mode": "1",
                "act_count": "1",
                "act_0_filename": "po-identical.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "1",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "13",
                "act_0_row_0_description": "Старое замечание",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 200)
        db.session.refresh(self.old_task)
        self.assertEqual(self.old_task.status, STATUS_NOT_STARTED)
        self.assertEqual(Task.query.filter(Task.description == "Старое замечание").count(), 1)

    def test_po_mode_with_only_duplicate_rows_still_completes_other_previous_tasks(self):
        self._login()
        old_other = Task(
            source_uid="recognition-po-duplicate-old-other",
            project=self.project,
            apartment=self.apartment,
            work_point=self.point_25,
            description="Старое замечание другого пункта",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        db.session.add(old_other)
        db.session.commit()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "po_mode": "1",
                "act_count": "1",
                "act_0_filename": "po-only-duplicates.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "1",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "13",
                "act_0_row_0_description": "Старое замечание",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.old_task)
        db.session.refresh(old_other)
        self.assertEqual(self.old_task.status, STATUS_NOT_STARTED)
        self.assertEqual(old_other.status, STATUS_DONE)
        self.assertEqual(Task.query.filter(Task.description == "Старое замечание").count(), 1)

    def test_save_ignores_recognition_rows_before_point_ten(self):
        self._login()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "act_count": "1",
                "act_0_filename": "points.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "2",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "1",
                "act_0_row_0_description": "Старый пункт не должен сохраниться",
                "act_0_row_1_active": "1",
                "act_0_row_1_point": "10",
                "act_0_row_1_description": "Пункт десять сохраняется",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        self.assertIsNone(Task.query.filter(Task.description == "Старый пункт не должен сохраниться").one_or_none())
        saved_task = Task.query.filter(Task.description == "Пункт десять сохраняется").one()
        self.assertEqual(saved_task.work_point.point_number, "10")

    def test_auto_recognition_concession_marks_selected_point_tasks_as_concession(self):
        self._login()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "act_count": "1",
                "act_0_filename": "concession.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "1",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "26",
                "act_0_row_0_description": "Отступное из PDF",
                "act_0_concession_point_numbers": ["13"],
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.old_task)
        self.assertEqual(self.old_task.status, STATUS_CONCESSION)
        concession_task = Task.query.filter(Task.description == "Отступное из PDF").one()
        self.assertEqual(concession_task.work_point.point_number, "26")

    def test_auto_recognition_requires_text_for_concession_row(self):
        self._login()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "act_count": "1",
                "act_0_filename": "empty-concession.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "2",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "26",
                "act_0_row_0_description": "",
                "act_0_row_1_active": "1",
                "act_0_row_1_point": "10",
                "act_0_row_1_description": "Эту строку не сохраняем пока пустое отступное",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Заполните поле Отступное (ТМЦ)".encode("utf-8"), response.data)
        self.assertIsNone(Task.query.filter_by(description="Эту строку не сохраняем пока пустое отступное").one_or_none())

    def test_save_allows_mismatched_project_when_manually_verified(self):
        self._login()

        blocked_response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "act_count": "1",
                "act_0_filename": "mismatch.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "0",
                "act_0_project_name": "Другой объект",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "1",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "10",
                "act_0_row_0_description": "Ручная сверка без подтверждения",
            },
        )

        self.assertEqual(blocked_response.status_code, 200)
        self.assertIn("Сверьте ЖК".encode("utf-8"), blocked_response.data)
        self.assertIsNone(Task.query.filter_by(description="Ручная сверка без подтверждения").first())

        saved_response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "act_count": "1",
                "act_0_filename": "mismatch.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "0",
                "act_0_project_override": "1",
                "act_0_project_name": "Другой объект",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "1",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "10",
                "act_0_row_0_description": "Ручная сверка подтверждена",
            },
            follow_redirects=False,
        )

        self.assertEqual(saved_response.status_code, 302)
        self.assertEqual(saved_response.location, f"/apartments/{self.apartment.id}")
        saved_task = Task.query.filter_by(description="Ручная сверка подтверждена").one()
        self.assertEqual(saved_task.apartment_id, self.apartment.id)
        self.assertEqual(saved_task.work_point.point_number, "10")

    def test_save_ignores_unchecked_recognition_rows_even_with_text_in_po_mode(self):
        self._login()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "po_mode": "1",
                "act_count": "1",
                "act_0_filename": "unchecked.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "2",
                "act_0_row_0_point": "13",
                "act_0_row_0_description": "Снятая строка не должна сохраниться",
                "act_0_row_1_active": "1",
                "act_0_row_1_point": "10",
                "act_0_row_1_description": "Отмеченная строка сохраняется",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        self.assertIsNone(Task.query.filter(Task.description == "Снятая строка не должна сохраниться").one_or_none())
        saved_task = Task.query.filter(Task.description == "Отмеченная строка сохраняется").one()
        self.assertEqual(saved_task.work_point.point_number, "10")

    def test_auto_import_warns_to_enable_po_when_apartment_already_has_many_open_remarks(self):
        self._login()
        for index in range(5):
            db.session.add(Task(
                source_uid=f"recognition-po-many-{index}",
                project=self.project,
                apartment=self.apartment,
                work_point=self.point_10,
                description=f"Открытое замечание {index}",
                status=STATUS_NOT_STARTED,
                is_done=False,
            ))
        db.session.commit()

        response = self.client.post(
            "/tasks/recognition",
            data={
                "action": "save",
                "confirm_import": "1",
                "act_count": "1",
                "act_0_filename": "repeat.pdf",
                "act_0_template_ok": "1",
                "act_0_project_ok": "1",
                "act_0_apartment_id": str(self.apartment.id),
                "act_0_row_count": "1",
                "act_0_row_0_active": "1",
                "act_0_row_0_point": "10",
                "act_0_row_0_description": "Новое замечание без ПО",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertIn("Поставьте кнопку ПО", html)
        self.assertIsNone(Task.query.filter(Task.description == "Новое замечание без ПО").one_or_none())

    def test_manual_act_po_completes_old_non_identical_and_keeps_identical_open(self):
        self._login()
        old_other = Task(
            source_uid="manual-po-old-other",
            project=self.project,
            apartment=self.apartment,
            work_point=self.point_10,
            description="Старое по вентиляции",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        old_unmentioned_point = Task(
            source_uid="manual-po-old-unmentioned-point",
            project=self.project,
            apartment=self.apartment,
            work_point=self.point_25,
            description="Старое по пункту которого нет в новом акте",
            status=STATUS_NOT_STARTED,
            is_done=False,
        )
        db.session.add_all([old_other, old_unmentioned_point])
        db.session.commit()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "act",
                "apartment_id": str(self.apartment.id),
                "po_mode": "1",
                "description_10": "Новое по вентиляции",
                "description_13": "Старое замечание",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        db.session.refresh(self.old_task)
        db.session.refresh(old_other)
        db.session.refresh(old_unmentioned_point)
        self.assertEqual(self.old_task.status, STATUS_NOT_STARTED)
        self.assertEqual(old_other.status, STATUS_DONE)
        self.assertEqual(old_unmentioned_point.status, STATUS_DONE)
        self.assertEqual(Task.query.filter(Task.description == "Старое замечание").count(), 1)
        new_task = Task.query.filter(Task.description == "Новое по вентиляции").one()
        self.assertEqual(new_task.status, STATUS_NOT_STARTED)

    def test_manual_act_with_one_filled_point_is_saved(self):
        self._login()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "act",
                "apartment_id": str(self.apartment.id),
                "description_10": "Единственное замечание из акта",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        task = Task.query.filter(Task.description == "Единственное замечание из акта").one()
        self.assertEqual(task.work_point.point_number, "10")
        self.assertEqual(task.status, STATUS_NOT_STARTED)

    def test_manual_act_without_rows_warns_to_enable_po(self):
        self._login()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "act",
                "apartment_id": str(self.apartment.id),
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertIn("Вероятнее всего вам нужно нажать кнопку ПО", html)
        self.assertEqual(Task.query.count(), 1)

    def test_manual_act_po_without_rows_marks_apartment_no_remarks_and_completes_old_tasks(self):
        self._login()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "act",
                "apartment_id": str(self.apartment.id),
                "po_mode": "1",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/apartments/{self.apartment.id}")
        db.session.refresh(self.apartment)
        db.session.refresh(self.old_task)
        self.assertEqual(self.apartment.app_deadline_status, APP_DEADLINE_NO_REMARKS)
        self.assertEqual(self.old_task.status, STATUS_DONE)
        self.assertTrue(self.old_task.is_done)

    def test_manual_act_warns_to_enable_po_for_three_points_when_existing_remarks_exist(self):
        self._login()
        self.old_task.status = STATUS_DONE
        self.old_task.is_done = True
        db.session.commit()

        response = self.client.post(
            "/tasks/new",
            data={
                "add_mode": "manual",
                "manual_kind": "act",
                "apartment_id": str(self.apartment.id),
                "description_10": "Первое новое",
                "description_13": "Второе новое",
                "description_25": "Третье новое",
            },
            follow_redirects=True,
        )

        html = response.get_data(as_text=True)
        self.assertIn("Поставьте кнопку ПО", html)
        self.assertIsNone(Task.query.filter(Task.description == "Первое новое").one_or_none())


if __name__ == "__main__":
    unittest.main()
