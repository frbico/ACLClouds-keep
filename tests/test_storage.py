import sqlite3
import tempfile
import unittest
from pathlib import Path

import storage


class StorageAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = storage.DB_PATH
        storage.DB_PATH = Path(self.tmp.name) / "aclkeep.db"
        storage.init_db()

    def tearDown(self):
        storage.DB_PATH = self.original
        self.tmp.cleanup()

    def test_multiple_accounts_have_independent_state(self):
        first = storage.create_account("Lisa", "enc-1", next_check_at="2026-09-24T00:00:00+00:00")
        second = storage.create_account("Killy", "enc-2", next_check_at="2026-09-25T00:00:00+00:00")
        third = storage.create_account("Account 3", "enc-3", enabled=False)

        storage.update_account(first, remaining_minutes="3060", last_status="ok")
        storage.update_account(second, remaining_minutes="1440", last_status="renewed")

        accounts = storage.list_accounts()
        self.assertEqual(len(accounts), 3)
        self.assertEqual(storage.get_account(first)["remaining_minutes"], "3060")
        self.assertEqual(storage.get_account(second)["remaining_minutes"], "1440")
        self.assertFalse(storage.get_account(third)["enabled"])
        storage.update_account(
            first,
            probe_node_id="3f6c305b-0d4e-4b33-8393-39a40bdb997d",
            probe_node_name="ACLClouds-1",
            probe_status="online",
            probe_miss_count=0,
        )
        first_account = storage.get_account(first)
        self.assertEqual(first_account["probe_node_name"], "ACLClouds-1")
        self.assertEqual(first_account["probe_status"], "online")
        with self.assertRaises(sqlite3.IntegrityError):
            storage.update_account(second, probe_node_id=first_account["probe_node_id"])
        self.assertEqual(len(storage.list_accounts(include_disabled=False)), 2)

        self.assertTrue(storage.delete_account(second))
        self.assertIsNone(storage.get_account(second))
        self.assertEqual(storage.count_accounts(), 2)


    def test_existing_v2_database_is_migrated_in_place(self):
        storage.DB_PATH.unlink(missing_ok=True)
        connection = sqlite3.connect(storage.DB_PATH)
        connection.executescript(
            """
            CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            );
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cookie_enc TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                project_url TEXT NOT NULL DEFAULT '',
                remaining_minutes TEXT NOT NULL DEFAULT '',
                last_check_at TEXT NOT NULL DEFAULT '',
                last_renew_at TEXT NOT NULL DEFAULT '',
                next_check_at TEXT NOT NULL DEFAULT '',
                last_status TEXT NOT NULL DEFAULT 'never',
                last_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.close()
        storage.init_db()
        with storage.connect() as connection:
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(accounts)")
            }
        self.assertIn("probe_node_id", columns)
        self.assertIn("probe_status", columns)
        self.assertIn("next_check_reason", columns)

if __name__ == "__main__":
    unittest.main()
