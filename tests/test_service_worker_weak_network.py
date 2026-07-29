import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"


class ServiceWorkerWeakNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")

    def test_navigation_has_a_bounded_network_wait(self):
        self.assertIn("const NAVIGATION_NETWORK_TIMEOUT_MS = 8000;", self.worker)
        navigation_start = self.worker.index(
            "async function navigationNetworkFirst(request)"
        )
        navigation_end = self.worker.index(
            "async function staticNetworkFirst(request)", navigation_start
        )
        navigation = self.worker[navigation_start:navigation_end]

        self.assertIn(
            "fetchWithTimeout(request, NAVIGATION_NETWORK_TIMEOUT_MS)",
            navigation,
        )
        self.assertIn("MOBILE_OFFLINE_HTML", navigation)
        self.assertIn("'X-CRM-Mobile-Offline': '1'", navigation)

    def test_timeout_aborts_the_stalled_request_and_cleans_up(self):
        helper_start = self.worker.index(
            "async function fetchWithTimeout(request, timeoutMs)"
        )
        helper_end = self.worker.index(
            "async function navigationNetworkFirst(request)", helper_start
        )
        helper = self.worker[helper_start:helper_end]

        self.assertIn("new AbortController()", helper)
        self.assertIn("setTimeout(() => controller.abort(), timeoutMs)", helper)
        self.assertIn("fetch(request, { signal: controller.signal })", helper)
        self.assertIn("clearTimeout(timeoutId)", helper)

    def test_static_assets_fall_back_to_cache_without_waiting_indefinitely(self):
        self.assertIn("const STATIC_NETWORK_TIMEOUT_MS = 6000;", self.worker)
        static_start = self.worker.index("async function staticNetworkFirst(request)")
        cache_first_start = self.worker.index(
            "async function staticCacheFirst(request)", static_start
        )
        static_network = self.worker[static_start:cache_first_start]
        static_cache = self.worker[cache_first_start:]

        self.assertIn(
            "fetchWithTimeout(request, STATIC_NETWORK_TIMEOUT_MS)",
            static_network,
        )
        self.assertIn(
            "fetchWithTimeout(request, STATIC_NETWORK_TIMEOUT_MS)",
            static_cache,
        )

    def test_lost_connection_is_reported_on_an_open_page(self):
        self.assertIn(
            "window.addEventListener('offline', () => {\n"
            "        window.crmShowOfflineFallback();\n"
            "      });",
            self.template,
        )

    def test_service_worker_cache_buster_is_updated_and_synchronized(self):
        worker_version = re.search(
            r"service-worker\.js\?v=([^']+)", self.template
        ).group(1)
        cache_version = re.search(
            r"STATIC_CACHE = 'peredacha-static-([^']+)'", self.worker
        ).group(1)

        self.assertEqual(worker_version, cache_version)
        self.assertEqual(worker_version, "v154-apartments-filtered-export")


if __name__ == "__main__":
    unittest.main()
