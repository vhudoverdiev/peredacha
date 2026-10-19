import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
SERVICE_WORKER = (ROOT / "app" / "static" / "service-worker.js").read_text(encoding="utf-8")


class StaticCacheContractsTests(unittest.TestCase):
    def test_static_cache_versions_match_current_stylesheets(self):
        self.assertIn("style.css') }}?v=v698-task-comments", BASE_TEMPLATE)
        self.assertIn("desktop-only.css') }}?v=v76-objects-three-columns", BASE_TEMPLATE)
        self.assertIn("peredacha-static-v188-task-comments", SERVICE_WORKER)
        self.assertIn("/static/style.css?v=v698-task-comments", SERVICE_WORKER)
        self.assertIn("/static/desktop-only.css?v=v76-objects-three-columns", SERVICE_WORKER)
        self.assertNotIn("/static/desktop-only.css?v=v75-account-back-text", SERVICE_WORKER)
        self.assertNotIn("/static/style.css?v=v652-password-generator", SERVICE_WORKER)
        self.assertNotIn("/static/desktop-only.css?v=v72-apartment-filter-single-row", SERVICE_WORKER)


if __name__ == "__main__":
    unittest.main()
