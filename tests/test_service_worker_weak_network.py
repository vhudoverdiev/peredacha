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
        self.assertIn("const NAVIGATION_NETWORK_TIMEOUT_MS = 3000;", self.worker)
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

    def test_stalled_lte_is_detected_by_real_request_not_browser_online_flag(self):
        navigation_start = self.worker.index(
            "async function navigationNetworkFirst(request)"
        )
        navigation_end = self.worker.index(
            "async function staticNetworkFirst(request)", navigation_start
        )
        navigation = self.worker[navigation_start:navigation_end]

        self.assertNotIn("navigator.onLine", self.worker)
        self.assertIn(
            "fetchWithTimeout(request, NAVIGATION_NETWORK_TIMEOUT_MS)",
            navigation,
        )
        self.assertIn("const NAVIGATION_NETWORK_TIMEOUT_MS = 3000;", self.worker)

    def test_navigation_returns_the_logo_shell_without_waiting_for_network(self):
        fetch_start = self.worker.index("self.addEventListener('fetch'")
        helper_start = self.worker.index("async function fetchWithTimeout", fetch_start)
        fetch_handler = self.worker[fetch_start:helper_start]

        self.assertIn("if (!url.searchParams.has('_crm_retry'))", fetch_handler)
        self.assertNotIn("event.clientId", fetch_handler)
        self.assertIn("event.respondWith(new Response(launchHtml", fetch_handler)
        self.assertLess(
            fetch_handler.index("event.respondWith(new Response(launchHtml"),
            fetch_handler.index("event.respondWith(navigationNetworkFirst(request))"),
        )
        self.assertIn("retryOnline(true);", self.worker)

    def test_successful_retry_marker_is_removed_before_the_next_launch(self):
        self.assertIn("currentUrl.searchParams.delete('_crm_retry');", self.template)
        self.assertIn("window.history.replaceState(null, ''", self.template)

    def test_offline_logo_uses_the_same_stable_viewport_center_as_online_logo(self):
        self.assertIn("left: 50%; top: 50vh; top: 50svh;", self.worker)
        self.assertIn("top: 50vh;\n      top: 50svh;", self.template)

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

    def test_retry_keeps_offline_card_visible_until_connection_succeeds(self):
        retry_start = self.worker.index("const retryOnline = async (initialLaunch = false) =>")
        retry_end = self.worker.index("retryButton?.addEventListener", retry_start)
        retry = self.worker[retry_start:retry_end]

        self.assertIn("showRetryProgress();", retry)
        self.assertLess(retry.index("showRetryProgress();"), retry.index("await fetch("))
        self.assertGreater(retry.rindex("showLogo();"), retry.index("if (!response.ok)"))
        self.assertNotIn("showLoader();", retry)

    def test_retry_uses_the_same_three_second_network_timeout(self):
        self.assertIn(
            "setTimeout(() => controller.abort(), 3000)",
            self.worker,
        )

    def test_service_worker_cache_buster_is_updated_and_synchronized(self):
        worker_version = re.search(
            r"service-worker\.js\?v=([^']+)", self.template
        ).group(1)
        cache_version = re.search(
            r"STATIC_CACHE = 'peredacha-static-([^']+)'", self.worker
        ).group(1)

        self.assertEqual(worker_version, cache_version)
        self.assertEqual(worker_version, "v167-instant-network-probe")


if __name__ == "__main__":
    unittest.main()
