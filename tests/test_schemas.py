import unittest

from pydantic import ValidationError

from app.schemas.auth import SignUpRequest
from app.schemas.submission import SubmitRequest


class SchemaValidationTests(unittest.TestCase):
    def test_signup_rejects_short_password(self):
        with self.assertRaises(ValidationError):
            SignUpRequest(email="a@b.com", username="user_123", password="1234")

    def test_signup_rejects_invalid_username(self):
        with self.assertRaises(ValidationError):
            SignUpRequest(email="a@b.com", username="bad name", password="password123")

    def test_submit_rejects_blank_code(self):
        with self.assertRaises(ValidationError):
            SubmitRequest(language="python", code="   \n\t")

    def test_submit_accepts_valid_payload(self):
        req = SubmitRequest(language="python", code="print(1)")
        self.assertEqual(req.language, "python")


if __name__ == "__main__":
    unittest.main()
