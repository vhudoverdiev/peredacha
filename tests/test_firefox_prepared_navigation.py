import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"
SHARED_CSS = PROJECT_ROOT / "app" / "static" / "style.css"


class FirefoxFrameBufferedNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")
        cls.shared_css = SHARED_CSS.read_text(encoding="utf-8")

    def test_frame_buffer_is_top_level_desktop_firefox_only(self):
        gate = self.script.index("const isDesktopFirefoxFrameNavigation")
        handler = self.script.index(
            "const getDesktopFirefoxFrameNavigationUrl", gate
        )
        section = self.script[gate:handler]

        self.assertIn("isTopLevelWindow()", section)
        self.assertIn("document.body?.classList.contains('app-body')", section)
        self.assertIn("isDesktopLikePointer()", section)
        self.assertIn("/Firefox\\//i.test", section)
        self.assertNotIn("isMobileViewport()", section)

    def test_navigation_uses_two_reusable_same_origin_frames(self):
        self.assertIn("const desktopFirefoxNavigationFrames = []", self.script)
        self.assertIn("createDesktopFirefoxNavigationFrame", self.script)
        self.assertIn(
            "desktopFirefoxNavigationFrames.find(frame => frame !== desktopFirefoxActiveFrame)",
            self.script,
        )
        self.assertIn("finalUrl.origin !== window.location.origin", self.script)
        self.assertIn("frameDocument.body?.classList.contains('app-body')", self.script)

    def test_outgoing_page_stays_visible_until_loaded_frame_is_ready(self):
        load_handler = self.script.index("frame.onload = () =>")
        next_active = self.script.index("frame.classList.add('is-active')", load_handler)
        old_hidden = self.script.index(
            "desktopFirefoxActiveFrame.classList.remove('is-active')", next_active
        )

        self.assertLess(load_handler, next_active)
        self.assertLess(next_active, old_hidden)
        self.assertIn("frame.contentWindow.requestAnimationFrame", self.script)
        self.assertNotIn("crm-desktop-navigation-leaving", self.script)
        self.assertNotIn("crm-desktop-navigation-entering", self.script)

    def test_child_links_reach_partial_handlers_before_the_persistent_host(self):
        self.assertIn(
            "frameWindow.addEventListener('click', handleDesktopFirefoxNavigationClick)",
            self.script,
        )
        self.assertIn(
            "window.addEventListener('click', handleDesktopFirefoxNavigationClick)",
            self.script,
        )
        self.assertNotIn(
            "addEventListener('click', handleDesktopFirefoxNavigationClick, true)",
            self.script,
        )
        navigation_gate = self.script[
            self.script.index("const getDesktopFirefoxFrameNavigationUrl"):
            self.script.index("const createDesktopFirefoxNavigationFrame")
        ]
        self.assertIn("event.defaultPrevented", navigation_gate)
        self.assertIn("event.stopImmediatePropagation()", self.script)
        self.assertIn("window.__crmNavigateDesktopFirefoxFrame = href =>", self.script)
        self.assertIn("window.top !== window.self ? window.top : window", self.script)
        self.assertIn("requestDesktopFirefoxFrameNavigation(href)", self.script)

    def test_history_and_redirected_destination_stay_in_sync(self):
        self.assertIn("finalUrl = new URL(frame.contentWindow.location.href)", self.script)
        self.assertIn("window.history.pushState(", self.script)
        self.assertIn("crmFirefoxFrameNavigation: true", self.script)
        self.assertIn("window.addEventListener('popstate'", self.script)
        self.assertIn("{ pushHistory: false }", self.script)

    def test_downloads_and_non_page_links_keep_native_behavior(self):
        self.assertIn("link.hasAttribute('download')", self.script)
        self.assertIn("link.dataset.downloadMode", self.script)
        self.assertIn("link.hasAttribute('data-bs-toggle')", self.script)
        self.assertIn("link.target && link.target !== '_self'", self.script)

    def test_frame_layer_is_desktop_only_and_has_no_fade(self):
        marker = self.desktop_css.index(".crm-firefox-navigation-frame")
        media_start = self.desktop_css.rfind("@media (min-width: 768px)", 0, marker)
        section = self.desktop_css[media_start:]

        self.assertGreaterEqual(media_start, 0)
        self.assertIn("opacity: 0 !important", section)
        self.assertIn(".crm-firefox-navigation-frame.is-active", section)
        self.assertIn("opacity: 1 !important", section)
        self.assertIn("transition: none !important", section)
        self.assertNotIn("touch-app-device", section)

    def test_buffered_pages_pause_and_resume_existing_entry_animations(self):
        self.assertIn(
            "document.documentElement.classList.add('crm-firefox-buffered-page')",
            self.template,
        )
        self.assertIn("window.top !== window.self", self.template)
        self.assertIn(
            ".crm-firefox-buffered-page:not(.crm-firefox-buffer-revealed)",
            self.desktop_css,
        )
        self.assertIn("animation-play-state: paused !important", self.desktop_css)
        self.assertIn(
            "frameRoot.classList.add('crm-firefox-buffer-revealed')",
            self.script,
        )

        frame_visible = self.script.index("frame.classList.add('is-active')")
        reveal = self.script.index(
            "revealDesktopFirefoxBufferedPageAnimations(frameDocument)",
            frame_visible,
        )
        old_frame_hidden = self.script.index(
            "desktopFirefoxActiveFrame.classList.remove('is-active')"
        )
        self.assertLess(frame_visible, reveal)
        self.assertLess(reveal, old_frame_hidden)

    def test_all_desktop_tabs_keep_the_shared_native_entrance(self):
        self.assertIn(
            "animation: dashboardFadeUp .36s ease both",
            self.shared_css,
        )
        self.assertIn("transform: translateY(12px)", self.shared_css)
        self.assertNotIn("crm-firefox-buffer-enter", self.script)
        self.assertNotIn("crm-firefox-buffer-enter", self.desktop_css)

        blocking_rule = re.compile(
            r"html\.desktop-like-pointer body\.app-body \.crm-page-entry-surface\s*"
            r"\{[^}]*animation:\s*none\s*!important",
            re.DOTALL,
        )
        self.assertIsNone(blocking_rule.search(self.desktop_css))

    def test_obsolete_prepared_cache_path_is_removed(self):
        self.assertNotIn("desktopFirefoxNavigationCache", self.script)
        self.assertNotIn("requestDesktopNavigationWorkerCapability", self.script)
        self.assertNotIn("DESKTOP_NAVIGATION_CACHE", self.worker)
        self.assertNotIn("crm-desktop-navigation-capability", self.worker)
        self.assertNotIn("isPreparedDesktopNavigationSubresource", self.worker)

    def test_service_worker_cache_buster_is_synchronized(self):
        worker_version = re.search(
            r"service-worker\.js\?v=([^']+)", self.template
        ).group(1)
        cache_version = re.search(
            r"STATIC_CACHE = 'peredacha-static-([^']+)'", self.worker
        ).group(1)

        self.assertEqual(worker_version, cache_version)
        self.assertEqual(worker_version, "v133-preserve-partial-navigation")

    def test_script_and_css_cache_busters_are_synchronized(self):
        script_version = re.search(
            r"script\.js'\) }}\?v=([^\"]+)", self.template
        ).group(1)
        worker_script_version = re.search(
            r"'/static/script\.js\?v=([^']+)'", self.worker
        ).group(1)
        css_version = re.search(
            r"desktop-only\.css'\) }}\?v=([^\"]+)", self.template
        ).group(1)
        worker_css_version = re.search(
            r"'/static/desktop-only\.css\?v=([^']+)'", self.worker
        ).group(1)

        self.assertEqual(script_version, worker_script_version)
        self.assertEqual(css_version, worker_css_version)
        self.assertEqual(script_version, "v658-preserve-partial-navigation")
        self.assertEqual(css_version, "v60-restore-desktop-entry")


if __name__ == "__main__":
    unittest.main()
