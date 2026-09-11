import unittest

from config import Config
from app import create_app, db
from app.models import AppSetting, WorkCategory, WorkPoint
from app.services.mapping_service import (
    _mapping_custom_key,
    apply_default_point_mapping,
    ensure_default_categories,
    is_dop_agreement_header,
    is_dop_agreement_point,
    update_category_points,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "mapping-service-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class MappingServiceContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_dop_agreement_detection_uses_human_header_text_not_fixed_point_number(self):
        self.assertTrue(is_dop_agreement_header("Доп. соглашение ТМЦ"))
        self.assertTrue(is_dop_agreement_header("Отступные по ТМЦ"))
        self.assertFalse(is_dop_agreement_header("Обычный пункт 18"))

        point = WorkPoint(point_number="77", original_column_name="Доп соглашение ТМЦ")
        self.assertTrue(is_dop_agreement_point(point))
        self.assertFalse(is_dop_agreement_point(WorkPoint(point_number="18", short_name="Витражи")))
        self.assertFalse(is_dop_agreement_point(None))

    def test_ensure_default_categories_reactivates_defaults_and_deactivates_removed_or_unknown_categories(self):
        removed = WorkCategory(name="Электрики", is_active=True)
        unknown = WorkCategory(name="Legacy custom", is_active=True)
        hidden_point = WorkPoint(point_number="5", short_name="Hidden")
        visible_point = WorkPoint(point_number="10", short_name="Visible")
        dop_point = WorkPoint(point_number="99", original_column_name="Доп соглашение ТМЦ")
        unknown.work_points.extend([hidden_point, visible_point, dop_point])
        db.session.add_all([removed, unknown, hidden_point, visible_point, dop_point])
        db.session.commit()

        ensure_default_categories()
        db.session.commit()

        all_category = WorkCategory.query.filter_by(name="Все").first()
        painters = WorkCategory.query.filter_by(name="Маляры").first()
        dop = WorkCategory.query.filter_by(name="Доп.Соглашение").first()

        self.assertIsNotNone(all_category)
        self.assertTrue(all_category.is_active)
        self.assertTrue(painters.is_active)
        self.assertFalse(db.session.get(WorkCategory, removed.id).is_active)
        self.assertFalse(db.session.get(WorkCategory, unknown.id).is_active)
        self.assertIn(visible_point, painters.work_points)
        self.assertIn(dop_point, dop.work_points)
        self.assertNotIn(hidden_point, unknown.work_points)

    def test_apply_default_point_mapping_respects_customized_category(self):
        point_10 = WorkPoint(point_number="10", short_name="10")
        point_11 = WorkPoint(point_number="11", short_name="11")
        painters = WorkCategory(name="Маляры", is_active=True)
        db.session.add_all([point_10, point_11, painters])
        db.session.flush()
        db.session.add(AppSetting(key=_mapping_custom_key(painters.id), value="1"))
        db.session.commit()

        apply_default_point_mapping()

        self.assertEqual(painters.work_points, [])

    def test_update_category_points_replaces_mapping_marks_customized_and_rejects_missing_category(self):
        category = WorkCategory(name="QA")
        first = WorkPoint(point_number="10")
        second = WorkPoint(point_number="11")
        db.session.add_all([category, first, second])
        db.session.commit()

        updated = update_category_points(category.id, [second.id])

        self.assertEqual(updated.work_points, [second])
        self.assertEqual(AppSetting.query.filter_by(key=_mapping_custom_key(category.id)).first().value, "1")

        with self.assertRaises(ValueError):
            update_category_points(99999, [first.id])


if __name__ == "__main__":
    unittest.main()
