import unittest

from app import create_app, db, login_manager
from app.models import Apartment, ChangeLog, Project, Task, TaskComment, User, WorkPoint
from config import Config


class CommentConfig(Config):
    TESTING = True
    SECRET_KEY = 'comment-tests'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class TaskCommentTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(CommentConfig)
        self.context = self.app.app_context()
        self.context.push()
        self.protection = login_manager.session_protection
        login_manager.session_protection = None
        db.create_all()
        self.project = Project(name='Comments')
        self.user = User(username='comment-manager', role='manager', project=self.project)
        self.other = User(username='other-manager', role='manager', project=self.project)
        self.task = Task(source_uid='comment-task', project=self.project,
                         apartment=Apartment(project=self.project, apartment_number='1'),
                         work_point=WorkPoint(point_number='10', short_name='Test', source_sheet_name='test'),
                         description='Test remark')
        self.user.set_password('Comment-tests-2026!')
        self.other.set_password('Comment-tests-2026!')
        db.session.add_all([self.user, self.other, self.task])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(_user_id=str(self.user.id), _fresh=True,
                           session_version=int(self.user.session_version or 0),
                           current_project_id=self.project.id)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.protection

    def add_comment(self, user=None, task=None):
        comment = TaskComment(task=task or self.task, user=user or self.user, body='Comment text')
        db.session.add(comment)
        db.session.commit()
        return comment

    def delete_url(self, comment):
        return f'/tasks/{self.task.id}/comments/{comment.id}/delete'

    def test_add_returns_history_and_immediate_delete_action(self):
        response = self.client.post(f'/tasks/{self.task.id}/comment', data={'body': 'New comment'},
                                    headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['ok'])
        self.assertIn('New comment', payload['history_entry']['summary'])
        self.assertEqual(TaskComment.query.count(), 1)
        self.assertEqual(self.client.post(payload['comment']['delete_url']).status_code, 302)
        self.assertEqual(TaskComment.query.count(), 0)
        self.assertEqual(ChangeLog.query.filter_by(action='comment_deleted').count(), 1)

    def test_cannot_delete_another_authors_comment(self):
        comment = self.add_comment(user=self.other)
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 403)
        self.assertEqual(TaskComment.query.count(), 1)

    def test_comment_must_belong_to_task(self):
        other_task = Task(source_uid='other-task', project=self.project, apartment=self.task.apartment,
                          work_point=self.task.work_point)
        comment = self.add_comment(task=other_task)
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 404)
        self.assertEqual(TaskComment.query.count(), 1)

    def test_cannot_delete_comment_in_another_project(self):
        comment = self.add_comment()
        self.task.project = Project(name='Foreign')
        db.session.commit()
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 404)
        self.assertEqual(TaskComment.query.count(), 1)

    def test_csrf_and_post_required(self):
        comment = self.add_comment()
        self.assertEqual(self.client.get(self.delete_url(comment)).status_code, 405)
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 400)
        self.assertEqual(TaskComment.query.count(), 1)

    def test_office_and_viewer_cannot_delete(self):
        comment = self.add_comment()
        for role in ('office', 'viewer'):
            self.user.role = role
            db.session.commit()
            self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 403)
        self.assertEqual(TaskComment.query.count(), 1)

    def test_admin_can_delete_other_authors_comment(self):
        comment = self.add_comment(user=self.other)
        self.user.role = 'admin'
        db.session.commit()
        self.assertEqual(self.client.post(self.delete_url(comment)).status_code, 302)
        self.assertEqual(TaskComment.query.count(), 0)
