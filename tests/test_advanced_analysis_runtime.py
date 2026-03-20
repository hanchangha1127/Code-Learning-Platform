from __future__ import annotations

import unittest

from backend import learning_mode_handlers


class _FakeStorage:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def append(self, item: dict) -> None:
        self.records.append(dict(item))

    def filter(self, predicate):
        return [item for item in self.records if predicate(item)]

    def find_one(self, predicate):
        for item in self.records:
            if predicate(item):
                return item
        return None


class _FakeProblemGenerator:
    def __init__(self, files: list[dict]) -> None:
        self.files = files

    def generate_single_file_analysis_problem_sync(self, **_kwargs):
        return {
            "title": "단일 파일 분석 문제",
            "summary": "단일 파일 요약",
            "prompt": "단일 파일 흐름을 설명하세요.",
            "workspace": "single-file-analysis.workspace",
            "checklist": ["흐름", "상태", "예외"],
            "files": self.files[:1],
            "reference_report": "모범 단일 파일 리포트",
            "difficulty": "beginner",
        }

    def generate_multi_file_analysis_problem_sync(self, **_kwargs):
        return {
            "title": "다중 파일 분석 문제",
            "summary": "다중 파일 요약",
            "prompt": "다중 파일 호출 흐름을 설명하세요.",
            "workspace": "multi-file-analysis.workspace",
            "checklist": ["호출", "책임", "결합"],
            "files": self.files[:2],
            "reference_report": "모범 다중 파일 리포트",
            "difficulty": "beginner",
        }

    def generate_fullstack_analysis_problem_sync(self, **_kwargs):
        return {
            "title": "풀스택 분석 문제",
            "summary": "풀스택 요약",
            "prompt": "사용자 액션부터 UI 반영까지 설명하세요.",
            "workspace": "fullstack-analysis.workspace",
            "checklist": ["액션", "API", "서버", "UI"],
            "files": self.files,
            "reference_report": "모범 풀스택 리포트",
            "difficulty": "beginner",
        }


class _FakeAIClient:
    def analyze_advanced_analysis_report(self, **_kwargs):
        return {
            "summary": "코드 흐름을 구조적으로 설명했습니다.",
            "strengths": ["파일 간 연결을 명확히 설명했습니다."],
            "improvements": ["예외 처리 흐름을 조금 더 보완해 보세요."],
            "score": 82.0,
            "correct": True,
            "feedback_source": "ai",
            "ai_provider": "openai",
        }


class _FakeService:
    def __init__(self) -> None:
        self.storage = _FakeStorage()
        self.problem_generator = _FakeProblemGenerator(
            [
                {
                    "path": "app/main.py",
                    "name": "main.py",
                    "language": "python",
                    "role": "entrypoint",
                    "content": "def main():\n    return run()",
                },
                {
                    "path": "app/service.py",
                    "name": "service.py",
                    "language": "python",
                    "role": "service",
                    "content": "def run():\n    return 1",
                },
                {
                    "path": "frontend/page.tsx",
                    "name": "page.tsx",
                    "language": "tsx",
                    "role": "frontend",
                    "content": "export function Page() { return null; }",
                },
            ]
        )
        self.ai_client = _FakeAIClient()
        self.tier_updates = 0

    def _get_user_storage(self, _username: str):
        return self.storage

    def _update_tier_if_needed(self, _storage, _username: str) -> None:
        self.tier_updates += 1

    def _single_file_analysis_history_context(self, _storage, limit: int = 5):
        return None

    def _multi_file_analysis_history_context(self, _storage, limit: int = 5):
        return None

    def _fullstack_analysis_history_context(self, _storage, limit: int = 5):
        return None


class AdvancedAnalysisRuntimeTests(unittest.TestCase):
    def test_problem_generation_persists_reference_report_for_all_modes(self) -> None:
        service = _FakeService()
        scenarios = [
          (learning_mode_handlers.request_single_file_analysis_problem, "single_file_analysis_instance", "모범 단일 파일 리포트"),
          (learning_mode_handlers.request_multi_file_analysis_problem, "multi_file_analysis_instance", "모범 다중 파일 리포트"),
          (learning_mode_handlers.request_fullstack_analysis_problem, "fullstack_analysis_instance", "모범 풀스택 리포트"),
        ]

        for request_fn, instance_type, expected_report in scenarios:
            with self.subTest(instance_type=instance_type):
                service.storage.records.clear()
                payload = request_fn(
                    service,
                    "runtime-user",
                    "python",
                    "beginner",
                    default_track_id="algorithms",
                    difficulty_choices={"beginner": {"generator": "beginner"}},
                    utcnow=lambda: "2026-03-16T10:00:00+09:00",
                )
                self.assertTrue(payload["problemId"])
                instance = service.storage.find_one(lambda item: item.get("type") == instance_type)
                self.assertIsNotNone(instance)
                self.assertEqual(instance.get("reference_report"), expected_report)

    def test_submit_runtime_report_returns_reference_report(self) -> None:
        service = _FakeService()
        problem = learning_mode_handlers.request_single_file_analysis_problem(
            service,
            "runtime-user",
            "python",
            "beginner",
            default_track_id="algorithms",
            difficulty_choices={"beginner": {"generator": "beginner"}},
            utcnow=lambda: "2026-03-16T10:00:00+09:00",
        )

        result = learning_mode_handlers.submit_single_file_analysis_report(
            service,
            "runtime-user",
            problem["problemId"],
            "핵심 흐름과 상태 변화를 정리했습니다.",
            utcnow=lambda: "2026-03-16T10:05:00+09:00",
        )

        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["referenceReport"], "모범 단일 파일 리포트")
        self.assertEqual(result["feedbackSource"], "ai")
        self.assertEqual(result["aiProvider"], "openai")
        event = service.storage.find_one(lambda item: item.get("type") == "single_file_analysis_event")
        self.assertIsNotNone(event)
        self.assertEqual(event.get("reference_report"), "모범 단일 파일 리포트")
        self.assertEqual(event.get("feedback_source"), "ai")
        self.assertEqual(event.get("ai_provider"), "openai")
        self.assertEqual(service.tier_updates, 1)

    def test_submit_runtime_report_rejects_blank_report(self) -> None:
        service = _FakeService()
        problem = learning_mode_handlers.request_multi_file_analysis_problem(
            service,
            "runtime-user",
            "python",
            "beginner",
            default_track_id="algorithms",
            difficulty_choices={"beginner": {"generator": "beginner"}},
            utcnow=lambda: "2026-03-16T10:00:00+09:00",
        )

        with self.assertRaisesRegex(ValueError, "리포트를 입력"):
            learning_mode_handlers.submit_multi_file_analysis_report(
                service,
                "runtime-user",
                problem["problemId"],
                "   ",
                utcnow=lambda: "2026-03-16T10:05:00+09:00",
            )


if __name__ == "__main__":
    unittest.main()
