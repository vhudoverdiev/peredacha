import unittest

from app import db
from app.models import CrmAuditLog, Project
from tests import test_worker_task_updates as fixture


class CrmAuditTests(unittest.TestCase):
    setUp = fixture.WorkerTaskUpdatesTests.setUp
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def test_committed_changes_are_logged_and_journal_is_admin_only(self):
        self.login(self.manager)
        response = self.client.post("/objects/new", data={
            "name": "CRM audit example", "has_apartments": "y",
        })
        self.assertEqual(response.status_code, 302)
        project = Project.query.filter_by(name="CRM audit example").one()
        log = CrmAuditLog.query.filter_by(entity="projects", entity_id=project.id, action="create").one()
        self.assertEqual(log.user_id, self.manager.id)
        self.assertEqual(log.project_id, project.id)
        self.assertEqual(log.path, "/objects/new")
        self.assertIsNone(log.fields)

        path = "/developer/delete-logs?view=history"
        self.assertEqual(self.client.get(path).status_code, 403)
        self.manager.role = "admin"
        db.session.commit()
        self.login(self.manager)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn("private, no-store", response.headers["Cache-Control"])
        self.assertIn("Создание · Объект", response.text)
        self.assertIn(self.manager.username, response.text)
        self.assertIn(project.name, response.text.split('class="developer-delete-log-list"', 1)[1])

    def test_journal_tabs_have_a_separate_ajax_content_region(self):
        self.manager.role = "admin"
        db.session.commit()
        self.login(self.manager)
        for suffix, active in (("", "Удаления"), ("?view=history", "История изменений CRM")):
            response = self.client.get("/developer/delete-logs" + suffix)
            self.assertEqual(response.status_code, 200)
            journal = response.text.split('data-ajax-pagination-page="developer-delete-logs"', 1)[1]
            tabs, content = journal.split('<div data-ajax-pagination-content>', 1)
            self.assertIn("data-ajax-pagination-tabs", tabs)
            self.assertIn('aria-current="page"', tabs.split(f"<span>{active}</span>", 1)[0])
            self.assertIn("developer-delete-log-list", content)

    def test_bulk_changes_roll_back_with_business_transaction(self):
        with self.app.test_request_context("/audit-test", method="POST"):
            from flask_login import login_user

            login_user(self.manager)
            Project.query.filter_by(id=self.project.id).update({"name": "Rolled back"})
            log = CrmAuditLog.query.filter_by(entity="projects", action="update").one()
            self.assertEqual(log.affected_count, 1)
            db.session.rollback()
            self.assertEqual(CrmAuditLog.query.count(), 0)

    def test_journal_includes_existing_object_history(self):
        from app.models import ChangeLog, Task

        task = Task.query.filter_by(project_id=self.project.id).first()
        db.session.add(ChangeLog(
            task=task, user_id=self.manager.id, action="comment_added",
            field_name="comment", new_value="Комментарий из истории объекта",
        ))
        db.session.add(ChangeLog(
            task=task, action="source_header_point_repaired", field_name="work_point_id",
            old_value="12", new_value="34",
        ))
        self.manager.role = "admin"
        db.session.commit()
        self.login(self.manager)

        response = self.client.get("/developer/delete-logs?view=history")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Комментарий из истории объекта", response.text)
        self.assertIn(self.project.name, response.text)
        self.assertIn(task.apartment.detail_label(), response.text)
        self.assertIn(task.description, response.text)
        self.assertIn("Пункт исправлен по заголовку исходной таблицы", response.text)
        self.assertIn("было № 12, стало № 34", response.text)
