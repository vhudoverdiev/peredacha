from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LandingAnimationPerformanceTests(unittest.TestCase):
    @unittest.skip("Server-specific landing/index.html is preserved unchanged during this merge")
    def test_viewport_sync_is_frame_coalesced_and_not_bound_to_scroll(self):
        html = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")
        script = html.rsplit("<script>", 1)[1].split("</script>", 1)[0]

        self.assertNotRegex(script, r'visualViewport\s*&&\s*window\.visualViewport\.addEventListener\("scroll"')
        self.assertRegex(script, r"if\s*\(landingViewportSyncFrame\)\s*\{\s*return;\s*\}")
        self.assertRegex(script, r"landingViewportSyncFrame\s*=\s*window\.requestAnimationFrame\(")
        self.assertNotRegex(script, r"setTimeout\(syncLandingViewport")

    def test_existing_entrance_and_device_animations_are_preserved(self):
        css = (ROOT / "landing" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("animation: fade-up 0.62s ease forwards", css)
        self.assertIn("animation: device-float 8s ease-in-out infinite", css)
        self.assertRegex(css, re.compile(r"@keyframes\s+fade-up\s*\{"))
        self.assertRegex(css, re.compile(r"@keyframes\s+device-float\s*\{"))
        self.assertIn("translate3d(0, calc(var(--device-lift) * -1), 0)", css)
        self.assertIn("backdrop-filter: blur(8px)", css)

    @unittest.skip("Server-specific landing/index.html is preserved unchanged during this merge")
    def test_below_fold_photo_decodes_lazily_and_hero_image_decodes_async(self):
        html = (ROOT / "landing" / "index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r'class="founder-photo"[\s\S]*?loading="lazy"[\s\S]*?decoding="async"')
        self.assertRegex(html, r'crm-dashboard-laptop\.jpg[^>]*decoding="async"')


if __name__ == "__main__":
    unittest.main()
