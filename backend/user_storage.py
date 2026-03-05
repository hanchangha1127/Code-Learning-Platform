"""Helpers for managing per-user JSONL storage."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from backend.jsonl_storage import JSONLStorage


USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]{2,47}$")


class UserStorageManager:
    """Create and retrieve JSONL storage instances for individual users."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def normalize_username(self, username: str) -> Optional[str]:
        """Return a normalized username or ``None`` when invalid."""

        cleaned = username.strip().lower()
        if not cleaned or not USERNAME_PATTERN.match(cleaned):
            return None
        return cleaned

    def user_path(self, username: str) -> Path:
        """Return absolute path for *username*'s JSONL file."""

        return self.base_dir / f"{username}.jsonl"

    def exists(self, username: str) -> bool:
        """Return True if storage for *username* already exists."""

        return self.user_path(username).exists()

    def create_user_storage(self, username: str) -> JSONLStorage:
        """Create a new JSONL storage for *username*."""

        path = self.user_path(username)
        if path.exists():
            raise FileExistsError(f"Storage already exists for {username}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return JSONLStorage(path)

    def get_storage(self, username: str) -> JSONLStorage:
        """Return JSONL storage for *username*; raises FileNotFoundError if missing."""

        path = self.user_path(username)
        if not path.exists():
            raise FileNotFoundError(f"No storage found for {username}")
        return JSONLStorage(path)

    def delete_storage(self, username: str) -> None:
        """Delete storage for *username* if it exists."""

        path = self.user_path(username)
        if path.exists():
            path.unlink()

    def list_users(self) -> list[str]:
        """Return all usernames that have valid JSONL storage files."""

        users: list[str] = []
        for path in self.base_dir.glob("*.jsonl"):
            if not path.is_file():
                continue
            normalized = self.normalize_username(path.stem)
            if normalized is None:
                continue
            users.append(normalized)
        users.sort()
        return users
