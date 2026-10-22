import json
import runpy
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import date, time
from flask import g
from app import db
from app.models import User, ROLE_ADMIN, InspectionSlot, InspectionBooking
import test_worker_task_updates as fixture


class ErrorAuditRegressionsTests(unittest.TestCase):
    setUp = fixture.WorkerTaskUpdatesTests.setUp
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def admin(self):
        admin = User(username='audit-admin', role=ROLE_ADMIN, project=self.project)
        admin.set_password('audit-admin-password')
        db.session.add(admin)
        db.session.commit()
        return admin

    def test_public_icon_and_robot_routes_work_without_login(self):
        for path, content_type in [('/favicon.ico', 'image/'), ('/apple-touch-icon.png', 'image/'), ('/robots.txt', 'text/plain')]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertTrue(response.content_type.startswith(content_type))
            self.assertNotIn('Set-Cookie', response.headers)
            response.close()

    def test_admin_links_are_hidden_from_manager_and_permissions_remain(self):
        self.login(self.manager)
        page = self.client.get('/tasks').text
        self.assertNotIn('href="/users"', page)
        self.assertNotIn('href="/conflicts"', page)
        for path in ['/users', '/conflicts']:
            self.assertEqual(self.client.get(path).status_code, 403)
        self.login(self.admin())
        self.assertEqual(self.client.get('/users').status_code, 200)
        self.assertEqual(self.client.get('/conflicts').status_code, 200)

    def test_conflict_redirect_preserves_admin_only_access(self):
        from app.routes import _redirect_after_sync_conflict
        for user, expected in [(self.manager, '/'), (self.admin(), '/conflicts')]:
            self.login(user)
            with self.app.test_request_context('/'), patch('app.routes.current_user', user):
                response = _redirect_after_sync_conflict()
                self.assertEqual(response.location, expected)

    def test_http_failure_logging_excludes_payload_query_and_credentials(self):
        self.login(self.manager)
        with self.assertLogs(self.app.logger, 'WARNING') as output:
            response = self.client.get('/conflicts?token=QUERY_SECRET', headers={'Authorization': 'Bearer HEADER_SECRET'})
        self.assertEqual(response.status_code, 403)
        message = '\n'.join(output.output)
        self.assertIn('administrative_section_required', message)
        self.assertNotIn('QUERY_SECRET', message)
        self.assertNotIn('HEADER_SECRET', message)
        self.assertIn('X-Request-ID', response.headers)
        self.assertIn(response.headers['X-Request-ID'], message)

    def test_missing_booking_stays_404_with_diagnostic_reason(self):
        self.login(self.manager)
        with self.assertLogs(self.app.logger, 'WARNING') as output:
            response = self.client.get('/records/999999')
        self.assertEqual(response.status_code, 404)
        self.assertIn('workflow_item_not_found', '\n'.join(output.output))

    def test_calendar_links_use_booking_id_and_existing_detail_opens(self):
        self.login(self.manager)
        first = InspectionSlot(project=self.project, day=date(2026, 10, 22), start_time=time(9))
        db.session.add(first)
        db.session.flush()
        slot = InspectionSlot(project=self.project, day=first.day, start_time=time(10))
        db.session.add(slot)
        db.session.flush()
        booking = InspectionBooking(slot=slot, active_slot_id=slot.id, apartment=self.apartment,
                                    created_by=self.manager, contact='Тест')
        db.session.add(booking)
        db.session.commit()
        self.assertNotEqual(booking.id, slot.id)
        page = self.client.get('/records?date=2026-10-22').text
        self.assertIn(f'href="/records/{booking.id}"', page)
        self.assertEqual(self.client.get(f'/records/{booking.id}').status_code, 200)

    def test_csrf_rejection_is_logged_and_never_executes_recognition(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.login(self.admin())
        with self.assertLogs(self.app.logger, 'WARNING') as output:
            response = self.client.post('/tasks/recognition', data={
                'csrf_token': 'PRIVATE_CSRF_SENTINEL', 'action': 'preview', 'message': 'PRIVATE_BODY_SENTINEL',
            })
        self.assertEqual(response.status_code, 400)
        message = '\n'.join(output.output)
        self.assertIn('csrf_validation', message)
        self.assertNotIn('PRIVATE_CSRF_SENTINEL', message)
        self.assertNotIn('PRIVATE_BODY_SENTINEL', message)

    def test_gunicorn_config_enables_journal_logs_without_query_or_cookies(self):
        import gunicorn.config
        settings = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'gunicorn.conf.py'))
        config = gunicorn.config.Config()
        self.assertEqual(config.config, './gunicorn.conf.py')
        for key in ['accesslog', 'errorlog', 'capture_output', 'access_log_format']:
            config.set(key, settings[key])
        self.assertEqual(config.accesslog, '-')
        self.assertEqual(config.errorlog, '-')
        self.assertTrue(config.capture_output)
        self.assertIn('%(U)s', config.access_log_format)
        self.assertNotIn('%(r)s', config.access_log_format)
        self.assertNotIn('%(q)s', config.access_log_format)
