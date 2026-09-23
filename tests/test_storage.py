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
        self.assertEqual(len(storage.list_accounts(include_disabled=False)), 2)

        self.assertTrue(storage.delete_account(second))
        self.assertIsNone(storage.get_account(second))
        self.assertEqual(storage.count_accounts(), 2)


if __name__ == "__main__":
    unittest.main()
