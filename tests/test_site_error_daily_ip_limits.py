import time
import unittest

from config import Config
from app import create_app, db
from app.models import SiteErrorReport
from app.security import _BUCKETS, ip_limit_key


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "site-error-daily-ip-limits-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class SiteErrorDailyIpLimitsTests(unittest.TestCase):
    def setUp(self):
        _BUCKETS.clear()
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        _BUCKETS.clear()

    def _prime_registration_captcha(self):
        with self.client.session_transaction() as session:
            session["registration_captcha_answer"] = "9"
            session["registration_captcha_issued_at"] = int(time.time())

    def test_registration_request_is_limited_to_one_successful_submission_per_ip_per_day(self):
        self.assertEqual(ip_limit_key("198.51.100.77"), ip_limit_key("198.51.100.78"))

        self._prime_registration_captcha()
        first = self.client.post(
            "/registration-request",
            data={"name": "QA Engineer", "email": "qa@example.com", "captcha_answer": "9"},
            environ_base={"REMOTE_ADDR": "198.51.100.77"},
            follow_redirects=False,
        )
        self.assertEqual(first.status_code, 302)

        self._prime_registration_captcha()
        second = self.client.post(
            "/registration-request",
            data={"name": "Second QA", "email": "second@example.com", "captcha_answer": "9"},
            environ_base={"REMOTE_ADDR": "198.51.100.77"},
            follow_redirects=False,
        )
        self.assertEqual(second.status_code, 302)

        reports = SiteErrorReport.query.filter_by(kind="registration").all()
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].ip_address, "198.51.100.77")
        self.assertIn("qa@example.com", reports[0].message)

        self._prime_registration_captcha()
        same_subnet = self.client.post(
            "/registration-request",
            data={"name": "Same Subnet QA", "email": "same-subnet@example.com", "captcha_answer": "9"},
            environ_base={"REMOTE_ADDR": "198.51.100.78"},
            follow_redirects=False,
        )
        self.assertEqual(same_subnet.status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(kind="registration").count(), 1)

        self._prime_registration_captcha()
        third = self.client.post(
            "/registration-request",
            data={"name": "Other QA", "email": "other@example.com", "captcha_answer": "9"},
            environ_base={"REMOTE_ADDR": "198.51.101.78"},
            follow_redirects=False,
        )
        self.assertEqual(third.status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(kind="registration").count(), 2)

    def test_report_error_is_limited_to_three_successful_submissions_per_ip_per_day(self):
        for index in range(3):
            response = self.client.post(
                "/report-error",
                data={"message": f"Problem {index + 1}", "page_url": "/"},
                environ_base={"REMOTE_ADDR": "203.0.113.45"},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)

        blocked = self.client.post(
            "/report-error",
            data={"message": "Problem 4", "page_url": "/"},
            environ_base={"REMOTE_ADDR": "203.0.113.45"},
            follow_redirects=False,
        )
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(kind="user").count(), 3)
        self.assertEqual(
            {report.ip_address for report in SiteErrorReport.query.filter_by(kind="user").all()},
            {"203.0.113.45"},
        )

        same_subnet = self.client.post(
            "/report-error",
            data={"message": "Problem from same subnet", "page_url": "/"},
            environ_base={"REMOTE_ADDR": "203.0.113.46"},
            follow_redirects=False,
        )
        self.assertEqual(same_subnet.status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(kind="user").count(), 3)

        other_ip = self.client.post(
            "/report-error",
            data={"message": "Problem from another subnet", "page_url": "/"},
            environ_base={"REMOTE_ADDR": "203.0.114.46"},
            follow_redirects=False,
        )
        self.assertEqual(other_ip.status_code, 302)
        self.assertEqual(SiteErrorReport.query.filter_by(kind="user").count(), 4)


if __name__ == "__main__":
    unittest.main()
