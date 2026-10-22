"""Project workflows: permissions, isolated records, slot capacity and downloads."""
from datetime import date
from io import BytesIO
from pathlib import Path
from PIL import Image
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import (
    Appeal,
    AppealAttachment,
    AppealComment,
    InspectionSlot,
    InspectionBooking,
    Project,
    Apartment,
    ROLE_OFFICE,
    ROLE_OFFICE_MANAGER,
)
from app.services.inspection_schedule import has_prior_inspection, inspection_contact_lines, inspection_phone_lines
import test_worker_task_updates as fixture
import unittest


class ProjectWorkflowsTests(unittest.TestCase):
    setUp = fixture.WorkerTaskUpdatesTests.setUp
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def availability(self):
        return self.client.post('/records/availability', data={
            'start_date':'2026-10-21','end_date':'2026-10-21',
            'start_time':'09:00','end_time':'10:00','duration':'30','weekday':['2']})

    def test_mobile_workflow_shortcuts_exist_only_inside_a_project(self):
        self.login(self.manager)
        mobile_headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1'}
        for selected in (False, True):
            with self.client.session_transaction() as state:
                if selected:
                    state['current_project_id'] = self.project.id
                else:
                    state.pop('current_project_id', None)
            self.assertNotIn('workflow-mobile-shortcuts', self.client.get('/objects', headers=mobile_headers).text)
        dashboard = self.client.get('/', headers=mobile_headers).text
        self.assertIn('class="workflow-mobile-shortcuts"', dashboard)
        self.assertIn('class="btn mobile-section-shortcut" href="/appeals"', dashboard)
        self.assertIn('class="btn mobile-section-shortcut" href="/records"', dashboard)

    def test_previous_inspection_and_multiple_names(self):
        self.assertEqual(inspection_contact_lines('Иванов Иван Иванович Петров Пётр Петрович'),
                         'Иванов Иван Иванович\nПетров Пётр Петрович')
        self.assertFalse(has_prior_inspection(self.apartment, date(2026, 10, 21)))
        self.apartment.inspection_date = date(2026, 10, 20)
        self.assertTrue(has_prior_inspection(self.apartment, date(2026, 10, 21)))
        self.assertFalse(has_prior_inspection(self.apartment, date(2026, 10, 20)))

    def test_multiple_phones_are_displayed_on_separate_lines(self):
        self.assertEqual(
            inspection_phone_lines('7 921 490-58-00 7 902 507-00-77'),
            '7 921 490-58-00\n7 902 507-00-77',
        )
        self.login(self.manager)
        self.availability()
        slot = InspectionSlot.query.first()
        self.client.post(f'/records/slots/{slot.id}/book', data={
            'apartment_id': self.apartment.id,
            'contact': 'Иванов Иван Иванович',
            'contact_phone': '7 921 490-58-00 7 902 507-00-77',
        })
        page = self.client.get('/records?date=2026-10-21').text
        self.assertIn('workflow-contact-phones', page)
        self.assertIn('7 921 490-58-00\n7 902 507-00-77', page)

    def test_office_manager_can_filter_and_change_internal_status(self):
        self.manager.role = ROLE_OFFICE_MANAGER
        db.session.commit()
        self.login(self.manager)
        listing = self.client.get('/apartments').text
        self.assertIn('name="po_status"', listing)
        detail = self.client.get(f'/apartments/{self.apartment.id}').text
        self.assertIn(f'/apartments/{self.apartment.id}/po-status', detail)
        response = self.client.post(f'/apartments/{self.apartment.id}/po-status',
                                    data={'po_status': 'do_not_invite'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.apartment.po_status, 'do_not_invite')
        filtered = self.client.get('/apartments?po_status=thrown').text
        self.assertIn('name="po_status"', filtered)
        self.assertIn('Найдено помещений: <b>0</b>', filtered)
        matching = self.client.get('/apartments?po_status=do_not_invite').text
        self.assertIn('Найдено помещений: <b>1</b>', matching)

    def test_upcoming_inspection_takes_priority_over_previous_date(self):
        from app.routes import _apartment_inspection_status
        from datetime import timedelta
        self.apartment.inspection_date = date.today() - timedelta(days=1)
        self.apartment.reinspection_date = date.today() + timedelta(days=1)
        self.assertEqual(_apartment_inspection_status([self.apartment]), 'Будет')

    def test_apartment_comments_show_author_and_date(self):
        self.login(self.manager)
        endpoint = f'/apartments/{self.apartment.id}/comment'
        self.client.post(endpoint, data={'apartment_comment': 'Первый комментарий'})
        self.client.post(endpoint, data={'apartment_comment': 'Второй комментарий'})
        page = self.client.get(f'/apartments/{self.apartment.id}').text
        self.assertIn('Первый комментарий', page)
        self.assertIn('Второй комментарий', page)
        self.assertIn('apartment-comment-entry', page)
        self.assertIn(self.manager.full_name or self.manager.username, page)

    def test_call_list_only_shows_invited_without_upcoming_inspection(self):
        from datetime import timedelta
        self.login(self.manager)
        self.apartment.po_status = 'thrown'
        self.apartment.po_status_manual = True
        db.session.commit()
        page = self.client.get('/records/call-list').text
        self.assertIn(self.apartment.label(), page)
        self.assertIn(f'/records/apartment/{self.apartment.id}/book', page)
        self.assertIn(f'/apartments/{self.apartment.id}', page)
        schedule = self.client.get('/records').text
        self.assertIn('Помещений для обзвона: 1', schedule)
        self.apartment.inspection_date = date.today() + timedelta(days=1)
        db.session.commit()
        page = self.client.get('/records/call-list').text
        self.assertIn('Список обзвона пуст', page)
        schedule = self.client.get('/records').text
        self.assertNotIn('Помещений для обзвона:', schedule)

    def test_call_list_comment_keeps_history_with_author(self):
        self.login(self.manager)
        self.apartment.po_status = 'thrown'
        self.apartment.po_status_manual = True
        db.session.commit()
        endpoint = f'/records/call-list/{self.apartment.id}/comments'
        for body in ('Не дозвонились', 'Перезвонить завтра'):
            response = self.client.post(endpoint, data={'body': body}, headers={'Accept': 'application/json'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['note']['body'], body)
        page = self.client.get('/records/call-list').text
        self.assertIn('Не дозвонились', page)
        self.assertIn('Перезвонить завтра', page)
        self.assertIn(self.manager.full_name or self.manager.username, page)

    def test_unsold_invited_apartment_is_not_in_call_list_or_count(self):
        self.login(self.manager)
        self.apartment.po_status = 'thrown'
        self.apartment.po_status_manual = True
        self.apartment.is_unsold = True
        db.session.commit()
        page = self.client.get('/records/call-list').text
        self.assertIn('Список обзвона пуст', page)
        self.assertNotIn(f'call-list-{self.apartment.id}', page)
        self.assertNotIn('Помещений для обзвона:', self.client.get('/records').text)

    def test_call_list_comment_can_be_deleted(self):
        from app.models import InspectionCallNote
        self.login(self.manager)
        self.apartment.po_status = 'thrown'
        self.apartment.po_status_manual = True
        db.session.commit()
        endpoint = f'/records/call-list/{self.apartment.id}/comments'
        created = self.client.post(endpoint, data={'body': 'Не дозвонились'}, headers={'Accept': 'application/json'})
        self.assertEqual(created.status_code, 200)
        note_id = created.json['note']['id']
        self.assertIn('Не дозвонились', self.client.get('/records/call-list').text)
        deleted = self.client.post(f'{endpoint}/{note_id}/delete', headers={'Accept': 'application/json'})
        self.assertEqual(deleted.status_code, 200)
        self.assertIsNone(db.session.get(InspectionCallNote, note_id))
        self.assertIn('Комментариев пока нет', self.client.get('/records/call-list').text)

    def test_time_settings_use_site_dropdowns(self):
        self.login(self.manager)
        response = self.client.get('/records/availability')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.count('data-time-field'), 6)
        self.assertNotIn('type="time"', response.text)
        self.assertIn('name="end_time" value="17:00"', response.text)
        self.assertIn('Выбрать время из списка', response.text)

    def test_allowed_roles_and_worker_exclusion(self):
        for role in ('admin','manager','supervisor','office','office_manager','viewer','painter','glazier','handyman','executor'):
            self.manager.role=role; db.session.commit(); self.login(self.manager)
            for path in ('/appeals','/records'):
                response=self.client.get(path)
                self.assertEqual(response.status_code==200, role in ('admin','manager','supervisor','office','office_manager','viewer'), (role,path,response.status_code))

    def test_only_developer_and_office_roles_can_create_appeals(self):
        payload = {
            'apartment_id': self.apartment.id,
            'caller_name': 'Сидоров Сергей',
            'caller_phone': '+7 900 111-22-33',
            'body': 'Просьба проверить квартиру',
        }
        for role in ('manager', 'supervisor', 'viewer', 'painter'):
            self.manager.role = role
            db.session.commit()
            self.login(self.manager)
            self.assertEqual(self.client.post('/appeals/new', data=payload).status_code, 403, role)
            if role != 'painter':
                self.assertNotIn('Создать обращение', self.client.get('/appeals').text)
        for role in ('admin', ROLE_OFFICE, ROLE_OFFICE_MANAGER):
            self.manager.role = role
            db.session.commit()
            self.login(self.manager)
            self.assertIn('Создать обращение', self.client.get('/appeals').text)
            response = self.client.post('/appeals/new', data=payload)
            self.assertEqual(response.status_code, 302, role)
            db.session.delete(Appeal.query.one())
            db.session.commit()

    def test_caller_name_and_phone_are_required(self):
        self.manager.role = ROLE_OFFICE
        db.session.commit()
        self.login(self.manager)
        base = {'apartment_id': self.apartment.id, 'body': 'Проверить обращение'}
        self.client.post('/appeals/new', data={**base, 'caller_phone': '+7 900 000-00-00'})
        self.client.post('/appeals/new', data={**base, 'caller_name': 'Иванов'})
        self.client.post('/appeals/new', data={**base, 'caller_name': 'Иванов', 'caller_phone': 'телефон'})
        self.assertEqual(Appeal.query.count(), 0)

    def test_appeal_accepts_only_real_pdf_or_jpeg_attachment(self):
        self.manager.role = ROLE_OFFICE_MANAGER
        db.session.commit()
        self.login(self.manager)
        base = {
            'apartment_id': str(self.apartment.id),
            'caller_name': 'Петров Пётр',
            'caller_phone': '+7 900 100-20-30',
            'body': 'Обращение с документом',
        }
        response = self.client.post('/appeals/new', data={
            **base,
            'attachment': (BytesIO(b'%PDF-1.4\n%%EOF\n'), 'акт осмотра.pdf'),
        }, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 302)
        appeal = Appeal.query.one()
        self.assertEqual(appeal.attachment.original_name, 'акт осмотра.pdf')
        self.assertNotIn('акт осмотра', appeal.attachment.stored_name)
        detail = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('акт осмотра.pdf', detail)
        download = self.client.get(f'/appeals/{appeal.id}/attachment')
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, 'application/pdf')
        self.assertTrue(download.data.startswith(b'%PDF'))
        download.close()

        db.session.delete(appeal)
        db.session.commit()
        invalid = self.client.post('/appeals/new', data={
            **base,
            'attachment': (BytesIO(b'<html>not an image</html>'), 'photo.jpeg'),
        }, content_type='multipart/form-data')
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('не соответствует расширению', invalid.get_data(as_text=True))
        self.assertEqual(Appeal.query.count(), 0)
        self.assertEqual(AppealAttachment.query.count(), 0)

        jpeg = self.client.post('/appeals/new', data={
            **base,
            'attachment': (BytesIO(b'\xff\xd8\xff\xe0JPEG DATA'), 'photo.JPG'),
        }, content_type='multipart/form-data')
        self.assertEqual(jpeg.status_code, 302)
        jpeg_appeal = Appeal.query.one()
        self.assertEqual(jpeg_appeal.attachment.mime_type, 'image/jpeg')
        self.assertTrue(jpeg_appeal.attachment.stored_name.endswith('.jpg'))

        foreign = Project(name='Закрытый объект')
        db.session.add(foreign)
        db.session.commit()
        jpeg_appeal.project_id = foreign.id
        db.session.commit()
        self.assertEqual(self.client.get(f'/appeals/{jpeg_appeal.id}/attachment').status_code, 404)

    def test_only_appeal_author_or_developer_can_delete_it_and_attachment(self):
        self.manager.role = ROLE_OFFICE
        db.session.commit()
        self.login(self.manager)
        response = self.client.post('/appeals/new', data={
            'apartment_id': str(self.apartment.id),
            'caller_name': 'Автор обращения',
            'caller_phone': '+7 900 000-00-01',
            'body': 'Удаляемое обращение',
            'attachment': (BytesIO(b'%PDF-1.4\n%%EOF\n'), 'delete-me.pdf'),
        }, content_type='multipart/form-data')
        appeal = Appeal.query.one()
        attachment_path = Path(self.app.config['UPLOAD_FOLDER']) / 'appeals' / str(self.project.id) / appeal.attachment.stored_name
        self.assertTrue(attachment_path.is_file())
        self.assertIn('Удалить', self.client.get(response.location).get_data(as_text=True))

        self.other.role = 'manager'
        db.session.commit()
        self.login(self.other)
        self.assertNotIn('Удалить', self.client.get(response.location).get_data(as_text=True))
        self.assertEqual(self.client.post(f'/appeals/{appeal.id}/delete').status_code, 403)
        self.assertEqual(Appeal.query.count(), 1)

        self.other.role = 'admin'
        self.other.all_projects_access = True
        db.session.commit()
        self.login(self.other)
        delete_response = self.client.post(f'/appeals/{appeal.id}/delete')
        self.assertEqual(delete_response.status_code, 302)
        self.assertEqual(Appeal.query.count(), 0)
        self.assertEqual(AppealAttachment.query.count(), 0)
        self.assertFalse(attachment_path.exists())

    def test_appeal_comments_status_and_project_isolation(self):
        self.manager.role = ROLE_OFFICE_MANAGER
        self.apartment.owner_name = 'Иванов Иван Иванович'
        self.apartment.phone = '+7 911 000-00-01'
        db.session.commit()
        self.login(self.manager)
        response=self.client.post('/appeals/new',data={
            'apartment_id':self.apartment.id,
            'caller_name':'Петров Пётр Петрович',
            'caller_phone':'+7 921 000-00-02',
            'body':'Нужен осмотр <script>',
        })
        self.assertEqual(response.status_code,302)
        appeal=Appeal.query.one(); self.assertEqual(appeal.status,'required')
        self.manager.role = 'manager'
        db.session.commit()
        self.login(self.manager)
        detail = self.client.get(response.location).text
        self.assertIn('&lt;script&gt;', detail)
        self.assertIn('Иванов Иван Иванович', detail)
        self.assertIn('+7 911 000-00-01', detail)
        self.assertIn('Петров Пётр Петрович', detail)
        self.assertIn('+7 921 000-00-02', detail)
        list_html = self.client.get('/appeals').text
        self.assertIn('Иванов Иван Иванович', list_html)
        self.assertIn('+7 911 000-00-01', list_html)
        self.client.post(response.location,data={'body':'Свяжемся с собственником'})
        self.client.post(f'/appeals/{appeal.id}/status',data={'status':'in_progress'})
        self.assertEqual(AppealComment.query.count(),2)
        self.assertEqual(appeal.status,'in_progress')
        self.assertIn('Нужен осмотр', self.client.get('/appeals?status=in_progress').text)
        self.assertNotIn('Нужен осмотр', self.client.get('/appeals?status=done').text)
        self.assertEqual(self.client.post(f'/appeals/{appeal.id}/status',data={'status':'invalid'}).status_code,400)
        foreign=Project(name='Other'); db.session.add(foreign);db.session.commit()
        apt=Apartment(project=foreign,apartment_number='999');db.session.add(apt);db.session.commit()
        self.client.post('/appeals/new',data={
            'apartment_id':apt.id,
            'caller_name':'Петров',
            'caller_phone':'+7 921 000-00-02',
            'body':'Wrong project',
        })
        self.assertEqual(Appeal.query.count(),1)
        appeal.project_id=foreign.id;db.session.commit()
        self.assertEqual(self.client.get(f'/appeals/{appeal.id}').status_code,404)

    def test_capacity_cancel_history_and_png(self):
        self.login(self.manager);self.availability();self.availability()
        self.assertEqual(InspectionSlot.query.count(),2)
        slot=InspectionSlot.query.first()
        payload={'apartment_id':self.apartment.id,'contact':'Петров +7 900 000 00 00','note':'Первичный осмотр','staff_id':self.manager.id}
        response=self.client.post(f'/records/slots/{slot.id}/book',data=payload)
        self.assertEqual(response.status_code,302)
        booking=InspectionBooking.query.one()
        self.client.post(f'/records/slots/{slot.id}/book',data=payload)
        self.assertEqual(InspectionBooking.query.count(),1)
        duplicate=InspectionBooking(slot_id=slot.id,active_slot_id=slot.id,apartment_id=self.apartment.id,status='booked')
        db.session.add(duplicate)
        with self.assertRaises(IntegrityError):db.session.commit()
        db.session.rollback()
        for view in ('day','week','month'):
            result=self.client.get('/records',query_string={'date':'2026-10-21','view':view})
            self.assertEqual(result.status_code,200)
            self.assertIn('173',result.text)
        png=self.client.get('/records/download?date=2026-10-21')
        self.assertEqual(png.status_code,200)
        self.assertEqual(png.mimetype,'image/png')
        image=Image.open(BytesIO(png.data));self.assertGreater(image.width,1000);image.verify()
        self.client.post(f'/records/{booking.id}/status',data={'status':'cancelled'})
        self.assertIsNone(booking.active_slot_id)
        self.client.post(f'/records/slots/{slot.id}/book',data=payload)
        self.assertEqual(InspectionBooking.query.count(),2)
        self.assertEqual(InspectionBooking.query.filter_by(status='cancelled').count(),1)

    def test_apartment_booking_form_and_month_grid(self):
        self.login(self.manager)
        self.apartment.owner_name = 'Иванов Иван Иванович'
        self.apartment.phone = '+7 900 111-22-33'
        db.session.commit()
        self.availability()
        slot = InspectionSlot.query.order_by(InspectionSlot.start_time).first()
        page = self.client.get(f'/records/apartment/{self.apartment.id}/book')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Иванов Иван Иванович', page.text)
        self.assertIn('+7 900 111-22-33', page.text)
        self.assertNotIn('Свободное время на', page.text)
        page = self.client.get(f'/records/apartment/{self.apartment.id}/book?date=2026-10-21')
        self.assertIn('Свободное время на', page.text)
        self.assertIn('09:00', page.text)
        result = self.client.post(f'/records/apartment/{self.apartment.id}/book', data={
            'date': '2026-10-21', 'slot_id': slot.id, 'appointment_time': '09:05',
            'contact': 'Иванов Иван Иванович', 'contact_phone': '+7 900 111-22-33',
            'note': 'Первый осмотр'})
        self.assertEqual(result.status_code, 302)
        self.assertIn('date=2026-10-21', result.location)
        self.assertEqual(InspectionBooking.query.one().appointment_time.strftime('%H:%M'), '09:05')
        month = self.client.get('/records?view=month&date=2026-10-21').text
        self.assertIn('data-day-url="/records?date=2026-09-28"', month)
        self.assertIn('data-day-url="/records?date=2026-11-01"', month)

    def test_closing_time_returns_json_without_page_navigation(self):
        self.login(self.manager)
        self.availability()
        slot = InspectionSlot.query.first()
        response = self.client.post(f'/records/slots/{slot.id}/toggle',
            data={'closed_reason': 'Обед'}, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['label'], 'Закрыто')
        self.assertFalse(response.json['is_open'])
        response = self.client.post(f'/records/slots/{slot.id}/toggle',
            headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['label'], 'Свободно')
        self.assertIsNone(slot.closed_reason)

    def test_apartment_booking_button_depends_on_inspection_status_not_date_editing(self):
        from datetime import timedelta
        for role in ('admin','manager','office','office_manager','supervisor'):
            self.manager.role=role;db.session.commit();self.login(self.manager)
            for future in (False,True):
                self.apartment.inspection_date=date.today()+timedelta(days=2) if future else None
                self.apartment.inspection_note=None
                self.apartment.first_inspection_present=False
                db.session.commit()
                for agent in ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1'):
                    response=self.client.get(f'/apartments/{self.apartment.id}',headers={'User-Agent':agent})
                    self.assertEqual(response.status_code,200)
                    import re
                    tag=re.search(r'<div[^>]*data-apartment-book-inspection-controls[^>]*>',response.text).group()
                    self.assertEqual('hidden' in tag,future,(role,future,agent))

    def test_booking_button_is_absent_for_unsold_and_app_on_desktop_and_mobile(self):
        for role in ('admin','office_manager'):
            self.manager.role=role;db.session.commit();self.login(self.manager)
            for mode in ('unsold','app','not_accepted'):
                self.apartment.is_unsold=mode=='unsold'
                self.apartment.is_app_mode=mode=='app'
                self.apartment.app_signed_date=date(2026,10,20) if mode=='app' else None
                self.apartment.inspection_date=None;self.apartment.reinspection_date=None
                self.apartment.first_inspection_date=None;self.apartment.inspection_note=None
                self.apartment.first_inspection_present=False
                db.session.commit()
                for agent in ('Mozilla/5.0 (Windows NT 10.0; Win64; x64)','Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1'):
                    response=self.client.get(f'/apartments/{self.apartment.id}',headers={'User-Agent':agent})
                    self.assertEqual(response.status_code,200)
                    self.assertEqual('data-apartment-book-inspection href=' in response.text,mode=='not_accepted',(role,mode,agent))

    def test_booking_then_repeated_manual_act_on_same_day_has_one_inspection_date(self):
        from app.routes import _apartment_inspection_values
        self.login(self.manager);self.availability()
        slot=InspectionSlot.query.first()
        response=self.client.post(f'/records/slots/{slot.id}/book',data={'apartment_id':self.apartment.id})
        self.assertEqual(response.status_code,302)
        self.assertEqual(InspectionBooking.query.count(),1)
        for attempt in range(2):
            response=self.client.post('/tasks/new',data={'add_mode':'manual','manual_kind':'act',
                'apartment_id':str(self.apartment.id),'inspection_date':'2026-10-21',
                'act_point':'17','act_description':'Регулировка оконного блока в комнате'})
            self.assertIn(response.status_code,(302,303) if attempt==0 else (200,302,303))
            db.session.refresh(self.apartment)
            self.assertEqual(_apartment_inspection_values(self.apartment),[date(2026,10,21)])
            self.assertNotIn('Дополнительный осмотр:',self.apartment.inspection_note or '')

    def test_booking_then_excel_and_act_same_date_does_not_duplicate(self):
        from datetime import datetime
        from app.routes import _apartment_inspection_values,_apply_inspection_date_to_group
        from app.services.task_service import sync_rows
        self.login(self.manager);self.availability()
        slot=InspectionSlot.query.first()
        self.client.post(f'/records/slots/{slot.id}/book',data={'apartment_id':self.apartment.id})
        for value in (date(2026,10,21),datetime(2026,10,21,10,30)):
            rows=[['№ кв. проект','стр. №','Дата осмотра','10. Вентиляция'],
                  [self.apartment.apartment_number,self.apartment.construction_number,value,'Проверка вентиляции']]
            sync_rows(rows,'Таблица',self.project.name);db.session.commit()
            self.assertFalse(_apply_inspection_date_to_group([self.apartment],date(2026,10,21)))
            db.session.commit();db.session.refresh(self.apartment)
            self.assertEqual(len(_apartment_inspection_values(self.apartment)),1)
            self.assertEqual(_apartment_inspection_values(self.apartment)[0].date() if isinstance(_apartment_inspection_values(self.apartment)[0],datetime) else _apartment_inspection_values(self.apartment)[0],date(2026,10,21))

    def test_elapsed_booking_sets_not_ready_once_at_end_of_moscow_interval(self):
        from datetime import datetime
        from unittest.mock import patch
        from app.routes import _apartment_inspection_status,_apartment_inspection_values
        self.login(self.manager);self.availability()
        slot=InspectionSlot.query.first()
        self.client.post(f'/records/slots/{slot.id}/book',data={'apartment_id':self.apartment.id})
        self.apartment.po_status='thrown';self.apartment.po_status_manual=True;db.session.commit()
        with patch('app.services.inspection_completion.utc_now',return_value=datetime(2026,10,21,6,29,59)):
            self.client.get(f'/apartments/{self.apartment.id}')
        self.assertEqual(self.apartment.po_status,'thrown')
        with patch('app.services.inspection_completion.utc_now',return_value=datetime(2026,10,21,6,30)):
            self.client.get(f'/apartments/{self.apartment.id}')
        db.session.refresh(self.apartment)
        self.assertEqual(InspectionBooking.query.one().status,'completed')
        self.assertEqual(self.apartment.po_status,'not_ready')
        self.assertEqual(_apartment_inspection_values(self.apartment),[date(2026,10,21)])
        self.assertEqual(_apartment_inspection_status([self.apartment]),'Был')
        self.apartment.po_status='to_throw';db.session.commit()
        self.client.get(f'/apartments/{self.apartment.id}')
        self.assertEqual(self.apartment.po_status,'to_throw')

    def test_elapsed_booking_uses_custom_time_and_does_not_touch_other_projects(self):
        from datetime import datetime,time
        from app.services.inspection_completion import complete_elapsed_inspections
        self.login(self.manager);self.availability()
        slot=InspectionSlot.query.first()
        self.client.post(f'/records/slots/{slot.id}/book',data={'apartment_id':self.apartment.id,'appointment_time':'09:20'})
        other=Project(name='Other inspection project');db.session.add(other);db.session.flush()
        other_apartment=Apartment(project=other,apartment_number='1',po_status='thrown',po_status_manual=True)
        other_slot=InspectionSlot(project=other,day=date(2026,10,21),start_time=time(8),duration_minutes=30)
        other_booking=InspectionBooking(slot=other_slot,apartment=other_apartment,status='booked')
        db.session.add_all([other_apartment,other_slot,other_booking]);db.session.commit()
        self.assertEqual(complete_elapsed_inspections(self.project.id,datetime(2026,10,21,6,30)),0)
        self.assertEqual(complete_elapsed_inspections(self.project.id,datetime(2026,10,21,6,50)),1)
        self.assertEqual(other_booking.status,'booked')
        self.assertEqual(other_apartment.po_status,'thrown')

    def test_cancelled_booking_does_not_reset_internal_status(self):
        from app.services.inspection_completion import complete_elapsed_inspections
        self.login(self.manager);self.availability()
        slot=InspectionSlot.query.first()
        self.client.post(f'/records/slots/{slot.id}/book',data={'apartment_id':self.apartment.id})
        booking=InspectionBooking.query.one();booking.status='cancelled';booking.active_slot_id=None
        self.apartment.po_status='thrown';self.apartment.po_status_manual=True;db.session.commit()
        self.assertEqual(complete_elapsed_inspections(self.project.id),0)
        self.assertEqual(self.apartment.po_status,'thrown')

    def test_mobile_can_delete_inspection_date_with_existing_permissions(self):
        headers={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1'}
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        self.apartment.inspection_date=date(2030,1,2);db.session.commit()
        response=self.client.post(f'/apartments/{self.apartment.id}/inspection-date/delete',data={'inspection_date':'2030-01-02'},headers=headers)
        self.assertEqual(response.status_code,302)
        db.session.refresh(self.apartment)
        self.assertIsNone(self.apartment.inspection_date)
        self.manager.role='viewer';db.session.commit()
        self.assertEqual(self.client.post(f'/apartments/{self.apartment.id}/inspection-date/delete',data={'inspection_date':'2030-01-02'},headers=headers).status_code,403)

    def test_each_free_slot_has_visible_close_icon_in_day_and_week(self):
        import re
        self.login(self.manager)
        self.availability()
        for view in ('day', 'week'):
            page=self.client.get(f'/records?date=2026-10-21&view={view}').text
            forms=re.findall(r'<form[^>]*data-slot-toggle[^>]*>.*?</form>', page, re.S)
            self.assertEqual(len(forms), 2)
            for form in forms:
                self.assertNotIn('hidden', form.split('>')[0])
                self.assertIn('aria-label="Закрыть время"', form)
                self.assertIn('bi-lock', form)
        slot=InspectionSlot.query.first()
        self.client.post(f'/records/slots/{slot.id}/toggle', headers={'Accept':'application/json'})
        page=self.client.get('/records?date=2026-10-21').text
        form=re.search(rf'<form[^>]*action="/records/slots/{slot.id}/toggle"[^>]*>.*?</form>', page, re.S).group()
        self.assertNotIn('hidden', form.split('>')[0])
        self.assertIn('aria-label="Открыть время"', form)

    def test_close_interval_stores_reason_without_showing_it_in_slots(self):
        self.login(self.manager)
        self.availability()
        response = self.client.post('/records/slots/close-interval', data={
            'day': '2026-10-21', 'start_time': '09:00', 'end_time': '10:00',
            'closed_reason': 'Служебная встреча',
        }, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['count'], 2)
        slots = InspectionSlot.query.order_by(InspectionSlot.start_time).all()
        self.assertTrue(all(not slot.is_open and slot.closed_reason == 'Служебная встреча' for slot in slots))
        self.manager.role = ROLE_OFFICE_MANAGER; db.session.commit(); self.login(self.manager)
        page = self.client.get('/records?date=2026-10-21').text
        self.assertIn('Закрыть интервал', page)
        self.assertIn('Служебная встреча', page)

    def test_close_interval_without_reason(self):
        self.login(self.manager)
        self.availability()
        before = Image.open(BytesIO(self.client.get('/records/download?date=2026-10-21').data))
        response = self.client.post('/records/slots/close-interval', data={
            'day': '2026-10-21', 'start_time': '09:00', 'end_time': '10:00',
        }, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['count'], 2)
        self.assertTrue(all(slot.closed_reason is None for slot in InspectionSlot.query.all()))
        after = Image.open(BytesIO(self.client.get('/records/download?date=2026-10-21').data))
        self.assertEqual(after.size, before.size)

    def test_only_office_manager_and_developer_see_reason_and_reopen_interval(self):
        self.login(self.manager)
        self.availability()
        slot = InspectionSlot.query.first()
        response = self.client.post('/records/slots/close-interval', data={
            'day': '2026-10-21', 'start_time': '09:00', 'end_time': '09:30',
            'closed_reason': 'Внутренняя встреча',
        }, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['closed_reason'], '')
        self.assertTrue(slot.closed_by_interval)
        for role in ('manager', ROLE_OFFICE, 'supervisor', 'viewer'):
            self.manager.role = role; db.session.commit(); self.login(self.manager)
            page = self.client.get('/records?date=2026-10-21').text
            self.assertNotIn('Внутренняя встреча', page)
            response = self.client.post(f'/records/slots/{slot.id}/toggle', headers={'Accept': 'application/json'})
            self.assertEqual(response.status_code, 403, role)
            self.assertFalse(slot.is_open)
        for role in (ROLE_OFFICE_MANAGER, 'admin'):
            self.manager.role = role; db.session.commit(); self.login(self.manager)
            self.assertIn('Внутренняя встреча', self.client.get('/records?date=2026-10-21').text)
        response = self.client.post(f'/records/slots/{slot.id}/toggle', headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(slot.is_open)

    def test_closed_slots_are_hidden_from_other_schedule_roles(self):
        self.login(self.manager)
        self.availability()
        slot = InspectionSlot.query.order_by(InspectionSlot.start_time).first()
        slot.is_open = False
        slot.closed_by_interval = True
        slot.closed_by_user_id = self.other.id
        db.session.commit()
        for role in ('manager', ROLE_OFFICE, ROLE_OFFICE_MANAGER, 'admin'):
            self.manager.role = role; db.session.commit(); self.login(self.manager)
            self.assertIn(f'data-slot-id="{slot.id}"', self.client.get('/records?date=2026-10-21').text)
        for role in ('supervisor', 'viewer'):
            self.manager.role = role; db.session.commit(); self.login(self.manager)
            for view in ('day', 'week'):
                self.assertNotIn(f'data-slot-id="{slot.id}"', self.client.get(f'/records?date=2026-10-21&view={view}').text)
        self.other.role = 'viewer'; db.session.commit(); self.login(self.other)
        self.assertIn(f'data-slot-id="{slot.id}"', self.client.get('/records?date=2026-10-21').text)

    def test_invalid_availability_and_csrf(self):
        self.login(self.manager)
        self.client.post('/records/availability',data={'start_date':'2026-10-21','end_date':'2027-10-21'})
        self.assertEqual(InspectionSlot.query.count(),0)
        self.app.config['WTF_CSRF_ENABLED']=True
        self.assertEqual(self.availability().status_code,400)
        self.assertEqual(self.client.post('/appeals/new',data={'apartment_id':self.apartment.id,'body':'text'}).status_code,400)

    def test_project_isolation_for_slots_and_readonly_legacy_roles_can_book(self):
        self.login(self.manager)
        self.availability()
        slot = InspectionSlot.query.first()
        foreign = Project(name='Foreign project')
        db.session.add(foreign); db.session.commit()
        apartment = Apartment(project=foreign, apartment_number='999')
        db.session.add(apartment); db.session.commit()
        url = f'/records/slots/{slot.id}/book'
        self.client.post(url, data={'apartment_id':apartment.id})
        self.assertEqual(InspectionBooking.query.count(), 0)
        self.client.post(url, data={'apartment_id':self.apartment.id, 'staff_id':self.worker.id})
        self.assertEqual(InspectionBooking.query.count(), 0)
        self.manager.role='viewer'; db.session.commit(); self.login(self.manager)
        self.assertEqual(self.client.post(url, data={'apartment_id':self.apartment.id}).status_code, 302)
        booking = InspectionBooking.query.one()
        slot.project_id=foreign.id; db.session.commit()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(f'/records/{booking.id}').status_code, 404)

    def test_new_workflow_tables_cascade_with_project(self):
        self.manager.role = ROLE_OFFICE
        db.session.commit()
        self.login(self.manager); self.availability()
        slot = InspectionSlot.query.first()
        self.client.post(f'/records/slots/{slot.id}/book', data={'apartment_id':self.apartment.id})
        self.client.post('/appeals/new',data={
            'apartment_id':self.apartment.id,
            'caller_name':'Звонивший',
            'caller_phone':'+7 900 000-00-00',
            'body':'Test',
        })
        db.session.delete(self.project); db.session.commit()
        self.assertEqual(InspectionBooking.query.count(),0)
        self.assertEqual(InspectionSlot.query.count(),0)
        self.assertEqual(Appeal.query.count(),0)
