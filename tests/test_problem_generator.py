import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.problem_generator import (
    ProblemGenerator,
    _normalize_analysis_prompt,
    _normalize_analysis_reference,
    _strip_comments,
)


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


class AnalysisPromptNormalizationTests(unittest.TestCase):
    def test_normalize_analysis_prompt_rewrites_output_only_question(self):
        prompt = "이 코드의 최종 출력값은 무엇인가요?"

        normalized = _normalize_analysis_prompt(prompt)

        self.assertIn("변수 상태 변화", normalized)
        self.assertIn("최종 출력값이나 반환값만 적지 말고", normalized)

    def test_normalize_analysis_prompt_rewrites_output_value_explanation_prompt(self):
        prompt = "코드가 출력하는 값을 설명하세요."

        normalized = _normalize_analysis_prompt(prompt)

        self.assertIn("실행 흐름을 단계별로 설명", normalized)
        self.assertNotIn("출력하는 값을 설명하세요", normalized)

    def test_generate_sync_includes_reasoning_over_output_instruction(self):
        generator = ProblemGenerator()
        generator.client = object()

        captured_contents: list[str] = []

        def fake_generate(contents: str):
            captured_contents.append(contents)
            return SimpleNamespace(
                text=(
                    '{"title":"분기 추적","code":"value = 1\\nif value:\\n    print(value)",'
                    '"prompt":"조건 분기와 변수 흐름을 설명하세요.","reference":"조건이 참이라 print가 호출됩니다.","difficulty":"beginner"}'
                )
            )

        with patch.object(generator, "_generate_with_thinking", side_effect=fake_generate):
            generated = generator.generate_sync(
                problem_id="problem-1",
                track_id="algorithms",
                language_id="python",
                difficulty="beginner",
                mode="practice",
            )

        self.assertEqual(generated.prompt, "조건 분기와 변수 흐름을 설명하세요.")
        self.assertEqual(len(captured_contents), 1)
        self.assertIn("최종 출력값/반환값만 맞히게 하지 말고", captured_contents[0])
        self.assertIn("'무엇이 출력되나요?'", captured_contents[0])

    def test_generate_sync_rewrites_output_centric_prompt_from_model(self):
        generator = ProblemGenerator()
        generator.client = object()

        with patch.object(
            generator,
            "_generate_with_thinking",
            return_value=SimpleNamespace(
                text=(
                    '{"title":"출력 맞히기","code":"print(1)","prompt":"이 코드의 최종 출력값은 무엇인가요?",'
                    '"reference":"1","difficulty":"beginner"}'
                )
            ),
        ):
            generated = generator.generate_sync(
                problem_id="problem-2",
                track_id="algorithms",
                language_id="python",
                difficulty="beginner",
                mode="practice",
            )

        self.assertIn("변수 상태 변화", generated.prompt)
        self.assertNotIn("최종 출력값은 무엇인가요", generated.prompt)

    def test_normalize_analysis_reference_adds_reasoning_prefix_for_output_only_reference(self):
        reference = "최종 출력값은 1입니다."

        normalized = _normalize_analysis_reference(reference)

        self.assertIn("해설 포인트:", normalized)
        self.assertIn("실행 순서와 변수/조건의 변화", normalized)
        self.assertIn("최종 출력값은 1입니다.", normalized)


    def test_generate_code_block_problem_sync_adds_objective_hint(self):
        generator = ProblemGenerator()
        generator.client = object()

        with patch.object(
            generator,
            "_generate_with_thinking",
            return_value=SimpleNamespace(
                text=(
                    '{"title":"짝수 합계 누적","objective":"짝수 값만 더해 총합을 계산하는 반복문을 완성하세요.",'
                    '"code":"numbers = [1, 2, 3, 4]\\ntotal = 0\\nfor number in numbers:\\n    if number % 2 == 0:\\n        total = [BLANK]\\nprint(total)",'
                    '"correct_option":"total + number","wrong_options":["total - number","number"],"explanation":"짝수일 때만 현재 숫자를 누적해야 합니다."}'
                )
            ),
        ):
            generated = generator.generate_code_block_problem_sync(
                problem_id="cb-1",
                track_id="algorithms",
                language_id="python",
                difficulty="beginner",
                mode="code-block",
            )

        self.assertEqual(generated["title"], "짝수 합계 누적")
        self.assertEqual(generated["objective"], "짝수 값만 더해 총합을 계산하는 반복문을 완성하세요.")
        self.assertIn("[BLANK]", generated["code"])


if __name__ == "__main__":
    unittest.main()
