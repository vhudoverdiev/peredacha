import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"


class FirefoxPreparedNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")

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
        self.assertIn("await preparedResponse.arrayBuffer()", self.worker)
        self.assertIn("preparedNavigationCache.delete(request", self.worker)
        self.assertIn("return new Response(preparedBody", self.worker)
        self.assertLess(
            self.worker.index("preparedNavigationCache.match(request"),
            self.worker.index("return await fetch(request)"),
        )
        self.assertLess(
            self.worker.index("await preparedResponse.arrayBuffer()"),
            self.worker.index("preparedNavigationCache.delete(request"),
        )

    def test_prepared_page_dependencies_do_not_wait_for_network_revalidation(self):
        prepared_static = self.worker.index(
            "if (isPreparedDesktopNavigationSubresource(request))"
        )
        regular_static = self.worker.index("event.respondWith(staticNetworkFirst(request))")
        helper = self.worker.index(
            "function isPreparedDesktopNavigationSubresource(request)"
        )

        self.assertLess(prepared_static, regular_static)
        self.assertIn("request.referrer", self.worker[helper:])
        self.assertIn(
            "searchParams.has('_crm_prepared_navigation')",
            self.worker[helper:],
        )
        self.assertIn("event.respondWith(staticCacheFirst(request))", self.worker)

    def test_service_worker_cache_buster_is_synchronized(self):
        worker_version = re.search(
            r"service-worker\.js\?v=([^']+)", self.template
        ).group(1)
        cache_version = re.search(
            r"STATIC_CACHE = 'peredacha-static-([^']+)'", self.worker
        ).group(1)

        self.assertEqual(worker_version, cache_version)
        self.assertTrue(worker_version.startswith("v"))

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
        worker_script_version = re.search(
            r"'/static/script\.js\?v=([^']+)'", self.worker
        ).group(1)

        self.assertEqual(script_version, worker_script_version)

    def test_desktop_css_cache_buster_is_synchronized(self):
        css_version = re.search(
            r"desktop-only\.css'\) }}\?v=([^\"]+)", self.template
        ).group(1)
        worker_css_version = re.search(
            r"'/static/desktop-only\.css\?v=([^']+)'", self.worker
        ).group(1)

        self.assertEqual(css_version, worker_css_version)

    def test_downloads_and_non_html_responses_are_not_staged(self):
        self.assertIn("link.hasAttribute('download')", self.script)
        self.assertIn("link.dataset.downloadMode", self.script)
        self.assertIn("contentType.toLowerCase().includes('text/html')", self.script)

    def test_programmatic_card_navigation_uses_the_same_desktop_firefox_path(self):
        helper = self.script.index(
            "const navigateDesktopFirefoxPreparedNavigation = async targetUrl"
        )
        viewport_navigation = self.script.index(
            "const navigateWithViewportTransition = href =>"
        )
        viewport_section = self.script[viewport_navigation : viewport_navigation + 1000]

        self.assertLess(helper, viewport_navigation)
        self.assertIn("if (isDesktopFirefoxPreparedNavigation())", viewport_section)
        self.assertIn(
            "void navigateDesktopFirefoxPreparedNavigation(targetUrl)",
            viewport_section,
        )
        self.assertLess(
            viewport_section.index(
                "void navigateDesktopFirefoxPreparedNavigation(targetUrl)"
            ),
            viewport_section.rindex("window.location.href = href"),
        )

    def test_content_handoff_runs_after_staging_and_before_navigation(self):
        cache_put = self.script.index("await cache.put(cacheKey, response)")
        exit_wait = self.script.index(
            "await waitForDesktopFirefoxExitTransition()", cache_put
        )
        assign = self.script.index("window.location.assign(navigationUrl.href)")

        self.assertLess(cache_put, exit_wait)
        self.assertLess(exit_wait, assign)
        self.assertIn("prefers-reduced-motion: reduce", self.script)
        self.assertIn("event.propertyName === 'opacity'", self.script)

    def test_handoff_animates_only_the_page_surface(self):
        handoff_marker = self.desktop_css.index(
            "Firefox does not yet provide cross-document View Transitions"
        )
        handoff_css = self.desktop_css[handoff_marker:]

        self.assertIn("crm-desktop-navigation-leaving", handoff_css)
        self.assertIn("crm-desktop-navigation-entering", handoff_css)
        self.assertIn("body.app-body .crm-page-entry-surface", handoff_css)
        self.assertIn("opacity: .72 !important", handoff_css)
        self.assertIn("transition: opacity 105ms", handoff_css)
        self.assertIn("transition: opacity 170ms", handoff_css)
        self.assertIn("prefers-reduced-motion: reduce", handoff_css)
        self.assertNotIn(".app-sidebar", handoff_css)
        self.assertNotIn(".app-topbar", handoff_css)

    def test_prepared_response_uses_a_one_time_url_and_cleans_it_from_history(self):
        self.assertIn("navigationUrl.searchParams.set(\n      '_crm_prepared_navigation'", self.script)
        self.assertIn("searchParams.has('_crm_prepared_navigation')", self.script)
        self.assertIn("searchParams.delete('_crm_prepared_navigation')", self.script)
        self.assertIn("window.history.replaceState", self.script)


if __name__ == "__main__":
    unittest.main()
