import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from app import db,create_app
from app.models import RemarkLibraryEntry,AppSetting
from app.services.remark_library_file import import_library,export_library,SCHEMA
import test_excel_import_contracts as fixture


class RemarkLibraryFileTests(unittest.TestCase):
    setUp=fixture.ExcelImportContractsTests.setUp
    tearDown=fixture.ExcelImportContractsTests.tearDown

    def test_portable_import_merges_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'library.json'
            payload={'schema':SCHEMA,'entries':[{'text':'Редкая переносимая формулировка','points':['17']},{'text':'Скол','points':[]}]}
            path.write_text(json.dumps(payload),encoding='utf-8')
            self.assertEqual(import_library(path),2)
            before=[(r.id,r.text,r.occurrences) for r in RemarkLibraryEntry.query.all()]
            self.assertEqual(import_library(path),0)
            payload['entries'].append({'text':'Ещё одна переносимая формулировка','points':['23']})
            path.write_text(json.dumps(payload),encoding='utf-8')
            self.assertEqual(import_library(path),3)
            self.assertEqual(before,[(r.id,r.text,r.occurrences) for r in RemarkLibraryEntry.query.order_by(RemarkLibraryEntry.id).limit(2)])
            self.assertEqual(RemarkLibraryEntry.query.count(),3)

    def test_invalid_update_is_atomic_and_can_be_retried(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'library.json'
            payload={'schema':SCHEMA,'entries':[{'text':'Корректная формулировка','points':['17']},{'text':'Ошибка','points':['999']}]}
            path.write_text(json.dumps(payload),encoding='utf-8')
            with self.assertRaises(ValueError):import_library(path)
            self.assertEqual(RemarkLibraryEntry.query.count(),0)
            self.assertIsNone(AppSetting.query.filter_by(key='remark_library_portable_sha256').first())
            payload['entries'].pop();path.write_text(json.dumps(payload),encoding='utf-8')
            self.assertEqual(import_library(path),1)

    def test_export_contains_only_text_and_points_without_database_ids(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'library.json'
            self.assertGreater(export_library(path),5000)
            payload=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(payload['schema'],SCHEMA)
            self.assertTrue(all(set(entry)=={'text','points'} for entry in payload['entries']))
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_startup_imports_explicit_file(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'library.json'
            path.write_text(json.dumps({'schema':SCHEMA,'entries':[{'text':'Автоматический импорт при запуске','points':['17']}]}),encoding='utf-8')
            class Config(fixture.TestConfig):
                REMARK_LIBRARY_FILE=str(path)
            app=create_app(Config)
            with app.app_context():
                self.assertEqual(RemarkLibraryEntry.query.one().text,'Автоматический импорт при запуске')
                db.session.remove();db.drop_all()
