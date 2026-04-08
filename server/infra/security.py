"""Security helpers for password hashing and token generation."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass


PBKDF2_ITERATIONS = 120_000
SALT_LENGTH = 16


def hash_password(password: str) -> str:
    """Return a PBKDF2-HMAC hash containing salt and digest."""

    salt = os.urandom(SALT_LENGTH)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify that *password* matches the hashed *encoded* value."""

    try:
        algorithm, iter_str, salt_hex, hash_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(expected, derived)


def generate_token(prefix: str | None = None) -> str:
    """Generate a cryptographically secure random token, optionally namespaced."""

    token = os.urandom(24).hex()
    if prefix:
        return f"{prefix}:{token}"
    return token
