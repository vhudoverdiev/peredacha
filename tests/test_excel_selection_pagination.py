import unittest

from flask import Flask
from werkzeug.datastructures import MultiDict

from app import db
from app.models import Apartment, Project, Task, WorkPoint
from app.routes import _prepare_task_list_pagination
from app.services.task_service import build_task_query


class ExcelSelectionPaginationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)
        cls.context = cls.app.app_context()
        cls.context.push()
        db.create_all()

        project = Project(name="Pagination QA")
        point = WorkPoint(point_number="10", source_sheet_name="qa", is_active=True)
        apartments = [
            Apartment(project=project, apartment_number=str(number))
            for number in range(1, 4)
        ]
        db.session.add_all([project, point, *apartments])
        db.session.flush()

        task_counts = (7, 7, 9)
        for apartment, task_count in zip(apartments, task_counts):
            for index in range(task_count):
                db.session.add(
                    Task(
                        source_uid=f"qa-{apartment.id}-{index}",
                        project=project,
                        apartment=apartment,
                        work_point=point,
                        description="QA",
                    )
                )
        db.session.commit()
        cls.project_id = project.id
        cls.selected_apartment_ids = [apartments[0].id, apartments[1].id]

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.context.pop()

    def base_query(self):
        return build_task_query({}, project_id=self.project_id)

    def test_desktop_excel_selection_filters_before_ten_row_pagination(self):
        args = MultiDict([("excel_selection", "1")])
        for apartment_id in self.selected_apartment_ids:
            args.add("premise_ids", str(apartment_id))

        query, per_page = _prepare_task_list_pagination(
            self.base_query(), args, is_mobile_request=False
        )
        first_page = query.paginate(page=1, per_page=per_page, error_out=False)
        second_page = query.paginate(page=2, per_page=per_page, error_out=False)

        self.assertEqual(per_page, 10)
        self.assertEqual(first_page.total, 14)
        self.assertEqual(first_page.pages, 2)
        self.assertEqual(len(first_page.items), 10)
        self.assertEqual(len(second_page.items), 4)
        self.assertTrue(
            all(task.apartment_id in self.selected_apartment_ids for task in first_page.items + second_page.items)
        )

    def test_empty_desktop_selection_does_not_fall_back_to_all_tasks(self):
        query, per_page = _prepare_task_list_pagination(
            self.base_query(),
            MultiDict([("excel_selection", "1")]),
            is_mobile_request=False,
        )
        page = query.paginate(page=1, per_page=per_page, error_out=False)

        self.assertEqual(per_page, 10)
        self.assertEqual(page.total, 0)

    def test_regular_desktop_list_keeps_twenty_rows(self):
        query, per_page = _prepare_task_list_pagination(
            self.base_query(), MultiDict(), is_mobile_request=False
        )
        page = query.paginate(page=1, per_page=per_page, error_out=False)

        self.assertEqual(per_page, 20)
        self.assertEqual(page.total, 23)
        self.assertEqual(len(page.items), 20)

    def test_mobile_list_ignores_desktop_excel_selection_marker(self):
        args = MultiDict([
            ("excel_selection", "1"),
            ("premise_ids", str(self.selected_apartment_ids[0])),
        ])
        query, per_page = _prepare_task_list_pagination(
            self.base_query(), args, is_mobile_request=True
        )
        page = query.paginate(page=1, per_page=per_page, error_out=False)

        self.assertEqual(per_page, 10)
        self.assertEqual(page.total, 23)


if __name__ == "__main__":
    unittest.main()
