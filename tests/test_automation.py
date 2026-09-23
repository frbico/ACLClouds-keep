import unittest

from automation import (
    extract_remaining_minutes_from_text,
    parse_cookie_header,
    parse_duration_minutes,
)


class AutomationParsingTests(unittest.TestCase):
    def test_cookie_header_parsing(self):
        cookies = parse_cookie_header("session=abc123; locale=en; empty=")
        self.assertEqual([c["name"] for c in cookies], ["session", "locale", "empty"])
        self.assertEqual(cookies[0]["value"], "abc123")

    def test_current_aclclouds_expiry_format(self):
        body = "My bot\ngolang generic\nRAM 315 MB\nExpires in 2j 3h\nRenewal will be available 2 days before expiration"
        self.assertEqual(extract_remaining_minutes_from_text(body), 2 * 1440 + 3 * 60)

    def test_legacy_english_duration(self):
        self.assertEqual(parse_duration_minutes("1d 2h 15min"), 1575)
        self.assertEqual(
            extract_remaining_minutes_from_text("Time remaining: 1d 2h 15min"),
            1575,
        )

    def test_french_and_chinese_duration(self):
        self.assertEqual(
            extract_remaining_minutes_from_text("Expire dans 1j 4h"),
            1680,
        )
        self.assertEqual(
            extract_remainining_minutes_from_text("剩余时间：2天 6小时 30分钟�),
            3270,
        )

    def test_renewal_banner_is_not_mistaken_for_expiry(self):
        body = "Renewal will be available 2 days before expiration"
        self.assertIsNone(extract_remaining_minutes_from_text(body))


if __name__ == "__main__":
    unittest.main()
