from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import unittest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from app import db
from app.models import STATUS_CONCESSION, STATUS_FINISHERS, STATUS_GUARANTEE, STATUS_NOT_STARTED, Task
import test_worker_task_updates as fixture


class ApartmentSourceExportTests(unittest.TestCase):
    setUp = fixture.WorkerTaskUpdatesTests.setUp
    tearDown = fixture.WorkerTaskUpdatesTests.tearDown
    login = fixture.WorkerTaskUpdatesTests.login

    def test_template_headers_single_current_row_and_styles(self):
        self.login(self.manager)
        source=Path(self.temp_files.name)/'source.xlsx'
        wb=Workbook();ws=wb.active;ws.title='Квартиры'
        ws.append(['№ квартиры','ФИО собственника','Телефон','11. Стены и потолки'])
        ws['A1'].font=Font(name='Arial',bold=True,color='123456')
        ws['A1'].fill=PatternFill('solid',fgColor='AABBCC')
        ws['AR1'].fill=PatternFill('solid',fgColor='FFC000')
        ws.auto_filter.ref='A1:AR2'
        ws.append(['999','Чужой собственник','other phone','Секретное замечание'])
        hidden=wb.create_sheet('Hidden');hidden.sheet_state='hidden';hidden.append(['Other secret'])
        wb.save(source);wb.close()
        self.point.point_number='11'; self.task.is_done=True;self.task.status='done';db.session.commit()
        with patch('app.services.excel_export.resolve_source_excel_with_strikes_path',return_value=source):
            response=self.client.get(f'/apartments/{self.apartment.id}/source-table/export')
        self.assertEqual(response.status_code,200)
        exported=load_workbook(BytesIO(response.data),rich_text=True)
        self.assertEqual(exported.sheetnames,['Квартиры'])
        sheet=exported.active
        self.assertEqual(sheet.max_row,2)
        self.assertEqual(sheet.max_column,4)
        self.assertEqual(sheet.auto_filter.ref,'A1:D2')
        self.assertEqual(sheet.print_area,"'Квартиры'!$A$1:$D$2")
        self.assertEqual(sheet['A2'].value,'173')
        self.assertTrue(sheet['A1'].font.bold)
        self.assertEqual(sheet['A1'].fill.fgColor.rgb,'00AABBCC')
        content=' '.join(str(c.value) for row in sheet for c in row)
        self.assertIn('Покрасить стену',content)
        self.assertIn('- Покрасить стену', content)
        self.assertNotIn('Секретное',content);self.assertNotIn('999',content)
        self.assertTrue(any(c.font.strike for c in sheet[2]))
        exported.close();response.close()

    def test_one_apartment_status_markers_match_source_table_rules(self):
        self.login(self.manager)
        self.point.point_number = '11'
        self.task.description = 'Устранённое замечание'
        self.task.status = 'done'
        self.task.is_done = True
        statuses = [
            ('finishers', STATUS_FINISHERS, 'Передать отделочникам'),
            ('concession', STATUS_CONCESSION, 'Согласованное отступление'),
            ('guarantee', STATUS_GUARANTEE, 'Гарантийная работа'),
            ('open', STATUS_NOT_STARTED, 'Открытое замечание'),
        ]
        for uid, status, description in statuses:
            db.session.add(Task(
                source_uid=f'apartment-export-{uid}', project=self.project,
                apartment=self.apartment, work_point=self.point,
                description=description, source_cell_value=description,
                status=status, is_done=status != STATUS_NOT_STARTED,
            ))
        db.session.commit()
        response = self.client.get(f'/apartments/{self.apartment.id}/source-table/export')
        workbook = load_workbook(BytesIO(response.data), rich_text=True)
        text = '\n'.join(str(cell.value or '') for cell in workbook.active[workbook.active.max_row])
        self.assertIn('- Устранённое замечание', text)
        self.assertIn('Передать отделочникам (чистовики)', text)
        self.assertIn('Согласованное отступление (отступное)', text)
        self.assertIn('Гарантийная работа (гарантия)', text)
        self.assertIn('Открытое замечание', text)
        self.assertNotIn('- Открытое замечание', text)
        workbook.close(); response.close()

    def test_fallback_without_source_and_worker_denial(self):
        self.login(self.manager)
        page = self.client.get(f'/apartments/{self.apartment.id}').get_data(as_text=True)
        self.assertIn('btn btn-success apartment-source-export-btn', page)
        self.assertNotIn('title="Скачать таблицу только этого помещения"', page)
        with patch('app.services.excel_export.resolve_source_excel_with_strikes_path',side_effect=FileNotFoundError):
            response=self.client.get(f'/apartments/{self.apartment.id}/source-table/export')
        self.assertEqual(response.status_code,200)
        workbook=load_workbook(BytesIO(response.data));self.assertEqual(workbook.active.max_row,2)
        self.assertIn('Покрасить стену',' '.join(str(c.value) for c in workbook.active[2]))
        workbook.close();response.close()
        self.login(self.worker)
        self.assertNotEqual(self.client.get(f'/apartments/{self.apartment.id}/source-table/export').status_code,200)
