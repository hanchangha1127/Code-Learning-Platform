from __future__ import annotations

import unittest

from server_runtime.user_agent import is_mobile_user_agent


class UserAgentDetectionTests(unittest.TestCase):
    def test_iphone_is_mobile(self) -> None:
        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
        )
        self.assertTrue(is_mobile_user_agent(user_agent))

    def test_android_mobile_is_mobile(self) -> None:
        user_agent = (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
        )
        self.assertTrue(is_mobile_user_agent(user_agent))

    def test_ipad_defaults_to_desktop(self) -> None:
        user_agent = (
            "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
        )
        self.assertFalse(is_mobile_user_agent(user_agent))

    def test_desktop_browser_is_not_mobile(self) -> None:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        self.assertFalse(is_mobile_user_agent(user_agent))


if __name__ == "__main__":
    unittest.main()
