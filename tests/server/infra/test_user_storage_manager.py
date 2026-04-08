import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from server.infra.user_service import UserService
from server.infra.user_storage import UserStorageManager


class UserStorageManagerTests(unittest.TestCase):
    def test_list_users_filters_invalid_entries(self):
        with TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            manager = UserStorageManager(base_dir)

            manager.create_user_storage("valid_user")
            manager.create_user_storage("guest_abc123")

            # Invalid username patterns or non-JSONL files must be ignored.
            (base_dir / "ab.jsonl").touch()
            (base_dir / "bad name.jsonl").touch()
            (base_dir / "README.txt").touch()

            self.assertEqual(manager.list_users(), ["guest_abc123", "valid_user"])

    def test_cleanup_expired_guests_removes_only_expired_guest_files(self):
        with TemporaryDirectory() as tmpdir:
            manager = UserStorageManager(Path(tmpdir))
            service = UserService(manager)

            now = datetime.now(timezone.utc)

            expired = manager.create_user_storage("guest_expired123")
            expired.append(
                {
                    "type": "user",
                    "username": "guest_expired123",
                    "guest": True,
                    "expires_at": (now - timedelta(minutes=5)).isoformat(),
                }
            )

            active = manager.create_user_storage("guest_active123")
            active.append(
                {
                    "type": "user",
                    "username": "guest_active123",
                    "guest": True,
                    "expires_at": (now + timedelta(minutes=5)).isoformat(),
                }
            )

            regular = manager.create_user_storage("member_user123")
            regular.append(
                {
                    "type": "user",
                    "username": "member_user123",
                    "guest": False,
                }
            )

            service._cleanup_expired_guests()

            self.assertFalse(manager.exists("guest_expired123"))
            self.assertTrue(manager.exists("guest_active123"))
            self.assertTrue(manager.exists("member_user123"))


if __name__ == "__main__":
    unittest.main()

