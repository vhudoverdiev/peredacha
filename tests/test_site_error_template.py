from pathlib import Path
import unittest


class SiteErrorTemplateTests(unittest.TestCase):
    def test_500_error_button_uses_home_label(self):
        template = Path("app/templates/site_error_500.html").read_text(encoding="utf-8")

        self.assertIn(">На главную<", template)
        self.assertNotIn(">На дашборд<", template)


if __name__ == "__main__":
    unittest.main()
