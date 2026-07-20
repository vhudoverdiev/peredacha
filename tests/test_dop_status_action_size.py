import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_LIST = PROJECT_ROOT / "app" / "templates" / "task_list.html"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
MOBILE_CSS = PROJECT_ROOT / "app" / "static" / "mobile-only.css"
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class DopStatusActionSizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task_list = TASK_LIST.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        cls.mobile_css = MOBILE_CSS.read_text(encoding="utf-8")
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_only_dop_binary_status_form_gets_the_size_hook(self):
        self.assertIn(
            "binary-status-toggle-form{% if is_dop %} dop-binary-status-toggle-form{% endif %}",
            self.task_list,
        )
        self.assertIn("data-binary-status-toggle", self.task_list)
        self.assertIn("data-done-url", self.task_list)
        self.assertIn("data-not-started-url", self.task_list)

    def test_desktop_button_is_larger_in_both_binary_states(self):
        selector = ".dop-binary-status-toggle-form .btn.btn-sm"
        start = self.desktop_css.index(selector)
        end = self.desktop_css.index("}", start)
        rule = self.desktop_css[start:end]

        self.assertIn("html.desktop-like-pointer", self.desktop_css[start - 220:start])
        self.assertIn("width: 3rem !important", rule)
        self.assertIn("height: 3rem !important", rule)
        self.assertIn("font-size: 1.2rem !important", rule)

    def test_mobile_styles_are_untouched(self):
        self.assertNotIn("dop-binary-status-toggle-form", self.mobile_css)

    def test_desktop_stylesheet_cache_buster_is_synchronized(self):
        template_version = re.search(
            r"desktop-only\.css'\) }}\?v=([^\"]+)", self.base
        ).group(1)
        worker_version = re.search(
            r"/static/desktop-only\.css\?v=([^']+)", self.worker
        ).group(1)
        self.assertEqual(template_version, worker_version)


if __name__ == "__main__":
    unittest.main()
