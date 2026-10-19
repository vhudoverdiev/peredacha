import unittest
from unittest.mock import patch
from sqlalchemy import event

from tests import test_apartment_history_contracts as history_tests
from app import db
from app.models import Apartment, Project, Task, WorkPoint
from app.routes import _project_apartment_options, _project_concession_candidates, _open_concession_candidate_tasks


class TaskNewLoadingTests(unittest.TestCase):
    setUp = history_tests.ApartmentHistoryContractsTests.setUp
    tearDown = history_tests.ApartmentHistoryContractsTests.tearDown

    def test_chooser_does_not_load_apartments_or_candidates(self):
        with patch("app.routes._project_apartment_options", side_effect=AssertionError("unneeded query")):
            response = self.client.get("/tasks/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Автоматическое", response.get_data(as_text=True))
        self.assertIn("Ручное", response.get_data(as_text=True))

    def test_batch_candidates_match_existing_rules_with_bounded_queries(self):
        point = WorkPoint(point_number="10")
        concession = WorkPoint(point_number="26")
        other = Project(name="Other")
        db.session.add_all([point, concession, other])
        db.session.flush()
        apartments = [self.apartment] + [
            Apartment(project=self.project, apartment_number=str(n), owner_name="Owner")
            for n in range(2, 52)
        ]
        foreign = Apartment(project=other, apartment_number="1", owner_name="Other")
        db.session.add_all(apartments + [foreign])
        db.session.flush()
        for n, apartment in enumerate(apartments + [foreign]):
            db.session.add(Task(source_uid=f"candidate-{n}", project_id=apartment.project_id,
                                apartment=apartment, work_point=point, description="remark"))
        db.session.add(Task(source_uid="archived", project=self.project, apartment=self.apartment,
                            work_point=point, is_archived=True))
        db.session.add(Task(source_uid="concession", project=self.project, apartment=self.apartment,
                            work_point=concession))
        db.session.commit()
        options = _project_apartment_options(self.project.id)
        expected = {a.id: [t.id for t in _open_concession_candidate_tasks(project=self.project, apartment=a)]
                    for a in options}
        queries = []
        def record(_conn, _cursor, statement, *_args):
            queries.append(statement)
        event.listen(db.engine, "before_cursor_execute", record)
        try:
            actual = _project_concession_candidates(project=self.project, apartments=options)
            actual_ids = {key: [t.id for t in tasks] for key, tasks in actual.items()}
        finally:
            event.remove(db.engine, "before_cursor_execute", record)
        self.assertEqual(actual_ids, expected)
        self.assertLessEqual(len(queries), 3)
        for mode in ("single", "act"):
            response = self.client.get(f"/tasks/new?mode=manual&kind={mode}")
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
