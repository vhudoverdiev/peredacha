import unittest

from app import create_app, db, login_manager
from app.models import Apartment, Project, ROLE_ADMIN, Task, User, WorkPoint
from config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "contractor-points-contracts-test"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


class ContractorPointsContractsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.previous_session_protection = login_manager.session_protection
        login_manager.session_protection = None
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.project = Project(name="Contractor points project")
        self.admin = User(username="admin-points", role=ROLE_ADMIN, project_id=None, all_projects_access=True)
        self.admin.set_password("correct-password")
        self.apartment_1 = Apartment(project=self.project, apartment_number="12", owner_name="Иванов")
        self.apartment_2 = Apartment(project=self.project, apartment_number="44", owner_name="Петров")
        self.point_10 = WorkPoint(point_number="10", short_name="Вентиляция", original_column_name="Вентиляция")
        self.point_11 = WorkPoint(point_number="11", short_name="Стены", original_column_name="Стены. Потолки")
        self.point_26 = WorkPoint(point_number="26", short_name="Отступное (ТМЦ)", original_column_name="Отступное (ТМЦ)")
        db.session.add_all([self.project, self.admin, self.apartment_1, self.apartment_2, self.point_10, self.point_11, self.point_26])
        db.session.flush()
        self.task_1 = Task(
            source_uid="contractor-points-1",
            project=self.project,
            apartment=self.apartment_1,
            work_point=self.point_10,
            description="Проверить вентканал в кухне.",
        )
        self.task_2 = Task(
            source_uid="contractor-points-2",
            project=self.project,
            apartment=self.apartment_2,
            work_point=self.point_11,
            description="Подшпаклевать стену в коридоре.",
        )
        db.session.add_all([self.task_1, self.task_2])
        db.session.commit()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.admin.id)
            session["_fresh"] = True
            session["session_version"] = int(self.admin.session_version or 0)
            session["current_project_id"] = self.project.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        login_manager.session_protection = self.previous_session_protection

    def test_directory_has_points_button(self):
        response = self.client.get("/contractors/directory")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('href="/contractors/points"', html)
        self.assertIn("btn btn-success remarks-page-primary-btn contractor-points-link", html)
        self.assertIn("Пункты", html)

    def test_points_page_lists_remarks_and_inline_point_selects(self):
        response = self.client.get("/contractors/points")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Проверить вентканал", html)
        self.assertIn("Подшпаклевать стену", html)
        self.assertIn("12", html)
        self.assertIn("44", html)
        self.assertIn('data-task-detail-point-autosave', html)
        self.assertIn('data-force-custom-select', html)
        self.assertNotIn('data-no-custom-select', html)
        self.assertIn(f'action="/tasks/{self.task_1.id}/point"', html)
        self.assertIn("10. Вентиляция", html)
        self.assertIn("11. Стены. Потолки", html)
        self.assertIn("26. Отступное (ТМЦ)", html)
        self.assertIn('name="point"', html)
        self.assertNotIn('name="q"', html)
        self.assertNotIn('for="contractor-points-search"', html)
        self.assertIn("Все пункты", html)
        self.assertIn("btn btn-success remarks-page-primary-btn", html)
        self.assertNotIn("Квартира, замечание, пункт, собственник", html)
        self.assertNotIn("contractor-points-sort-btn", html)

    def test_points_page_ignores_removed_search_parameter(self):
        response = self.client.get("/contractors/points", query_string={"q": "вентканал"})

        html = response.get_data(as_text=True)
        self.assertIn("Проверить вентканал", html)
        self.assertIn("Подшпаклевать стену", html)

    def test_points_page_can_filter_by_point(self):
        response = self.client.get("/contractors/points", query_string={"point": "11"})

        html = response.get_data(as_text=True)
        self.assertIn("Подшпаклевать стену", html)
        self.assertNotIn("Проверить вентканал", html)
        self.assertIn('<option value="11" selected>', html)

    def test_points_page_keeps_route_sort_without_visible_sort_button(self):
        response = self.client.get("/contractors/points", query_string={"sort": "point_desc"})

        html = response.get_data(as_text=True)
        self.assertLess(html.index("Подшпаклевать стену"), html.index("Проверить вентканал"))
        self.assertNotIn("contractor-points-sort-btn", html)

    def test_points_page_paginates_twenty_rows_and_preserves_filters(self):
        extra_apartments = []
        extra_tasks = []
        for index in range(22):
            apartment = Apartment(
                project=self.project,
                apartment_number=str(100 + index),
                owner_name=f"Собственник {index}",
            )
            task = Task(
                source_uid=f"contractor-points-page-{index}",
                project=self.project,
                apartment=apartment,
                work_point=self.point_11,
                description=f"Пагинация замечание {index}",
            )
            extra_apartments.append(apartment)
            extra_tasks.append(task)
        db.session.add_all(extra_apartments + extra_tasks)
        db.session.commit()

        response = self.client.get("/contractors/points", query_string={"point": "11"})

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Найдено замечаний: <strong>23</strong>", html)
        self.assertIn("Стр. 1 / 2", html)
        self.assertIn('class="pagination justify-content-center mb-0"', html)
        self.assertIn('>Далее</a>', html)
        self.assertEqual(html.count('aria-label="Страницы замечаний"'), 1)
        self.assertNotIn("contractor-points-pagination", html)
        self.assertIn("point=11", html)
        self.assertIn("page=2", html)
        self.assertNotIn("q=", html)
        self.assertEqual(html.count("data-task-detail-point-autosave"), 20)

    def test_points_page_orders_open_remarks_before_done(self):
        self.task_1.is_done = True
        self.task_2.is_done = False
        db.session.commit()

        response = self.client.get("/contractors/points")

        html = response.get_data(as_text=True)
        self.assertLess(html.index("Подшпаклевать стену"), html.index("Проверить вентканал"))

    def test_inline_point_update_reuses_task_point_endpoint(self):
        response = self.client.post(
            f"/tasks/{self.task_1.id}/point",
            data={"point_number": "11"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(db.session.get(Task, self.task_1.id).work_point.point_number, "11")


if __name__ == "__main__":
    unittest.main()
