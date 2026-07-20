import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = PROJECT_ROOT / "app" / "templates" / "base.html"
SCRIPT = PROJECT_ROOT / "app" / "static" / "script.js"
SERVICE_WORKER = PROJECT_ROOT / "app" / "static" / "service-worker.js"
DESKTOP_CSS = PROJECT_ROOT / "app" / "static" / "desktop-only.css"


class FirefoxFrameBufferedNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = BASE_TEMPLATE.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.worker = SERVICE_WORKER.read_text(encoding="utf-8")
        cls.desktop_css = DESKTOP_CSS.read_text(encoding="utf-8")

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

    def test_child_links_are_captured_by_the_persistent_host(self):
        self.assertIn(
            "frameWindow.addEventListener('click', handleDesktopFirefoxNavigationClick, true)",
            self.script,
        )
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

        frame_visible = self.script.index("frame.classList.add('is-active')")
        reveal = self.script.index(
            "startDesktopFirefoxBufferedPageAnimation(frame, frameDocument, finalUrl)",
            frame_visible,
        )
        old_frame_hidden = self.script.index(
            "desktopFirefoxActiveFrame.classList.remove('is-active')"
        )
        self.assertLess(frame_visible, reveal)
        self.assertLess(reveal, old_frame_hidden)

    def test_named_sidebar_sections_receive_a_consistent_surface_animation(self):
        expected_paths = (
            "/tasks",
            "/contractors",
            "/apartments",
            "/avr",
            "/materials",
            "/glass-measurements",
            "/assignments",
            "/site-errors",
        )
        animated_paths = self.script[
            self.script.index("const desktopFirefoxAnimatedSectionPaths") :
            self.script.index("const isTopLevelWindow")
        ]
        for path in expected_paths:
            with self.subTest(path=path):
                self.assertIn(f"'{path}'", animated_paths)
        self.assertNotIn("'/report'", animated_paths)
        self.assertNotIn("'/'", animated_paths)
        self.assertIn("desktopFirefoxAnimatedSectionPaths.has(finalUrl.pathname)", self.script)
        self.assertIn("@keyframes desktopFirefoxBufferedPageEnter", self.desktop_css)
        self.assertIn(
            "animation: desktopFirefoxBufferedPageEnter 180ms",
            self.desktop_css,
        )

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
        self.assertEqual(worker_version, "v130-dop-orange-standard")

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
        self.assertEqual(script_version, "v655-firefox-buffered-animations")
        self.assertEqual(css_version, "v58-dop-orange-standard")


if __name__ == "__main__":
    unittest.main()
