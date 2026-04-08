import os
import unittest

from sqlalchemy.exc import IntegrityError

os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from server.features.auth.service import signup


class _FakeUserQuery:
    def __init__(self, db):
        self._db = db
        self._field = None
        self._value = None

    def filter(self, expression):
        self._field = getattr(getattr(expression, "left", None), "key", None)
        self._value = getattr(getattr(expression, "right", None), "value", None)
        return self

    def first(self):
        if not self._db.after_conflict:
            return None
        if self._field == "email" and self._value == self._db.conflict_email:
            return object()
        if self._field == "username" and self._value == self._db.conflict_username:
            return object()
        return None


class _FakeSignupSession:
    def __init__(self, *, conflict_email=None, conflict_username=None, raise_on_flush=False):
        self.conflict_email = conflict_email
        self.conflict_username = conflict_username
        self.raise_on_flush = raise_on_flush
        self.after_conflict = False
        self.rollback_calls = 0
        self.user = None

    def query(self, _model):
        return _FakeUserQuery(self)

    def add(self, obj):
        if obj.__class__.__name__ == "User":
            self.user = obj

    def flush(self):
        if self.raise_on_flush:
            self.after_conflict = True
            raise IntegrityError("insert", None, Exception("duplicate"))
        if self.user is not None:
            self.user.id = 11

    def commit(self):
        return None

    def rollback(self):
        self.rollback_calls += 1

    def refresh(self, _obj):
        return None


class AuthServiceTests(unittest.TestCase):
    def test_signup_translates_integrity_error_to_email_conflict(self):
        db = _FakeSignupSession(conflict_email="dup@example.com", raise_on_flush=True)

        with self.assertRaises(ValueError) as ctx:
            signup(db, "dup@example.com", "dup_user", "strong-password")

        self.assertEqual(str(ctx.exception), "email already exists")
        self.assertEqual(db.rollback_calls, 1)


if __name__ == "__main__":
    unittest.main()

