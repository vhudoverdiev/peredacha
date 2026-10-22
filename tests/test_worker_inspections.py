from datetime import date, datetime, time, timedelta
from unittest.mock import patch
import unittest

from app import db
from app.models import Apartment, InspectionBooking, InspectionSlot, Project
import test_worker_task_updates as fixture


class WorkerInspectionsTests(unittest.TestCase):
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def setUp(self):
        fixture.WorkerTaskUpdatesTests.setUp(self)
        self.today = date(2026, 10, 22)
        self.second = Project(name='Разрешённый второй объект')
        self.forbidden = Project(name='ЗАПРЕЩЕННЫЙ ОБЪЕКТ')
        self.second_apartment = Apartment(project=self.second, apartment_number='42')
        self.forbidden_apartment = Apartment(project=self.forbidden, apartment_number='999')
        db.session.add_all([self.second_apartment, self.forbidden_apartment])
        db.session.flush()
        self.worker.set_project_access([self.project.id, self.second.id])
        self.first_booking = self.book(self.apartment, self.today, time(10), appointment_time=time(10, 15))
        self.second_booking = self.book(self.second_apartment, self.today, time(9))
        self.forbidden_booking = self.book(self.forbidden_apartment, self.today, time(11))
        self.tomorrow = self.book(self.apartment, self.today + timedelta(days=1), time(12))
        self.yesterday = self.book(self.apartment, self.today - timedelta(days=1), time(12))
        self.cancelled = self.book(self.apartment, self.today, time(13), status='cancelled')
        self.completed = self.book(self.apartment, self.today, time(14), status='completed')
        self.inconsistent = self.book(self.forbidden_apartment, self.today, time(15), project=self.project)
        db.session.commit()
        self.clock = patch('app.routes.utc_now', return_value=datetime(2026, 10, 21, 22, 30))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.login(self.worker)

    def book(self, apartment, day, start, status='booked', appointment_time=None, project=None):
        slot = InspectionSlot(project=project or apartment.project, day=day, start_time=start, duration_minutes=30)
        db.session.add(slot)
        db.session.flush()
        booking = InspectionBooking(slot=slot, active_slot_id=slot.id if status != 'cancelled' else None,
                                    apartment=apartment, status=status, appointment_time=appointment_time,
                                    contact='СЕКРЕТНЫЙ СОБСТВЕННИК', contact_phone='+79998887766', note='СЕКРЕТНЫЙ КОММЕНТАРИЙ')
        db.session.add(booking)
        db.session.flush()
        return booking

    def test_each_worker_role_sees_only_today_in_allowed_projects(self):
        for role in ('painter', 'handyman', 'glazier', 'executor'):
            with self.subTest(role=role):
                self.worker.role = role
                db.session.commit()
                self.login(self.worker)
                response = self.client.get('/my-inspections')
                self.assertEqual(response.status_code, 200)
                page = response.text
                for booking in (self.first_booking, self.second_booking, self.completed):
                    self.assertIn(f'data-worker-inspection="{booking.id}"', page)
                for booking in (self.forbidden_booking, self.tomorrow, self.yesterday, self.cancelled, self.inconsistent):
                    self.assertNotIn(f'data-worker-inspection="{booking.id}"', page)
                self.assertIn('10:15', page)
                self.assertNotIn('СЕКРЕТНЫЙ СОБСТВЕННИК', page)
                self.assertNotIn('+79998887766', page)
                self.assertNotIn('СЕКРЕТНЫЙ КОММЕНТАРИЙ', page)
                self.assertNotIn('ЗАПРЕЩЕННЫЙ ОБЪЕКТ', page)

    def test_query_parameters_cannot_expand_projects_or_change_today(self):
        page = self.client.get(f'/my-inspections?project_id={self.forbidden.id}&date=2026-10-23').text
        self.assertIn(f'data-worker-inspection="{self.first_booking.id}"', page)
        self.assertNotIn(f'data-worker-inspection="{self.forbidden_booking.id}"', page)
        self.assertNotIn(f'data-worker-inspection="{self.tomorrow.id}"', page)

    def test_revoked_project_access_is_applied_immediately(self):
        self.worker.set_project_access([self.project.id])
        db.session.commit()
        page = self.client.get('/my-inspections').text
        self.assertNotIn(f'data-worker-inspection="{self.second_booking.id}"', page)
        self.assertIn(f'data-worker-inspection="{self.first_booking.id}"', page)

    def test_no_project_access_does_not_fall_back_to_all_projects(self):
        self.worker.set_project_access([])
        db.session.commit()
        page = self.client.get('/my-inspections').text
        self.assertIn('На сегодня осмотров нет', page)
        self.assertNotIn('data-worker-inspection="', page)

    def test_section_is_readonly_and_not_available_to_manager(self):
        self.assertEqual(self.client.post('/my-inspections').status_code, 405)
        self.login(self.manager)
        response = self.client.get('/my-inspections')
        self.assertEqual(response.status_code, 403)
