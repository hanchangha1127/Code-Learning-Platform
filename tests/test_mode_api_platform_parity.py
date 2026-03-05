from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

# Ensure settings validation passes during imports.
os.environ.setdefault("DB_PASSWORD", "test-db-password")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-value-12345678901234567890")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_NAME", "code_platform")
os.environ.setdefault("DB_USER", "appuser")

from app.api.deps import get_db
from app.api.security_deps import get_current_user
from app.main import app as platform_backend_app
from server_runtime.deps import get_current_username
from server_runtime.webapp import app


def _shape(value):
    if isinstance(value, dict):
        return {key: _shape(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "null"
    return type(value).__name__


class ModeApiPlatformParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        app.dependency_overrides[get_current_username] = lambda: "parity_user"
        platform_backend_app.dependency_overrides[get_db] = lambda: SimpleNamespace()
        platform_backend_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        platform_backend_app.dependency_overrides.clear()

    def _assert_json_shape_parity(
        self,
        *,
        api_path: str,
        platform_path: str,
        request_payload: dict,
        api_patch_target: str,
        platform_patch_target: str,
        response_payload: dict,
    ) -> None:
        with (
            patch(api_patch_target, return_value=response_payload),
            patch(platform_patch_target, return_value=response_payload),
        ):
            api_response = self.client.post(api_path, json=request_payload)
            platform_response = self.client.post(platform_path, json=request_payload)

        self.assertEqual(api_response.status_code, 200, api_response.text)
        self.assertEqual(platform_response.status_code, 200, platform_response.text)

        api_json = api_response.json()
        platform_json = platform_response.json()
        self.assertEqual(set(api_json.keys()), set(platform_json.keys()))
        self.assertEqual(_shape(api_json), _shape(platform_json))

    def test_problem_response_shape_parity(self):
        scenarios = [
            {
                "api_path": "/api/auditor/problem",
                "platform_path": "/platform/auditor/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_auditor_problem",
                "platform_patch_target": "app.api.routes.auditor.create_auditor_problem",
                "request_payload": {"language": "python", "difficulty": "beginner"},
                "response_payload": {
                    "problemId": "aud-1",
                    "title": "감사관 문제",
                    "language": "python",
                    "difficulty": "beginner",
                    "code": "def solve():\n    return True",
                    "prompt": "함정을 찾아보세요.",
                    "trapCount": 1,
                },
            },
            {
                "api_path": "/api/context-inference/problem",
                "platform_path": "/platform/context-inference/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_context_inference_problem",
                "platform_patch_target": "app.api.routes.context_inference.create_context_inference_problem",
                "request_payload": {"language": "python", "difficulty": "intermediate"},
                "response_payload": {
                    "problemId": "ctx-1",
                    "title": "맥락 추론 문제",
                    "language": "python",
                    "difficulty": "intermediate",
                    "snippet": "def apply(x):\n    return x + 1",
                    "prompt": "실행 전 상태를 추론하세요.",
                    "inferenceType": "pre_condition",
                },
            },
            {
                "api_path": "/api/refactoring-choice/problem",
                "platform_path": "/platform/refactoring-choice/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_refactoring_choice_problem",
                "platform_patch_target": "app.api.routes.refactoring_choice.create_refactoring_choice_problem",
                "request_payload": {"language": "python", "difficulty": "advanced"},
                "response_payload": {
                    "problemId": "ref-1",
                    "title": "최적의 선택 문제",
                    "language": "python",
                    "difficulty": "advanced",
                    "scenario": "메모리가 제한된 환경",
                    "constraints": ["메모리 제한", "응답 지연 최소화"],
                    "options": [
                        {"optionId": "A", "title": "A안", "code": "pass"},
                        {"optionId": "B", "title": "B안", "code": "pass"},
                        {"optionId": "C", "title": "C안", "code": "pass"},
                    ],
                    "prompt": "최적안을 선택하세요.",
                    "decisionFacets": ["memory", "performance", "maintainability"],
                },
            },
            {
                "api_path": "/api/code-blame/problem",
                "platform_path": "/platform/code-blame/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_code_blame_problem",
                "platform_patch_target": "app.api.routes.code_blame.create_code_blame_problem",
                "request_payload": {"language": "python", "difficulty": "advanced"},
                "response_payload": {
                    "problemId": "blame-1",
                    "title": "범인 찾기 문제",
                    "language": "python",
                    "difficulty": "advanced",
                    "errorLog": "Traceback...",
                    "commits": [
                        {"optionId": "A", "title": "A commit", "diff": "diff --git a/a b/a"},
                        {"optionId": "B", "title": "B commit", "diff": "diff --git a/b b/b"},
                        {"optionId": "C", "title": "C commit", "diff": "diff --git a/c b/c"},
                        {"optionId": "D", "title": "D commit", "diff": "diff --git a/d b/d"},
                        {"optionId": "E", "title": "E commit", "diff": "diff --git a/e b/e"},
                    ],
                    "prompt": "범인 커밋을 추리하세요.",
                    "decisionFacets": ["log_correlation", "root_cause_diff", "failure_mechanism"],
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["api_path"]):
                self._assert_json_shape_parity(**scenario)

    def test_submit_response_shape_parity(self):
        scenarios = [
            {
                "api_path": "/api/auditor/submit",
                "platform_path": "/platform/auditor/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_auditor_report",
                "platform_patch_target": "app.api.routes.auditor.submit_auditor_report",
                "request_payload": {"problemId": "aud-1", "report": "리포트"},
                "response_payload": {
                    "correct": True,
                    "score": 82.5,
                    "verdict": "passed",
                    "feedback": {"summary": "좋습니다.", "strengths": ["핵심 지적"], "improvements": ["보완점"]},
                    "foundTypes": ["logic_error"],
                    "missedTypes": ["injection_risk"],
                    "referenceReport": "모범 리포트",
                    "passThreshold": 70,
                },
            },
            {
                "api_path": "/api/context-inference/submit",
                "platform_path": "/platform/context-inference/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_context_inference_report",
                "platform_patch_target": "app.api.routes.context_inference.submit_context_inference_report",
                "request_payload": {"problemId": "ctx-1", "report": "리포트"},
                "response_payload": {
                    "correct": False,
                    "score": 65.0,
                    "verdict": "failed",
                    "feedback": {"summary": "보완 필요", "strengths": ["입력 추론"], "improvements": ["영향 분석"]},
                    "foundTypes": ["input_shape"],
                    "missedTypes": ["state_transition"],
                    "referenceReport": "모범 추론",
                    "passThreshold": 70,
                },
            },
            {
                "api_path": "/api/refactoring-choice/submit",
                "platform_path": "/platform/refactoring-choice/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_refactoring_choice_report",
                "platform_patch_target": "app.api.routes.refactoring_choice.submit_refactoring_choice_report",
                "request_payload": {"problemId": "ref-1", "selectedOption": "A", "report": "리포트"},
                "response_payload": {
                    "correct": True,
                    "score": 90.0,
                    "verdict": "passed",
                    "feedback": {"summary": "선택 근거 우수", "strengths": ["제약 반영"], "improvements": ["보안 고려"]},
                    "foundTypes": ["memory", "performance"],
                    "missedTypes": ["security"],
                    "referenceReport": "모범 의사결정",
                    "passThreshold": 70,
                    "selectedOption": "A",
                    "bestOption": "A",
                    "optionReviews": [
                        {"optionId": "A", "summary": "최적안"},
                        {"optionId": "B", "summary": "차선"},
                        {"optionId": "C", "summary": "비추천"},
                    ],
                },
            },
            {
                "api_path": "/api/code-blame/submit",
                "platform_path": "/platform/code-blame/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_code_blame_report",
                "platform_patch_target": "app.api.routes.code_blame.submit_code_blame_report",
                "request_payload": {"problemId": "blame-1", "selectedCommits": ["B"], "report": "리포트"},
                "response_payload": {
                    "correct": True,
                    "score": 88.0,
                    "verdict": "passed",
                    "feedback": {"summary": "로그 상관분석이 정확", "strengths": ["원인 특정"], "improvements": ["검증 전략 강화"]},
                    "foundTypes": ["log_correlation", "root_cause_diff"],
                    "missedTypes": ["verification"],
                    "referenceReport": "모범 장애 분석",
                    "passThreshold": 70,
                    "selectedCommits": ["B"],
                    "culpritCommits": ["B"],
                    "commitReviews": [
                        {"optionId": "A", "summary": "비관련"},
                        {"optionId": "B", "summary": "핵심 원인"},
                        {"optionId": "C", "summary": "부수적"},
                        {"optionId": "D", "summary": "비관련"},
                        {"optionId": "E", "summary": "비관련"},
                    ],
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["api_path"]):
                self._assert_json_shape_parity(**scenario)

    def _assert_frontend_keys(self, payload: dict, required_keys: set[str], expected_types: dict[str, type]) -> None:
        missing = required_keys.difference(payload.keys())
        self.assertEqual(missing, set(), f"Missing frontend keys: {sorted(missing)}")
        for key, expected_type in expected_types.items():
            self.assertIsInstance(payload[key], expected_type, f"{key} should be {expected_type.__name__}")

    def test_problem_response_frontend_contract_keys(self):
        scenarios = [
            {
                "api_path": "/api/auditor/problem",
                "platform_path": "/platform/auditor/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_auditor_problem",
                "platform_patch_target": "app.api.routes.auditor.create_auditor_problem",
                "request_payload": {"language": "python", "difficulty": "beginner"},
                "response_payload": {
                    "problemId": "aud-1",
                    "title": "Auditor Problem",
                    "language": "python",
                    "difficulty": "beginner",
                    "code": "def solve():\n    return True",
                    "prompt": "Find suspicious parts.",
                    "trapCount": 2,
                },
                "required_keys": {"problemId", "title", "language", "difficulty", "code", "prompt", "trapCount"},
                "expected_types": {
                    "problemId": str,
                    "title": str,
                    "language": str,
                    "difficulty": str,
                    "code": str,
                    "prompt": str,
                    "trapCount": int,
                },
            },
            {
                "api_path": "/api/context-inference/problem",
                "platform_path": "/platform/context-inference/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_context_inference_problem",
                "platform_patch_target": "app.api.routes.context_inference.create_context_inference_problem",
                "request_payload": {"language": "python", "difficulty": "intermediate"},
                "response_payload": {
                    "problemId": "ctx-1",
                    "title": "Context Inference Problem",
                    "language": "python",
                    "difficulty": "intermediate",
                    "snippet": "def f(x):\n    return x + 1",
                    "prompt": "Infer pre/post state.",
                    "inferenceType": "pre_condition",
                },
                "required_keys": {"problemId", "title", "language", "difficulty", "snippet", "prompt", "inferenceType"},
                "expected_types": {
                    "problemId": str,
                    "title": str,
                    "language": str,
                    "difficulty": str,
                    "snippet": str,
                    "prompt": str,
                    "inferenceType": str,
                },
            },
            {
                "api_path": "/api/refactoring-choice/problem",
                "platform_path": "/platform/refactoring-choice/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_refactoring_choice_problem",
                "platform_patch_target": "app.api.routes.refactoring_choice.create_refactoring_choice_problem",
                "request_payload": {"language": "python", "difficulty": "advanced"},
                "response_payload": {
                    "problemId": "ref-1",
                    "title": "Refactoring Choice Problem",
                    "language": "python",
                    "difficulty": "advanced",
                    "scenario": "Memory constrained environment",
                    "constraints": ["memory", "latency"],
                    "options": [
                        {"optionId": "A", "title": "Option A", "code": "pass"},
                        {"optionId": "B", "title": "Option B", "code": "pass"},
                        {"optionId": "C", "title": "Option C", "code": "pass"},
                    ],
                    "prompt": "Pick the best option.",
                    "decisionFacets": ["memory", "performance", "maintainability"],
                },
                "required_keys": {
                    "problemId",
                    "title",
                    "language",
                    "difficulty",
                    "scenario",
                    "constraints",
                    "options",
                    "prompt",
                    "decisionFacets",
                },
                "expected_types": {
                    "problemId": str,
                    "title": str,
                    "language": str,
                    "difficulty": str,
                    "scenario": str,
                    "constraints": list,
                    "options": list,
                    "prompt": str,
                    "decisionFacets": list,
                },
            },
            {
                "api_path": "/api/code-blame/problem",
                "platform_path": "/platform/code-blame/problem",
                "api_patch_target": "server_runtime.routes.learning.learning_service.request_code_blame_problem",
                "platform_patch_target": "app.api.routes.code_blame.create_code_blame_problem",
                "request_payload": {"language": "python", "difficulty": "advanced"},
                "response_payload": {
                    "problemId": "blame-1",
                    "title": "Code Blame Problem",
                    "language": "python",
                    "difficulty": "advanced",
                    "errorLog": "Traceback...",
                    "commits": [
                        {"optionId": "A", "title": "A commit", "diff": "diff --git a/a b/a"},
                        {"optionId": "B", "title": "B commit", "diff": "diff --git a/b b/b"},
                        {"optionId": "C", "title": "C commit", "diff": "diff --git a/c b/c"},
                        {"optionId": "D", "title": "D commit", "diff": "diff --git a/d b/d"},
                        {"optionId": "E", "title": "E commit", "diff": "diff --git a/e b/e"},
                    ],
                    "prompt": "Find culprit commits.",
                    "decisionFacets": ["log_correlation", "root_cause_diff", "failure_mechanism"],
                },
                "required_keys": {
                    "problemId",
                    "title",
                    "language",
                    "difficulty",
                    "errorLog",
                    "commits",
                    "prompt",
                    "decisionFacets",
                },
                "expected_types": {
                    "problemId": str,
                    "title": str,
                    "language": str,
                    "difficulty": str,
                    "errorLog": str,
                    "commits": list,
                    "prompt": str,
                    "decisionFacets": list,
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["api_path"]):
                with (
                    patch(scenario["api_patch_target"], return_value=scenario["response_payload"]),
                    patch(scenario["platform_patch_target"], return_value=scenario["response_payload"]),
                ):
                    api_response = self.client.post(scenario["api_path"], json=scenario["request_payload"])
                    platform_response = self.client.post(scenario["platform_path"], json=scenario["request_payload"])

                self.assertEqual(api_response.status_code, 200, api_response.text)
                self.assertEqual(platform_response.status_code, 200, platform_response.text)
                self._assert_frontend_keys(api_response.json(), scenario["required_keys"], scenario["expected_types"])
                self._assert_frontend_keys(platform_response.json(), scenario["required_keys"], scenario["expected_types"])

    def test_submit_response_frontend_contract_keys(self):
        scenarios = [
            {
                "api_path": "/api/auditor/submit",
                "platform_path": "/platform/auditor/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_auditor_report",
                "platform_patch_target": "app.api.routes.auditor.submit_auditor_report",
                "request_payload": {"problemId": "aud-1", "report": "report"},
                "response_payload": {
                    "correct": True,
                    "score": 81.5,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": ["coverage"], "improvements": ["depth"]},
                    "foundTypes": ["logic_error"],
                    "missedTypes": ["injection_risk"],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                },
                "required_keys": {
                    "correct",
                    "score",
                    "verdict",
                    "feedback",
                    "foundTypes",
                    "missedTypes",
                    "referenceReport",
                    "passThreshold",
                },
                "expected_types": {
                    "correct": bool,
                    "score": float,
                    "verdict": str,
                    "feedback": dict,
                    "foundTypes": list,
                    "missedTypes": list,
                    "referenceReport": str,
                    "passThreshold": int,
                },
            },
            {
                "api_path": "/api/context-inference/submit",
                "platform_path": "/platform/context-inference/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_context_inference_report",
                "platform_patch_target": "app.api.routes.context_inference.submit_context_inference_report",
                "request_payload": {"problemId": "ctx-1", "report": "report"},
                "response_payload": {
                    "correct": False,
                    "score": 66.0,
                    "verdict": "failed",
                    "feedback": {"summary": "ok", "strengths": ["coverage"], "improvements": ["depth"]},
                    "foundTypes": ["state_transition"],
                    "missedTypes": ["post_condition"],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                },
                "required_keys": {
                    "correct",
                    "score",
                    "verdict",
                    "feedback",
                    "foundTypes",
                    "missedTypes",
                    "referenceReport",
                    "passThreshold",
                },
                "expected_types": {
                    "correct": bool,
                    "score": float,
                    "verdict": str,
                    "feedback": dict,
                    "foundTypes": list,
                    "missedTypes": list,
                    "referenceReport": str,
                    "passThreshold": int,
                },
            },
            {
                "api_path": "/api/refactoring-choice/submit",
                "platform_path": "/platform/refactoring-choice/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_refactoring_choice_report",
                "platform_patch_target": "app.api.routes.refactoring_choice.submit_refactoring_choice_report",
                "request_payload": {"problemId": "ref-1", "selectedOption": "A", "report": "report"},
                "response_payload": {
                    "correct": True,
                    "score": 90.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": ["coverage"], "improvements": ["depth"]},
                    "foundTypes": ["memory"],
                    "missedTypes": ["security"],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                    "selectedOption": "A",
                    "bestOption": "A",
                    "optionReviews": [
                        {"optionId": "A", "summary": "best"},
                        {"optionId": "B", "summary": "ok"},
                        {"optionId": "C", "summary": "worse"},
                    ],
                },
                "required_keys": {
                    "correct",
                    "score",
                    "verdict",
                    "feedback",
                    "foundTypes",
                    "missedTypes",
                    "referenceReport",
                    "passThreshold",
                    "selectedOption",
                    "bestOption",
                    "optionReviews",
                },
                "expected_types": {
                    "correct": bool,
                    "score": float,
                    "verdict": str,
                    "feedback": dict,
                    "foundTypes": list,
                    "missedTypes": list,
                    "referenceReport": str,
                    "passThreshold": int,
                    "selectedOption": str,
                    "bestOption": str,
                    "optionReviews": list,
                },
            },
            {
                "api_path": "/api/code-blame/submit",
                "platform_path": "/platform/code-blame/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_code_blame_report",
                "platform_patch_target": "app.api.routes.code_blame.submit_code_blame_report",
                "request_payload": {"problemId": "blame-1", "selectedCommits": ["A"], "report": "report"},
                "response_payload": {
                    "correct": True,
                    "score": 88.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": ["coverage"], "improvements": ["depth"]},
                    "foundTypes": ["root_cause_diff"],
                    "missedTypes": ["verification"],
                    "referenceReport": "reference",
                    "passThreshold": 70,
                    "selectedCommits": ["A"],
                    "culpritCommits": ["A"],
                    "commitReviews": [
                        {"optionId": "A", "summary": "root cause"},
                        {"optionId": "B", "summary": "not related"},
                        {"optionId": "C", "summary": "not related"},
                        {"optionId": "D", "summary": "not related"},
                        {"optionId": "E", "summary": "not related"},
                    ],
                },
                "required_keys": {
                    "correct",
                    "score",
                    "verdict",
                    "feedback",
                    "foundTypes",
                    "missedTypes",
                    "referenceReport",
                    "passThreshold",
                    "selectedCommits",
                    "culpritCommits",
                    "commitReviews",
                },
                "expected_types": {
                    "correct": bool,
                    "score": float,
                    "verdict": str,
                    "feedback": dict,
                    "foundTypes": list,
                    "missedTypes": list,
                    "referenceReport": str,
                    "passThreshold": int,
                    "selectedCommits": list,
                    "culpritCommits": list,
                    "commitReviews": list,
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["api_path"]):
                with (
                    patch("app.api.routes.platform_mode_queue.is_rq_enabled", return_value=False),
                    patch(scenario["api_patch_target"], return_value=scenario["response_payload"]),
                    patch(scenario["platform_patch_target"], return_value=scenario["response_payload"]),
                ):
                    api_response = self.client.post(scenario["api_path"], json=scenario["request_payload"])
                    platform_response = self.client.post(scenario["platform_path"], json=scenario["request_payload"])

                self.assertEqual(api_response.status_code, 200, api_response.text)
                self.assertEqual(platform_response.status_code, 200, platform_response.text)
                self._assert_frontend_keys(api_response.json(), scenario["required_keys"], scenario["expected_types"])
                self._assert_frontend_keys(platform_response.json(), scenario["required_keys"], scenario["expected_types"])

    def test_submit_frontend_payload_aliases_are_accepted_for_all_modes(self):
        scenarios = [
            {
                "api_path": "/api/auditor/submit",
                "platform_path": "/platform/auditor/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_auditor_report",
                "platform_patch_target": "app.api.routes.auditor.submit_auditor_report",
                "request_payload": {"problemId": "aud-1", "report": "frontend report"},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                },
            },
            {
                "api_path": "/api/context-inference/submit",
                "platform_path": "/platform/context-inference/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_context_inference_report",
                "platform_patch_target": "app.api.routes.context_inference.submit_context_inference_report",
                "request_payload": {"problemId": "ctx-1", "report": "frontend report"},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                },
            },
            {
                "api_path": "/api/refactoring-choice/submit",
                "platform_path": "/platform/refactoring-choice/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_refactoring_choice_report",
                "platform_patch_target": "app.api.routes.refactoring_choice.submit_refactoring_choice_report",
                "request_payload": {"problemId": "ref-1", "selectedOption": "B", "report": "frontend report"},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                    "selectedOption": "B",
                    "bestOption": "B",
                    "optionReviews": [{"optionId": "A", "summary": "alt"}, {"optionId": "B", "summary": "best"}, {"optionId": "C", "summary": "alt"}],
                },
            },
            {
                "api_path": "/api/code-blame/submit",
                "platform_path": "/platform/code-blame/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_code_blame_report",
                "platform_patch_target": "app.api.routes.code_blame.submit_code_blame_report",
                "request_payload": {"problemId": "blame-1", "selectedCommits": ["A"], "report": "frontend report"},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                    "selectedCommits": ["A"],
                    "culpritCommits": ["A"],
                    "commitReviews": [
                        {"optionId": "A", "summary": "root cause"},
                        {"optionId": "B", "summary": "noise"},
                        {"optionId": "C", "summary": "noise"},
                        {"optionId": "D", "summary": "noise"},
                        {"optionId": "E", "summary": "noise"},
                    ],
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(path=scenario["api_path"]):
                with (
                    patch("app.api.routes.platform_mode_queue.is_rq_enabled", return_value=False),
                    patch(scenario["api_patch_target"], return_value=scenario["response_payload"]) as api_mock,
                    patch(scenario["platform_patch_target"], return_value=scenario["response_payload"]) as platform_mock,
                ):
                    api_response = self.client.post(scenario["api_path"], json=scenario["request_payload"])
                    platform_response = self.client.post(scenario["platform_path"], json=scenario["request_payload"])

                self.assertEqual(api_response.status_code, 200, api_response.text)
                self.assertEqual(platform_response.status_code, 200, platform_response.text)
                api_mock.assert_called_once()
                platform_mock.assert_called_once()

    def test_submit_payload_normalization_matches_frontend_expectations(self):
        scenarios = [
            {
                "mode": "auditor",
                "api_path": "/api/auditor/submit",
                "platform_path": "/platform/auditor/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_auditor_report",
                "platform_patch_target": "app.api.routes.auditor.submit_auditor_report",
                "request_payload": {"problemId": "  aud-1  ", "report": "  report body  "},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                },
                "expected_api_args": ("parity_user", "aud-1", "report body"),
                "expected_platform_kwargs": {"user_id": 1, "problem_id": "aud-1", "report": "report body"},
            },
            {
                "mode": "context-inference",
                "api_path": "/api/context-inference/submit",
                "platform_path": "/platform/context-inference/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_context_inference_report",
                "platform_patch_target": "app.api.routes.context_inference.submit_context_inference_report",
                "request_payload": {"problemId": "  ctx-1  ", "report": "  report body  "},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                },
                "expected_api_args": ("parity_user", "ctx-1", "report body"),
                "expected_platform_kwargs": {"user_id": 1, "problem_id": "ctx-1", "report": "report body"},
            },
            {
                "mode": "refactoring-choice",
                "api_path": "/api/refactoring-choice/submit",
                "platform_path": "/platform/refactoring-choice/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_refactoring_choice_report",
                "platform_patch_target": "app.api.routes.refactoring_choice.submit_refactoring_choice_report",
                "request_payload": {"problemId": "  ref-1  ", "selectedOption": "  b  ", "report": "  report body  "},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                    "selectedOption": "B",
                    "bestOption": "B",
                    "optionReviews": [{"optionId": "A", "summary": "alt"}, {"optionId": "B", "summary": "best"}, {"optionId": "C", "summary": "alt"}],
                },
                "expected_api_args": ("parity_user", "ref-1", "B", "report body"),
                "expected_platform_kwargs": {"user_id": 1, "problem_id": "ref-1", "selected_option": "B", "report": "report body"},
            },
            {
                "mode": "code-blame",
                "api_path": "/api/code-blame/submit",
                "platform_path": "/platform/code-blame/submit",
                "api_patch_target": "server_runtime.routes.learning.learning_service.submit_code_blame_report",
                "platform_patch_target": "app.api.routes.code_blame.submit_code_blame_report",
                "request_payload": {"problemId": "  blame-1  ", "selectedCommits": [" a ", " c "], "report": "  report body  "},
                "response_payload": {
                    "correct": True,
                    "score": 80.0,
                    "verdict": "passed",
                    "feedback": {"summary": "ok", "strengths": [], "improvements": []},
                    "foundTypes": [],
                    "missedTypes": [],
                    "referenceReport": "ref",
                    "passThreshold": 70,
                    "selectedCommits": ["A", "C"],
                    "culpritCommits": ["A"],
                    "commitReviews": [
                        {"optionId": "A", "summary": "root cause"},
                        {"optionId": "B", "summary": "noise"},
                        {"optionId": "C", "summary": "noise"},
                        {"optionId": "D", "summary": "noise"},
                        {"optionId": "E", "summary": "noise"},
                    ],
                },
                "expected_api_args": ("parity_user", "blame-1", ["A", "C"], "report body"),
                "expected_platform_kwargs": {
                    "user_id": 1,
                    "problem_id": "blame-1",
                    "selected_commits": ["A", "C"],
                    "report": "report body",
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(mode=scenario["mode"]):
                with (
                    patch("app.api.routes.platform_mode_queue.is_rq_enabled", return_value=False),
                    patch(scenario["api_patch_target"], return_value=scenario["response_payload"]) as api_mock,
                    patch(scenario["platform_patch_target"], return_value=scenario["response_payload"]) as platform_mock,
                ):
                    api_response = self.client.post(scenario["api_path"], json=scenario["request_payload"])
                    platform_response = self.client.post(scenario["platform_path"], json=scenario["request_payload"])

                self.assertEqual(api_response.status_code, 200, api_response.text)
                self.assertEqual(platform_response.status_code, 200, platform_response.text)

                api_args, api_kwargs = api_mock.call_args
                self.assertEqual(api_kwargs, {})
                self.assertEqual(api_args, scenario["expected_api_args"])

                platform_args, platform_kwargs = platform_mock.call_args
                self.assertEqual(len(platform_args), 1)
                self.assertEqual(platform_kwargs, scenario["expected_platform_kwargs"])


if __name__ == "__main__":
    unittest.main()
