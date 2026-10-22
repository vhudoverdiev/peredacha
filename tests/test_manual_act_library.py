import re
import unittest
from werkzeug.datastructures import MultiDict
from app import db
from app.models import Task, RemarkLibraryEntry
from app.services.manual_act import collect_manual_act_entries
from app.services.remark_catalog import get_catalog
from app.services.remark_text_cleaning import clean_reference,vocabulary
from app.work_points import WORK_POINT_LABELS
import test_worker_task_updates as fixture


class ManualActCollectionTests(unittest.TestCase):
    def test_repeated_point_keeps_separate_remarks(self):
        form=MultiDict([('act_point','17'),('act_description','Первое замечание'),('act_point','17'),('act_description','Второе замечание')])
        self.assertEqual(collect_manual_act_entries(form,[{'number':'17'}]),[('17','Первое замечание'),('17','Второе замечание')])

    def test_missing_point_or_malformed_rows_rejects_whole_act(self):
        for values in [[('act_point',''),('act_description','Текст')],[('act_point','17')]]:
            with self.assertRaises(ValueError):collect_manual_act_entries(MultiDict(values),[{'number':'17'}])

    def test_legacy_forms_remain_supported(self):
        self.assertEqual(collect_manual_act_entries(MultiDict({'description_17':'Текст'}),[{'number':'17'}]),[('17','Текст')])

    def test_reference_spacing_and_capitalization(self):
        words=vocabulary(['Замена правой ручки входной двери']*3)
        for value,expected in [('требуетсязаменаправой ручки','Требуется замена правой ручки'),
                               ('требуетсярегулировкаэксцентрика','Требуется регулировка эксцентрика'),
                               ('царапины на входнойдвери','Царапины на входной двери'),
                               ('Регулировка окон (лб).','Регулировка окон'),
                               ('Замена ручки (ЛБ)','Замена ручки')]:
            self.assertEqual(clean_reference(value,words),expected)


class LibraryLearningTests(unittest.TestCase):
    def setUp(self):
        fixture.WorkerTaskUpdatesTests.setUp(self)
        db.session.query(RemarkLibraryEntry).delete();db.session.commit()

    tearDown=fixture.WorkerTaskUpdatesTests.tearDown
    login=fixture.WorkerTaskUpdatesTests.login

    def add_task(self,text,uid):
        self.point.short_name=WORK_POINT_LABELS['11']
        task=Task(source_uid=uid,project=self.project,apartment=self.apartment,work_point=self.point,description=text)
        db.session.add(task);return task

    def test_new_phrase_is_added_once_and_visible_without_restart(self):
        self.add_task('уникальная проверочная формулировка дефекта потолка','learn-1');db.session.commit()
        self.assertEqual(RemarkLibraryEntry.query.count(),1)
        self.assertTrue(any('Уникальная проверочная' in e['text'] for e in get_catalog().entries))
        self.add_task('Уникальная проверочная формулировка дефекта потолка','learn-2');db.session.commit()
        self.assertEqual(RemarkLibraryEntry.query.count(),1)
        self.assertEqual(RemarkLibraryEntry.query.one().occurrences,2)

    def test_status_change_does_not_duplicate_phrase(self):
        task=self.add_task('Новая фраза о повреждении потолка','learn-status');db.session.commit()
        before=RemarkLibraryEntry.query.one().occurrences
        task.status='done';db.session.commit()
        self.assertEqual(RemarkLibraryEntry.query.one().occurrences,before)

    def test_rollback_does_not_leave_phrase_or_cached_copy(self):
        self.add_task('Редкая отменённая формулировка потолка','learn-rollback');db.session.flush()
        get_catalog()
        db.session.rollback()
        self.assertEqual(RemarkLibraryEntry.query.count(),0)
        self.assertFalse(any('Редкая отменённая' in e['text'] for e in get_catalog().entries))

    def test_learned_phrase_does_not_prove_its_own_point_correct(self):
        self.add_task('Неведомый редкий квазидефект потолка 38195','learn-independent');db.session.commit()
        self.assertIsNone(get_catalog().classify('Неведомый редкий квазидефект потолка 38195')['target'])

    def test_act_renders_one_row_and_hides_reference_sources(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        page=self.client.get('/tasks/new?mode=manual&kind=act').text
        self.assertEqual(page.split('<template')[0].count('data-act-row>'),1)
        self.assertIn('Добавить ещё замечание',page)
        self.assertNotIn('data-act-remove',page)
        self.assertIn('btn btn-primary mt-3',page)
        self.assertEqual(self.client.get('/developer/remark-review?mode=library').status_code,404)

    def test_sequential_act_saves_two_new_remarks_under_the_same_point(self):
        self.manager.role='admin';db.session.commit();self.login(self.manager)
        data=MultiDict([('add_mode','manual'),('manual_kind','act'),('apartment_id',str(self.apartment.id)),
                        ('act_point','17'),('act_description','Регулировка оконного блока в комнате'),
                        ('act_point','17'),('act_description','Замена уплотнения оконного блока')])
        response=self.client.post('/tasks/new',data=data)
        self.assertIn(response.status_code,(302,303))
        tasks=Task.query.filter_by(source_sheet_name='manual_act').all()
        self.assertEqual(len(tasks),2)

    def test_backfill_covers_historical_archived_unknown_and_short_phrases_idempotently(self):
        from app.services.remark_learning import backfill_existing_phrases
        self.add_task('Старая формулировка повреждения стены (лб)','historical-1')
        self.add_task('Скол','historical-2')
        self.point.short_name='Особые работы';self.point.original_column_name='Особые работы'
        task=self.add_task('Исторический дефект с неизвестным пунктом','historical-3')
        from app.models import WorkPoint
        task.work_point=WorkPoint(point_number='custom',short_name='Особые работы')
        task.is_archived=True
        db.session.commit()
        db.session.query(RemarkLibraryEntry).delete();db.session.commit()
        snapshot={t.id:(t.description,t.work_point_id,t.status) for t in Task.query.all()}
        backfill_existing_phrases(force=True,batch_size=2)
        texts=[e.text for e in RemarkLibraryEntry.query.all()]
        self.assertTrue(any('Старая формулировка' in text for text in texts))
        self.assertIn('Скол',texts)
        self.assertTrue(any('неизвестным пунктом' in text for text in texts))
        self.assertTrue(all('(лб)' not in text.lower() for text in texts))
        before={e.id:(e.text,e.occurrences) for e in RemarkLibraryEntry.query.all()}
        backfill_existing_phrases(force=True,batch_size=2)
        self.assertEqual(before,{e.id:(e.text,e.occurrences) for e in RemarkLibraryEntry.query.all()})
        self.assertEqual(snapshot,{t.id:(t.description,t.work_point_id,t.status) for t in Task.query.all()})
