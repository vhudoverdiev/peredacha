"""The retired notifications archive must not remain callable or grantable."""
import unittest
from app import db
from app.role_settings import ACTIONS
from app.routes import SECTION_LOCK_CHOICES, SECTION_LOCK_GROUPS
from tests import test_worker_task_updates as fixture

class RetiredNotificationsTests(unittest.TestCase):
    setUp=fixture.WorkerTaskUpdatesTests.setUp
    tearDown=fixture.WorkerTaskUpdatesTests.tearDown
    login=fixture.WorkerTaskUpdatesTests.login

    def test_old_archive_routes_cannot_archive_tasks(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        endpoints={rule.endpoint for rule in self.app.url_map.iter_rules()}
        self.assertNotIn('main.notifications',endpoints)
        self.assertNotIn('main.archive_apartment_avr',endpoints)
        for path in ['/notifications','/notifications?tab=60','/notifications?tab=archive']:
            self.assertEqual(self.client.get(path).status_code,404)
        response=self.client.post(f'/notifications/{self.apartment.id}/avr')
        self.assertEqual(response.status_code,404)
        db.session.expire_all()
        self.assertFalse(self.task.is_archived)
        self.assertIsNone(self.apartment.avr_archived_at)

    def test_retired_access_controls_are_removed(self):
        self.assertFalse(any(s['key']=='notifications' for s in SECTION_LOCK_CHOICES))
        self.assertFalse(any(a[0]=='notifications_archive' for a in ACTIONS))
        self.assertFalse(any('notifications' in group[2] for group in SECTION_LOCK_GROUPS))

    def test_access_settings_do_not_offer_retired_section(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        response=self.client.get('/settings/roles')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('notifications_archive',response.text)
        self.assertNotIn('60 к.д.',response.text)

    def test_current_po_filter_still_opens(self):
        self.login(self.manager)
        response=self.client.get('/apartments?po=1')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('60 к.д.',response.text)
        self.assertNotIn('/notifications',response.text)
