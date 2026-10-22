import html
import re
import unittest
from unittest.mock import patch

from app import db
from app.models import ChangeLog, Project, Apartment, Task, WorkPoint, RemarkPointReview
from app.services.remark_catalog import get_catalog, point_keys, tokens, fingerprint, RemarkCatalog
from app.work_points import WORK_POINT_LABELS
import test_worker_task_updates as fixture


class CatalogTests(unittest.TestCase):
    def test_catalog_contains_four_sources_and_observed_names(self):
        catalog=get_catalog()
        self.assertEqual(len(catalog.sources),4)
        self.assertGreater(len(catalog.entries),6000)
        self.assertGreater(sum(len(e['points'])>1 for e in catalog.entries),100)
        self.assertTrue(all(e['origins'] and e['text'] for e in catalog.entries))

    def test_point_matching_uses_names_not_numbers(self):
        self.assertEqual(point_keys('99. Работы по монтажу ПВХ блоков'),('17',))
        self.assertEqual(point_keys('14. Работы по возведению блочных перегородок'),('15',))
        self.assertEqual(point_keys('Работы по монтажу системы отопления, в/с, канализации'),('21','22'))
        self.assertEqual(point_keys('Дата осмотра'),())

    def test_partial_words_and_inflections_find_pvc(self):
        catalog=get_catalog()
        self.assertTrue(catalog.suggestions('регулиров',point='17'))
        self.assertTrue(catalog.suggestions('регулировка ПВХ',point='17'))
        self.assertTrue(any('пвх' in row['text'].casefold() for row in catalog.suggestions('регулировка')))
        self.assertTrue(all(len(row['points'])==1 for row in catalog.suggestions('регулировка')))
        self.assertTrue(tokens('регулировка') & tokens('регулировки'))
        self.assertEqual(catalog.classify('Регулировка ПВХ')['target'],'17')

    def test_generic_or_unseen_text_is_not_an_automatic_correction(self):
        for value in ('регулировка','царапина на стекле','трещина в стене','несуществующий квазидефект'):
            self.assertIsNone(get_catalog().classify(value)['target'],value)

    def test_conflicting_exact_reference_remains_uncertain(self):
        catalog=RemarkCatalog({'version':'test','sources':[], 'entries':[
            {'text':'Регулировка ПВХ','points':['17','23'],'count':2,'origins':[]} ]})
        self.assertEqual(catalog.classify('Регулировка ПВХ')['state'],'uncertain')


class RemarkSuggestionsTests(unittest.TestCase):
    setUp=fixture.WorkerTaskUpdatesTests.setUp
    tearDown=fixture.WorkerTaskUpdatesTests.tearDown
    login=fixture.WorkerTaskUpdatesTests.login

    def test_suggestions_require_login_project_and_writable_role(self):
        self.assertIn(self.client.get('/remarks/suggestions?q=ПВХ',headers={'Accept':'application/json'}).status_code,(401,302))
        self.login(self.worker)
        self.assertIn(self.client.get('/remarks/suggestions?q=ПВХ').status_code,(302,403))
        self.login(self.manager)
        response=self.client.get('/remarks/suggestions?q=регулиров&point=17')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['items'])
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.client.get('/remarks/suggestions?q='+('a'*501)).status_code,400)
        self.manager.project=None; self.manager.project_access_ids_json='[]';db.session.commit()
        with self.client.session_transaction() as state: state.pop('current_project_id',None)
        self.assertEqual(self.client.get('/remarks/suggestions?q=регулиров').status_code,400)


    def test_import_reference_uses_named_columns_and_excludes_contacts(self):
        from pathlib import Path
        from openpyxl import Workbook
        from app.services.remark_catalog_import import build_catalog
        with self.assertRaises(ValueError): build_catalog([])
        source=Path(self.temp_files.name)/'anonymized-reference.xlsx'
        workbook=Workbook();sheet=workbook.active;sheet.title='Таблица'
        sheet.append(['Собственник','Телефон','99. Работы по монтажу ПВХ блоков'])
        sheet.append(['OWNER_SENTINEL','+79991234567','Регулировка ПВХ'])
        other=workbook.create_sheet('Окна ПВХ');other.append(['MIRROR_SENTINEL'])
        workbook.save(source);workbook.close()
        payload,stats=build_catalog([source])
        self.assertEqual(payload['entries'][0]['points'],['17'])
        self.assertEqual(len(payload['entries']),1)
        self.assertNotIn('OWNER_SENTINEL',str(payload))
        self.assertNotIn('+79991234567',str(payload))
        self.assertNotIn('MIRROR_SENTINEL',str(payload))


    def test_review_routes_are_removed_and_navigation_has_no_link(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        for url in ('/developer/remark-review','/developer/remark-review?mode=library'):
            self.assertEqual(self.client.get(url).status_code,404)
        for url in ('/developer/remark-review/preview','/developer/remark-review/confirm',f'/developer/remark-review/{self.task.id}/keep'):
            self.assertEqual(self.client.post(url).status_code,404)
        for url in ('/site-errors','/developer/delete-logs','/developer/statistics'):
            response=self.client.get(url)
            self.assertEqual(response.status_code,200)
            self.assertNotIn('Сверка замечаний',response.text)
            self.assertNotIn('/developer/remark-review',response.text)
