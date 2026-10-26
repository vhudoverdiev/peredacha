"""Source column positions must not become CRM point numbers."""
from unittest.mock import patch
from app import db
from app.models import Task, WorkPoint, SyncConflict
from app.services.task_service import sync_rows
from app.services.remark_catalog import point_keys
import unittest
import test_excel_import_contracts as fixture


class NamedPointSyncTests(unittest.TestCase):
    setUp=fixture.ExcelImportContractsTests.setUp
    tearDown=fixture.ExcelImportContractsTests.tearDown
    def rows(self, hydro=False):
        names=['Вентиляция','Стены. Потолки (штукатурка/шпаклёвка)','Возведение коробки здания','Работы по устройству подстилающего слоя']
        if hydro:names+=['Работы по устройству гидроизоляции пола в с/у']
        names+=['Работы по возведению блочных перегородок','Разнорабочие','Работы по монтажу ПВХ блоков','Работы по монтажу откосов и подоконников','Работы по монтажу холодного витражного остекления балконов','Работы по монтажу системы отопления','Работы по монтажу системы в/с, канализации','Работы по монтажу входных дверей','Электрика','Прочее']
        base=['№ кв. проект','стр. №','Собственник','Номер телефона','Вид отделки','Дата осмотра','АПП','Срок устранения замечаний по АПП','АВР']
        headers=base+names
        return [headers,list(range(1,len(headers)+1)),['1','1-1-1','','','Белая','','','','']+[f'Замечание по работам {i}' for i in range(len(names))]]

    def test_missing_hydro_and_rostelecom_do_not_shift_named_points(self):
        rows=self.rows();sync_rows(rows,'Таблица','Named project');db.session.commit()
        for task in Task.query.all():
            expected=point_keys(rows[0][task.source_column_index-1])
            self.assertEqual((task.work_point.point_number,),expected)
        self.assertNotIn('14',{t.work_point.point_number for t in Task.query.all()})
        self.assertNotIn('19',{t.work_point.point_number for t in Task.query.all()})

    def test_resync_repairs_old_assignments_without_duplicates_or_status_loss(self):
        rows=self.rows()
        def legacy(number,header,sheet,column):
            number=str(column)  # Simulate the old physical-column mapping.
            point=WorkPoint.query.filter_by(point_number=number,source_sheet_name=sheet).first()
            if point is None:
                point=WorkPoint(point_number=number,source_sheet_name=sheet);db.session.add(point)
            point.short_name=header;point.original_column_name=header;db.session.flush();return point
        with patch('app.services.task_service.get_or_update_work_point',side_effect=legacy):
            sync_rows(rows,'Таблица','Named project');db.session.commit()
        before={t.id:(t.description,t.source_uid) for t in Task.query.all()}
        task=Task.query.filter_by(source_column_index=16).one();task.status='done';task.is_done=True;db.session.commit()
        old_point=task.work_point;old_label=old_point.short_name
        sync_rows(rows,'Таблица','Named project');db.session.commit()
        self.assertEqual(before,{t.id:(t.description,t.source_uid) for t in Task.query.all()})
        db.session.refresh(task)
        self.assertEqual(task.work_point.point_number,'17');self.assertEqual(task.status,'done')
        self.assertEqual(old_point.short_name,old_label)
        self.assertEqual(SyncConflict.query.count(),0)
        sync_rows(rows,'Таблица','Named project');db.session.commit()
        self.assertEqual(len(before),Task.query.count())
