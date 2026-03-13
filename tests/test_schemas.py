import unittest

from pydantic import ValidationError

from app.schemas.auth import SignUpRequest
from app.schemas.auditor import AuditorSubmitRequest
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

    def test_auditor_report_rejects_over_max_length(self):
        with self.assertRaises(ValidationError):
            AuditorSubmitRequest(problemId="p1", report="a" * 8001)

    def test_auditor_report_accepts_max_length(self):
        req = AuditorSubmitRequest(problemId="p1", report="a" * 8000)
        self.assertEqual(len(req.report), 8000)


if __name__ == "__main__":
    unittest.main()
