from __future__ import annotations

import unittest

from backend.content import LANGUAGES, normalize_language_id


class LanguageCatalogTests(unittest.TestCase):
    def test_requested_languages_are_available(self) -> None:
        for language_id in ("typescript", "cpp", "csharp", "go", "rust", "php", "golfscript"):
            with self.subTest(language_id=language_id):
                self.assertIn(language_id, LANGUAGES)

    def test_aliases_normalize_to_canonical_language_ids(self) -> None:
        self.assertEqual(normalize_language_id("c++"), "cpp")
        self.assertEqual(normalize_language_id("cs"), "csharp")
        self.assertEqual(normalize_language_id("C#"), "csharp")
        self.assertEqual(normalize_language_id("TS"), "typescript")
        self.assertEqual(normalize_language_id("gs"), "golfscript")


if __name__ == "__main__":
    unittest.main()
