import unittest
from tests import test_apartment_history_contracts as fixture
from app import db
from app.models import Apartment
from app.services.task_service import parse_multi_premise_search, premise_selector_clause, premise_matches_selector

class PremiseRangeTests(unittest.TestCase):
    setUp = fixture.ApartmentHistoryContractsTests.setUp
    tearDown = fixture.ApartmentHistoryContractsTests.tearDown

    def test_range_sql_and_memory_agree_for_all_types(self):
        for kind, prefix in (("apartment", ""), ("commercial", ""), ("storeroom", "КЛ"), ("parking", "П")):
            for number in ("0", "2", "20", "21", "101", "1а"):
                db.session.add(Apartment(project=self.project, premise_type=kind, apartment_number=prefix + number))
        db.session.commit()
        apartments = Apartment.query.all()
        for text in ("1-20", "20 - 1", "1–20", "1 — 20"):
            selectors, tail = parse_multi_premise_search(text)
            self.assertEqual(selectors, [("premise_range", "1|20")])
            self.assertEqual(tail, "")
            selector = selectors[0]
            sql_ids = {a.id for a in Apartment.query.filter(premise_selector_clause(selector)).all()}
            memory_ids = {a.id for a in apartments if premise_matches_selector(a, selector)}
            self.assertEqual(sql_ids, memory_ids)
            self.assertEqual(len(sql_ids), 9)

    def test_ranges_can_be_combined_with_numbers_and_text(self):
        selectors, tail = parse_multi_premise_search("1-20, 25; 30-40 трещина")
        self.assertEqual(selectors, [("premise_range", "1|20"), ("premise_number", "25"), ("premise_range", "30|40")])
        self.assertEqual(tail, "трещина")
        self.assertEqual(parse_multi_premise_search("1-2-13")[0], [("construction_number", "1-2-13")])

if __name__ == "__main__":
    unittest.main()
