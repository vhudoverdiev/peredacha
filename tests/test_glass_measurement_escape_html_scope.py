import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class GlassMeasurementEscapeHtmlScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.base = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_escape_helper_is_shared_before_independent_ui_initializers(self):
        helper = self.script.index("const escapeHtml = value =>")
        first_initializer = self.script.index("document.addEventListener('DOMContentLoaded'")
        glass_initializer = self.script.index(
            "const buildGlassNeedMeasureMarkup = (taskId, csrfToken)"
        )

        self.assertLess(helper, first_initializer)
        self.assertLess(helper, glass_initializer)
        self.assertEqual(self.script.count("const escapeHtml = value =>"), 1)

    def test_glass_async_fallback_escapes_server_values(self):
        start = self.script.index(
            "const buildGlassNeedMeasureMarkup = (taskId, csrfToken)"
        )
        end = self.script.index("const bindGlassAllRowActions", start)
        section = self.script[start:end]

        self.assertIn("escapeHtml(taskId)", section)
        self.assertIn("escapeHtml(csrfToken || getCsrfToken())", section)

    def test_script_cache_buster_is_synchronized(self):
        template_version = re.search(
            r"script\.js'\) }}\?v=([^\"]+)", self.base
        ).group(1)
        worker_version = re.search(
            r"/static/script\.js\?v=([^']+)", self.worker
        ).group(1)

        self.assertEqual(template_version, worker_version)


if __name__ == "__main__":
    unittest.main()
