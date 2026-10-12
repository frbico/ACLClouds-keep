import tempfile
import unittest
from pathlib import Path

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
