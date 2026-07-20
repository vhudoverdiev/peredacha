import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class FirefoxPreparedNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_prepared_navigation_is_desktop_firefox_only(self):
        gate = self.script.index("const isDesktopFirefoxPreparedNavigation")
        handler = self.script.index("document.addEventListener('click', async event", gate)
        section = self.script[gate:handler]

        self.assertIn("document.body?.classList.contains('app-body')", section)
        self.assertIn("isDesktopLikePointer()", section)
        self.assertIn("/Firefox\\//i.test", section)
        self.assertNotIn("isMobileViewport()", section)

    def test_prepared_html_is_consumed_once_by_the_navigation_worker(self):
        self.assertIn("const DESKTOP_NAVIGATION_CACHE = 'crm-desktop-navigation-v1'", self.worker)
        self.assertIn("requestUrl.searchParams.has('_crm_prepared_navigation')", self.worker)
        self.assertIn("preparedNavigationCache.match(request", self.worker)
        self.assertIn("preparedNavigationCache.delete(request", self.worker)
        self.assertLess(
            self.worker.index("preparedNavigationCache.match(request"),
            self.worker.index("return await fetch(request)"),
        )

    def test_page_and_worker_use_the_same_navigation_cache(self):
        page_cache = re.search(
            r"desktopFirefoxNavigationCache = '([^']+)'", self.script
        ).group(1)
        worker_cache = re.search(
            r"DESKTOP_NAVIGATION_CACHE = '([^']+)'", self.worker
        ).group(1)
        self.assertEqual(page_cache, worker_cache)

    def test_page_confirms_worker_capability_before_staging(self):
        self.assertIn("requestDesktopNavigationWorkerCapability", self.script)
        self.assertIn("crm-desktop-navigation-capability", self.script)
        self.assertIn("crm-desktop-navigation-capability-ready", self.script)
        self.assertIn("if (!await desktopNavigationWorkerCapability)", self.script)
        self.assertIn("crm-desktop-navigation-capability", self.worker)
        self.assertIn("crm-desktop-navigation-capability-ready", self.worker)

    def test_script_cache_buster_is_synchronized(self):
        script_version = re.search(
            r"script\.js'\) }}\?v=([^\"]+)", self.template
        ).group(1)

        self.assertEqual(script_version, "v640-firefox-prepared-navigation")
        self.assertIn(
            "'/static/script.js?v=v640-firefox-prepared-navigation'",
            self.worker,
        )

    def test_downloads_and_non_html_responses_are_not_staged(self):
        self.assertIn("link.hasAttribute('download')", self.script)
        self.assertIn("link.dataset.downloadMode", self.script)
        self.assertIn("contentType.toLowerCase().includes('text/html')", self.script)

    def test_prepared_response_uses_a_one_time_url_and_cleans_it_from_history(self):
        self.assertIn("navigationUrl.searchParams.set(\n      '_crm_prepared_navigation'", self.script)
        self.assertIn("searchParams.has('_crm_prepared_navigation')", self.script)
        self.assertIn("searchParams.delete('_crm_prepared_navigation')", self.script)
        self.assertIn("window.history.replaceState", self.script)


if __name__ == "__main__":
    unittest.main()
