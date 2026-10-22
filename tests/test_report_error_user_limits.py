import unittest
from datetime import timedelta
from flask import g
from app import db
from app.models import SiteErrorReport, User
from app.security import _BUCKETS
from app.time_utils import utc_now
import test_worker_task_updates as fixture


class ReportErrorUserLimitsTests(unittest.TestCase):
    setUp = fixture.WorkerTaskUpdatesTests.setUp
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def report(self, ip='203.0.113.45', message='Ошибка'):
        g.pop('_login_user', None)
        return self.client.post('/report-error', data={'message': message, 'page_url': '/'},
                                environ_base={'REMOTE_ADDR': ip})

    def anonymous(self):
        g.pop('_login_user', None)
        with self.client.session_transaction() as session:
            session.clear()

    def test_each_account_has_three_reports_on_shared_ip(self):
        _BUCKETS.clear()
        for user in [self.worker, self.other, self.manager]:
            self.login(user)
            for _ in range(4):
                self.assertEqual(self.report().status_code, 302)
            self.assertEqual(SiteErrorReport.query.filter_by(user_id=user.id, kind='user').count(), 3)
        self.assertEqual(SiteErrorReport.query.filter_by(kind='user').count(), 9)

    def test_many_accounts_on_one_ip_do_not_share_a_quota(self):
        _BUCKETS.clear()
        for index in range(10):
            user = User(username=f'shared-ip-{index}', role='handyman', project=self.project)
            user.set_password('shared-ip-test-password')
            db.session.add(user)
            db.session.commit()
            self.login(user)
            for _ in range(3):
                self.assertEqual(self.report().status_code, 302)
            self.assertEqual(SiteErrorReport.query.filter_by(user_id=user.id, kind='user').count(), 3)
        self.assertEqual(SiteErrorReport.query.filter_by(kind='user').count(), 30)

    def test_account_limit_cannot_be_bypassed_by_changing_ip(self):
        _BUCKETS.clear()
        self.login(self.worker)
        for index in range(4):
            self.report(ip=f'198.51.{index}.1')
        self.assertEqual(SiteErrorReport.query.filter_by(user_id=self.worker.id).count(), 3)
        for row in SiteErrorReport.query.filter_by(user_id=self.worker.id):
            row.created_at = utc_now() - timedelta(days=2)
        db.session.commit()
        self.assertEqual(self.report().status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(user_id=self.worker.id).count(), 4)

    def test_anonymous_limit_stays_by_ip_and_excludes_authenticated_reports(self):
        _BUCKETS.clear()
        self.login(self.worker)
        for _ in range(3):
            self.report()
        self.anonymous()
        for _ in range(4):
            self.assertEqual(self.report().status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(kind='user', user_id=None).count(), 3)
        self.login(self.other)
        self.assertEqual(self.report().status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(user_id=self.other.id).count(), 1)
