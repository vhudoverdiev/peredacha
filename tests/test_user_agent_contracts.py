import unittest

from app.services.user_agent import (
    DESKTOP_LABEL,
    PHONE_LABEL,
    TABLET_LABEL,
    is_mobile_phone_user_agent,
    visit_browser_label,
    visit_device_label,
    visit_os_label,
)


class UserAgentContractsTests(unittest.TestCase):
    def test_browser_labels_preserve_known_desktop_and_tool_agents(self):
        self.assertEqual(visit_browser_label("Mozilla/5.0 Firefox/128.0"), "Mozilla Firefox")
        self.assertEqual(visit_browser_label("Mozilla/5.0 Chrome/126.0 Safari/537.36"), "Google Chrome")
        self.assertEqual(visit_browser_label("PostmanRuntime/7.40.0"), "Postman")

    def test_os_labels_preserve_common_platform_detection_order(self):
        self.assertEqual(visit_os_label("Mozilla/5.0 (Windows NT 10.0; Win64; x64)"), "Windows")
        self.assertEqual(visit_os_label("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"), "iPhone (iOS)")
        self.assertEqual(visit_os_label("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)"), "macOS")

    def test_device_labels_distinguish_tablets_phones_and_desktop(self):
        self.assertEqual(visit_device_label("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)"), TABLET_LABEL)
        self.assertEqual(visit_device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"), PHONE_LABEL)
        self.assertEqual(visit_device_label("Mozilla/5.0 (Windows NT 10.0; Win64; x64)"), DESKTOP_LABEL)

    def test_mobile_phone_detection_excludes_tablets(self):
        self.assertTrue(is_mobile_phone_user_agent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"))
        self.assertTrue(is_mobile_phone_user_agent("Mozilla/5.0 (Linux; Android 14; Pixel 8) Mobile Safari/537.36"))
        self.assertFalse(is_mobile_phone_user_agent("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) Mobile Safari/604.1"))
        self.assertFalse(is_mobile_phone_user_agent("Mozilla/5.0 (Linux; Android 14; Tablet) Safari/537.36"))


if __name__ == "__main__":
    unittest.main()
