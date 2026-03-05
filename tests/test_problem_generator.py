import unittest

from backend.problem_generator import _strip_comments


class StripCommentsTests(unittest.TestCase):
    def test_python_eof_comment_does_not_crash(self):
        text = "x = 1 # comment"
        self.assertEqual(_strip_comments(text, "python"), "x = 1")

    def test_javascript_eof_comment_does_not_crash(self):
        text = "// comment only"
        self.assertEqual(_strip_comments(text, "javascript"), "")

    def test_keeps_code_when_no_comment(self):
        text = "print('ok')"
        self.assertEqual(_strip_comments(text, "python"), "print('ok')")


if __name__ == "__main__":
    unittest.main()
