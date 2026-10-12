import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

import automation as automation_v2
import storage as storage_v2


class AutomationTests(unittest.TestCase):
    def test_cookie_header_parsing(self):
        cookies = automation_v2.parse_cookie_header("session=abc; locale=en")
        self.assertEqual([item["name"] for item in cookies], ["session", "locale"])

    def test_server_url_validation(self):
        self.assertEqual(
            automation_v2.validate_server_url("https://aclclouds.com/server/d7ff16ce/"),
            "https://aclclouds.com/server/d7ff16ce",
        )
        self.assertIsNone(automation_v2.validate_server_url("https://example.com/server/d7ff16ce"))
        self.assertIsNone(automation_v2.validate_server_url("https://aclclouds.com/dashboard/projects"))

    def test_time_remaining_parsing(self):
        self.assertEqual(automation_v2.parse_duration_minutes("1d 23h"), 2820)
        self.assertEqual(automation_v2.parse_duration_minutes("2j 3h 5m"), 3065)
        self.assertEqual(
            automation_v2.extract_remaining_minutes_from_text(
                "bot free\nTime remaining: 1d 23h\nFree plan"
            ),
            2820,
        )
    def test_online_and_offline_states(self):
        self.assertEqual(
            automation_v2.extract_server_state_from_text("bot free\nOnline\nStart\nRestart\nStop"),
            "online",
        )
        self.assertEqual(
            automation_v2.extract_server_state_from_text("bot free\nOffline\nStart"),
            "offline",
        )
        self.assertEqual(
            automation_v2.extract_server_state_from_text("Applications\nStartup\nSettings"),
            "unknown",
        )


class BrowserControlStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        launch_options = {"headless": True}
        system_chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
        if system_chrome.exists():
            launch_options["executable_path"] = str(system_chrome)
        cls.browser = cls.playwright.chromium.launch(**launch_options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1600, "height": 1000})

    def tearDown(self):
        self.page.close()

    def test_disabled_start_with_enabled_controls_is_online(self):
        self.page.set_content(
            """
            <span style="display:none">Online</span>
            <button style="display:none">Start</button>
            <button disabled>Start</button>
            <button>Restart</button>
            <button>Stop</button>
            """
        )
        self.assertEqual(automation_v2.read_server_state(self.page), "online")

    def test_visible_enabled_start_is_offline_even_with_hidden_duplicate(self):
        self.page.set_content(
            """
            <button style="display:none">Start</button>
            <button>Start</button>
            <button disabled>Restart</button>
            <button disabled>Stop</button>
            """
        )
        state, start = automation_v2.wait_for_control_panel(self.page, timeout_seconds=2)
        self.assertEqual(state, "offline")
        self.assertIsNotNone(start)
        self.assertTrue(start.is_enabled())
        self.assertTrue(start.is_visible())

    def test_waits_for_delayed_controls_and_verifies_online_after_click(self):
        self.page.set_content('<div id="controls"></div>')
        self.page.evaluate(
            """
            () => {
              setTimeout(() => {
                document.querySelector("#controls").innerHTML =
                  '<button id="start">Start</button>' +
                  '<button id="restart" disabled>Restart</button>' +
                  '<button id="stop" disabled>Stop</button>';
                document.querySelector("#start").onclick = () => {
                  document.querySelector("#start").disabled = true;
                  document.querySelector("#restart").disabled = false;
                  document.querySelector("#stop").disabled = false;
                };
              }, 50);
            }
            """
        )
        state, start = automation_v2.wait_for_control_panel(self.page, timeout_seconds=8)
        self.assertEqual(state, "offline")
        self.assertIsNotNone(start)
        start.click()
        self.assertTrue(
            automation_v2.wait_until_online(self.page, self.page.url, timeout_seconds=5)
        )

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = storage_v2.DB_PATH
        storage_v2.DB_PATH = Path(self.temp.name) / "keeper.db"
        storage_v2.init_db()

    def tearDown(self):
        storage_v2.DB_PATH = self.original
        self.temp.cleanup()

    def test_account_keeps_bot_url_and_start_timestamp(self):
        account_id = storage_v2.create_account(
            "Bot 1",
            "encrypted",
            project_url="https://aclclouds.com/server/d7ff16ce",
        )
        storage_v2.update_account(
            account_id,
            last_status="started",
            last_renew_at="2026-10-12T00:00:00+00:00",
        )
        account = storage_v2.get_account(account_id)
        self.assertEqual(account["project_url"], "https://aclclouds.com/server/d7ff16ce")
        self.assertEqual(account["last_status"], "started")
        self.assertEqual(account["last_renew_at"], "2026-10-12T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
