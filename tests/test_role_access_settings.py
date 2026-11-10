import json
import unittest
from app import db
from app.models import User
from app.services.task_service import set_setting
from tests import test_worker_task_updates as fixture

class AccessSettingsTests(unittest.TestCase):
    setUp=fixture.WorkerTaskUpdatesTests.setUp
    tearDown=fixture.WorkerTaskUpdatesTests.tearDown
    login=fixture.WorkerTaskUpdatesTests.login

    def test_anonymous_login_renders_without_role(self):
        from flask_login import AnonymousUserMixin
        from app.permissions import can_view_task_comments
        self.assertFalse(can_view_task_comments(AnonymousUserMixin()))
        from flask import g
        g.pop("_login_user", None)
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)

    def configure(self,role,sections,actions):
        set_setting('role_section_permissions',json.dumps({role:{'name':'Тестовая роль','sections':sections,'actions':actions}}))
        db.session.commit()

    def test_developer_page_prefills_existing_permissions(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        response=self.client.get('/settings/roles?role=office')
        self.assertEqual(response.status_code,200)
        import re
        html=response.get_data(as_text=True)
        self.assertIn('Настройка доступа',html)
        def checked(name,value):
            tag=re.search(r'<input[^>]*name="'+name+r'"[^>]*value="'+value+r'"[^>]*>',html)
            return bool(tag and 'checked' in tag.group(0))
        self.assertTrue(checked('sections','assignments'))
        self.assertTrue(checked('actions','object_create'))
        self.assertFalse(checked('actions','object_delete'))
        self.assertFalse(checked('sections','glass'))

    def test_history_uses_separate_scopes_and_filters_authors(self):
        from app.models import ChangeLog
        from app.role_settings import effective

        db.session.add_all([
            ChangeLog(task_id=self.task.id, user_id=self.manager.id, action="field_update",
                      field_name="description", new_value="OWN_HISTORY_MARKER"),
            ChangeLog(task_id=self.task.id, user_id=self.worker.id, action="field_update",
                      field_name="description", new_value="OTHER_HISTORY_MARKER"),
            ChangeLog(task_id=self.task.id, user_id=self.worker.id, action="comment_added",
                      new_value="PRIVATE_COMMENT_HISTORY"),
        ])
        db.session.commit()
        self.login(self.manager)
        with self.app.test_request_context():
            self.assertIn("remarks_history_own", effective("manager")["actions"])
            for role in ("painter", "handyman", "glazier"):
                self.assertNotIn("remarks_history_own", effective(role)["actions"])

        path = "/object/history"
        self.assertEqual(self.client.get(path).status_code, 404)

        set_setting("role_section_permissions", json.dumps({"manager": {
            "name": "Менеджер", "sections": ["dashboard", "remarks", "apartments"],
            "actions": ["dashboard_history_all", "remarks_history_own"],
            "history_permissions_saved": True,
        }}))
        db.session.commit()
        with self.app.test_request_context():
            self.assertNotIn("dashboard_history_all", effective("manager")["actions"])
        html = self.client.get(f"/tasks/{self.task.id}").text
        self.assertIn("OWN_HISTORY_MARKER", html)
        self.assertNotIn("OTHER_HISTORY_MARKER", html)
        self.assertNotIn("История изменений по помещению", self.client.get(f"/apartments/{self.apartment.id}").text)

    def test_admin_can_delete_only_unassigned_custom_roles(self):
        role = "custom_delete_test"
        self.configure(role, ["objects"], [])
        self.login(self.manager)
        path = "/settings/roles"
        deletion = {"operation": "delete", "role": role}
        self.assertEqual(self.client.post(path, data=deletion).status_code, 403)

        self.manager.role = "admin"
        self.worker.role = role
        db.session.commit()
        self.login(self.manager)
        self.assertEqual(self.client.post(path, data={"operation": "delete", "role": "manager"}).status_code, 400)
        blocked = self.client.post(path, data=deletion)
        self.assertEqual(blocked.status_code, 303)
        self.assertIn(role, blocked.location)
        self.assertEqual(self.client.get(f"{path}?role={role}").status_code, 200)

        self.worker.role = "painter"
        db.session.commit()
        deleted = self.client.post(path, data=deletion)
        self.assertEqual(deleted.status_code, 303)
        self.assertEqual(deleted.location, path)
        self.assertEqual(self.client.get(f"{path}?role={role}").status_code, 400)

    def test_new_user_can_only_receive_access_by_section(self):
        from app.models import ProjectGroup

        self.manager.role = "admin"
        group = ProjectGroup(name="Раздел для нового сотрудника")
        self.project.group = group
        db.session.commit()
        self.login(self.manager)
        path = "/users/new"
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn('name="access_group"', page.text)
        self.assertNotIn('name="limit_group_projects"', page.text)

        data = {"username": "section-user", "city": "Архангельск", "role": "manager",
                "password": "test-password", "access_group": str(group.id)}
        response = self.client.post(path, data={**data, "limit_group_projects": "1", "project_ids": str(self.project.id)})
        self.assertIn("выберите раздел целиком", response.text)
        self.assertIsNone(User.query.filter_by(username="section-user").first())
        self.assertEqual(self.client.post(path, data=data).status_code, 302)
        created = User.query.filter_by(username="section-user").one()
        self.assertEqual(created.project_group_policy["groups"], [group.id])

    def test_manager_cannot_manage_access(self):
        self.login(self.manager)
        self.assertEqual(self.client.get('/settings/roles').status_code,403)
        self.assertEqual(self.client.post('/settings/roles',data={'role':'new','name':'X'}).status_code,403)

    def test_disable_create_and_direct_url(self):
        self.configure('manager',['objects','apartments'],[])
        self.login(self.manager)
        self.assertEqual(self.client.get('/objects').status_code,200)
        self.assertEqual(self.client.get('/objects/new').status_code,403)
        self.assertEqual(self.client.post('/objects/new',data={'name':'Forbidden'}).status_code,403)
        self.assertEqual(self.client.get(f'/objects/{self.project.id}/edit').status_code,403)
        self.assertEqual(self.client.get('/assignments').status_code,403)

    def test_custom_role_section_and_actions(self):
        role='custom_permission_test'
        self.configure(role,['objects','apartments'],['premise_create'])
        self.manager.role=role;db.session.commit();self.login(self.manager)
        self.assertEqual(self.client.get(f'/objects/{self.project.id}/premises/new').status_code,200)
        self.assertEqual(self.client.get('/assignments').status_code,403)
        self.assertEqual(self.client.get('/settings/roles').status_code,403)
        self.assertEqual(self.client.get('/users').status_code,403)
        self.assertEqual(self.client.get('/settings').status_code,403)

    def test_new_role_save_and_selection(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        response=self.client.post('/settings/roles',data={'role':'new','name':'Контроль осмотров','sections':['records'],'actions':['record_book','unknown']})
        self.assertEqual(response.status_code,302)
        response=self.client.get(response.location)
        self.assertEqual(response.status_code,200)
        self.assertIn('Контроль осмотров',response.get_data(as_text=True))
        html=self.client.get('/users').get_data(as_text=True)
        self.assertIn('Контроль осмотров',html)

    def test_grant_create_but_keep_delete_and_other_project_protected(self):
        self.configure('manager',['objects'],['object_create'])
        self.login(self.manager)
        self.assertEqual(self.client.get('/objects/new').status_code,200)
        self.assertEqual(self.client.post(f'/objects/{self.project.id}/delete').status_code,403)
        self.assertEqual(self.client.get('/users').status_code,403)
        self.assertEqual(self.client.post('/objects/order',json={'ids':[self.project.id]}).status_code,403)

    def test_view_assignments_without_permission_to_change(self):
        self.configure('manager',['objects','assignments'],[])
        self.login(self.manager)
        self.assertEqual(self.client.get('/assignments?view=issued').status_code,200)
        self.assertEqual(self.client.post('/assignments?view=issued',data={'toggle_employee_status_task_id':self.task.id}).status_code,403)
        db.session.refresh(self.task)
        self.assertEqual(self.task.status,'not_started')

    def test_developer_badge_includes_other_objects_before_opening_inbox(self):
        from app.models import Project,SiteErrorReport
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        other=Project(name='Другой объект');db.session.add(other);db.session.flush()
        db.session.add(SiteErrorReport(project_id=other.id,message='Новое сообщение',status='new'))
        db.session.commit()
        html=self.client.get('/assignments?view=issued').get_data(as_text=True)
        self.assertIn('Новые уведомления: 1',html)

if __name__=='__main__':unittest.main()
