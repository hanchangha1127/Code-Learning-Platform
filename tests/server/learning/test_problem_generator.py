import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.features.learning.generator import (
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

    def test_generate_refactoring_choice_problem_sync_uses_shared_facet_taxonomy(self):
        generator = ProblemGenerator()
        generator.client = object()

        with patch.object(
            generator,
            "_request_json",
            return_value={
                "title": "최적의 선택",
                "scenario": "세 가지 구현안 중 하나를 고르세요.",
                "constraints": ["성능", "가독성"],
                "options": [
                    {"option_id": "A", "title": "A안", "code": "def solve():\n    pass  # comment"},
                    {"option_id": "B", "title": "B안", "code": "def solve_b():\n    return 1"},
                    {"option_id": "C", "title": "C안", "code": "def solve_c():\n    return 2"},
                ],
                "prompt": "가장 적절한 구현을 고르고 이유를 설명하세요.",
                "decision_facets": ["performance", "readability", "security"],
                "best_option": "A",
                "option_reviews": [
                    {"option_id": "A", "summary": "균형이 좋습니다."},
                    {"option_id": "B", "summary": "가독성이 낮습니다."},
                    {"option_id": "C", "summary": "불필요한 복잡성이 있습니다."},
                ],
                "reference_report": "A안이 가장 적절합니다.",
            },
        ):
            generated = generator.generate_refactoring_choice_problem_sync(
                problem_id="ref-1",
                track_id="algorithms",
                language_id="python",
                difficulty="beginner",
                mode="refactoring-choice",
                complexity_profile="simple",
                constraint_count=2,
            )

        self.assertEqual(generated["title"], "최적의 선택")
        self.assertEqual(generated["decision_facets"], ["performance", "readability", "security"])
        self.assertEqual(generated["options"][0]["code"], "def solve():\n    pass")

    def test_generate_code_blame_problem_sync_uses_shared_facet_taxonomy(self):
        generator = ProblemGenerator()
        generator.client = object()

        with patch.object(
            generator,
            "_request_json",
            return_value={
                "title": "범인 찾기",
                "error_log": "ValueError: boom",
                "commits": [
                    {"option_id": "A", "title": "Commit A", "diff": "diff --git a/app.py b/app.py\n@@\n-print('x')\n+raise ValueError('boom')"},
                    {"option_id": "B", "title": "Commit B", "diff": "diff --git a/app.py b/app.py\n@@\n+print('ok')"},
                    {"option_id": "C", "title": "Commit C", "diff": "diff --git a/app.py b/app.py\n@@\n+return True"},
                ],
                "prompt": "원인 커밋을 찾고 근거를 설명하세요.",
                "decision_facets": ["log_correlation", "root_cause_diff", "verification"],
                "culprit_commits": ["A"],
                "commit_reviews": [
                    {"option_id": "A", "summary": "오류를 직접 유발합니다."},
                    {"option_id": "B", "summary": "영향이 없습니다."},
                    {"option_id": "C", "summary": "무관합니다."},
                ],
                "reference_report": "A가 원인입니다.",
            },
        ):
            generated = generator.generate_code_blame_problem_sync(
                problem_id="blame-1",
                track_id="algorithms",
                language_id="python",
                difficulty="beginner",
                mode="code-blame",
                candidate_count=3,
                culprit_count=1,
                decision_facets=["log_correlation", "root_cause_diff", "verification"],
            )

        self.assertEqual(generated["title"], "범인 찾기")
        self.assertEqual(generated["culprit_commits"], ["A"])
        self.assertEqual(generated["decision_facets"], ["log_correlation", "root_cause_diff", "verification"])

    def test_generate_single_file_analysis_problem_sync_uses_shared_strip_comments_helper(self):
        generator = ProblemGenerator()
        generator.client = object()

        with patch.object(
            generator,
            "_request_json",
            return_value={
                "title": "단일 파일 분석",
                "summary": "흐름을 따라가세요.",
                "prompt": "실행 흐름을 설명하세요.",
                "workspace": "single-file-analysis.workspace",
                "checklist": ["흐름", "상태", "예외"],
                "files": [
                    {
                        "path": "src/main.py",
                        "name": "main.py",
                        "language": "python",
                        "role": "entrypoint",
                        "content": "def solve():\n    pass  # comment\n",
                    }
                ],
                "reference_report": "main.py의 흐름을 설명하세요.",
            },
        ):
            generated = generator.generate_single_file_analysis_problem_sync(
                problem_id="sfa-1",
                track_id="algorithms",
                language_id="python",
                difficulty="beginner",
                mode="single-file-analysis",
            )

        self.assertEqual(generated["files"][0]["content"], "def solve():\n    pass")


if __name__ == "__main__":
    unittest.main()
