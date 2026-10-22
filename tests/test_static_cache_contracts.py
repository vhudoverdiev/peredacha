import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
SERVICE_WORKER = (ROOT / "app" / "static" / "service-worker.js").read_text(encoding="utf-8")


class StaticCacheContractsTests(unittest.TestCase):
    def test_static_cache_versions_match_current_stylesheets(self):
        # Compare the URLs actually rendered by the application to the PWA
        # cache manifest, so version bumps cannot leave installed apps stale.
        for filename in ("style.css", "mobile-only.css", "desktop-only.css", "workflows.css", "script.js"):
            with self.subTest(filename=filename):
                pattern = re.escape(filename) + r"['\"]\) \}\}\?v=([\w.-]+)"
                version = re.search(pattern, BASE_TEMPLATE)
                self.assertIsNotNone(version)
                self.assertIn(f"/static/{filename}?v={version.group(1)}", SERVICE_WORKER)
        worker_version = re.search(r"/service-worker\.js\?v=([\w.-]+)", BASE_TEMPLATE)
        self.assertIsNotNone(worker_version)
        self.assertIn(f"peredacha-static-{worker_version.group(1)}", SERVICE_WORKER)
        self.assertNotIn("/static/desktop-only.css?v=v75-account-back-text", SERVICE_WORKER)
        self.assertNotIn("/static/style.css?v=v652-password-generator", SERVICE_WORKER)
        self.assertNotIn("/static/desktop-only.css?v=v72-apartment-filter-single-row", SERVICE_WORKER)


if __name__ == "__main__":
    unittest.main()
