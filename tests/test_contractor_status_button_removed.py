from pathlib import Path
import unittest


class ContractorStatusButtonRemovedTests(unittest.TestCase):
    def test_remark_interfaces_do_not_render_contractor_status_action(self):
        for template_path in (
            Path("app/templates/task_list.html"),
            Path("app/templates/task_detail.html"),
            Path("app/templates/apartment_detail.html"),
        ):
            with self.subTest(template=str(template_path)):
                template = template_path.read_text(encoding="utf-8")
                self.assertNotIn("status='contractor'", template)
                self.assertNotIn('status="contractor"', template)
                self.assertNotIn('data-status-action="contractor"', template)


if __name__ == "__main__":
    unittest.main()
