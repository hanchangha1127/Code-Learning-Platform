"""Gemini API를 호출해 학습자의 설명을 평가한다."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from google import genai
from google.genai import types

from backend.config import get_settings
from backend.admin_metrics import get_admin_metrics

SYSTEM_PROMPT = (
    "당신은 학습자의 코드 설명을 비판적으로 평가하는 감독관입니다. "
    "반드시 아래 JSON 형식으로만 답변하세요.\n"
    '{"summary": 문자열, "strengths": 문자열 배열, "improvements": 문자열 배열, "score": 숫자, "correct": 불리언}\n'
    "- score는 0~100 사이 점수(100이 만점)이며 확신이 없으면 20점 이하만 부여하세요.\n"
    "- correct는 설명이 코드의 핵심 로직을 정확히 짚었다면 true, 아니면 false 입니다.\n"
    "- strengths/improvements 배열에는 구체적인 포인트만 넣고, 없다면 빈 배열을 사용하세요.\n"
    "- summary는 2~3문장으로 핵심 리뷰만 전달하세요."
)

LEARNING_REPORT_MODEL = "gemini-3.1-pro-preview"
LEARNING_REPORT_ERROR_CODE = "learning_report_generation_failed"


class AIClient:
    """Google Gemini API로 학습 설명을 분석한다."""

    def __init__(self) -> None:
        settings = get_settings()
        raw_key = settings.google_api_key or settings.ai_api_key
        api_key = raw_key.strip() if raw_key and raw_key.strip() else None
        self.model = settings.google_model
        self.client = None
        if api_key:
            self.client = genai.Client(api_key=api_key)
        self.metrics = get_admin_metrics()

    def analyze(self, prompt: str) -> Dict[str, object]:
        """학습자의 설명을 분석해 요약/강점/개선/점수/정답 여부를 반환한다."""

        if not self.client:
            return {
                "summary": "AI API 키가 없어 기본 피드백을 제공합니다.",
                "strengths": ["설명 목적과 결과를 비교하며 명확히 정리했습니다."],
                "improvements": [
                    "GOOGLE_API_KEY를 설정하면 실제 AI 분석을 사용할 수 있습니다.",
                    "설명 구조를 단계별로 나누어 주면 더 좋은 피드백을 받을 수 있습니다.",
                ],
                "score": 60.0,
                "correct": False,
            }

        contents = f"{SYSTEM_PROMPT}\n\n=== 학습자 설명 ===\n{prompt}"

        try:
            response = self._analyze_with_thinking(contents)
        except Exception as exc:  # pragma: no cover - 네트워크 호출
            return {
                "summary": f"AI 호출에 실패했습니다: {exc}",
                "strengths": [],
                "improvements": ["잠시 후 다시 시도하거나 API 키 설정을 확인해주세요."],
                "score": 50.0,
                "correct": None,
            }

        message_text = (getattr(response, "text", "") or "").strip()
        if not message_text and getattr(response, "candidates", None):
            parts = []
            for candidate in response.candidates:  # type: ignore[attr-defined]
                for part in getattr(candidate, "content", {}).get("parts", []):
                    if isinstance(part, dict):
                        parts.append(part.get("text", ""))
            message_text = "\n".join(filter(None, parts)).strip()

        if not message_text:
            return {
                "summary": "AI 응답이 비어 있어 결과를 만들지 못했습니다.",
                "strengths": [],
                "improvements": [],
                "score": None,
                "correct": None,
            }

        parsed_candidate = _extract_json_block(message_text)
        if parsed_candidate:
            try:
                structured = json.loads(parsed_candidate)
            except json.JSONDecodeError:
                structured = {"summary": message_text, "strengths": [], "improvements": [], "score": None}
        else:
            try:
                structured = json.loads(message_text)
            except json.JSONDecodeError:
                structured = {"summary": message_text, "strengths": [], "improvements": [], "score": None}

        score_value = _normalize_score_points(structured.get("score"))

        summary_text = structured.get("summary", "")
        strengths = _normalize_points(structured.get("strengths"))
        improvements = _normalize_points(structured.get("improvements"))
        is_correct = structured.get("correct")

        if (not strengths or not strengths[0]) or (not improvements or not improvements[0]):
            parsed_strengths, parsed_improvements = _parse_from_summary(summary_text or message_text)
            if not strengths:
                strengths = parsed_strengths
            if not improvements:
                improvements = parsed_improvements

        reason = _first_sentence(summary_text or message_text)
        if improvements and reason:
            if all(reason not in item for item in improvements):
                improvements.append(f"이유: {reason}")

        return {
            "summary": summary_text.strip() or message_text,
            "strengths": strengths,
            "improvements": improvements,
            "score": score_value,
            "correct": is_correct,
        }

    def analyze_auditor_report(
        self,
        *,
        code: str,
        prompt: str,
        report: str,
        trap_catalog: list[dict[str, str]],
        reference_report: str,
        language: str,
        difficulty: str,
    ) -> Dict[str, object]:
        expected_types = _expected_trap_types(trap_catalog)
        expected_set = set(expected_types)

        if not self.client:
            report_lower = (report or "").lower()
            found_types = []
            for trap_type in expected_types:
                token = trap_type.replace("_", " ")
                if trap_type in report_lower or token in report_lower:
                    found_types.append(trap_type)
            missed_types = [item for item in expected_types if item not in set(found_types)]
            score = round((len(found_types) / max(len(expected_types), 1)) * 100.0, 1)
            correct = score >= 70.0
            return {
                "summary": "AI API 키가 없어 기본 채점 로직으로 평가했습니다.",
                "strengths": ["핵심 취약점을 명시적으로 지적했습니다."] if found_types else [],
                "improvements": ["취약점 근거와 재현 경로를 더 구체적으로 작성하세요."],
                "score": score,
                "correct": correct,
                "found_types": found_types,
                "missed_types": missed_types,
            }

        contents = (
            "당신은 시니어 코드 감사관입니다. 사용자 감사 리포트를 채점하세요.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"summary": 문자열, "strengths": 문자열 배열, "improvements": 문자열 배열, '
            '"score": 숫자, "correct": 불리언, "found_types": 문자열 배열}\n'
            "- score는 0~100 점수입니다.\n"
            "- correct는 score>=70 기준으로 판단하세요.\n"
            "- found_types는 아래 expected trap type 중 사용자 리포트가 짚은 항목만 넣으세요.\n\n"
            f"언어: {language}\n"
            f"난이도: {difficulty}\n"
            f"expected_trap_types: {expected_types}\n"
            f"trap_catalog: {json.dumps(trap_catalog, ensure_ascii=False)}\n\n"
            f"문제 prompt:\n{prompt}\n\n"
            f"대상 코드:\n{code}\n\n"
            f"사용자 감사 리포트:\n{report}\n\n"
            f"모범 감사 리포트:\n{reference_report}\n"
        )

        try:
            response = self._analyze_with_thinking(contents)
        except Exception as exc:
            return {
                "summary": f"AI 호출에 실패했습니다: {exc}",
                "strengths": [],
                "improvements": ["잠시 후 다시 시도하세요."],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected_types,
            }

        message_text = (getattr(response, "text", "") or "").strip()
        if not message_text and getattr(response, "candidates", None):
            parts = []
            for candidate in response.candidates:  # type: ignore[attr-defined]
                for part in getattr(candidate, "content", {}).get("parts", []):
                    if isinstance(part, dict):
                        parts.append(part.get("text", ""))
            message_text = "\n".join(filter(None, parts)).strip()

        if not message_text:
            return {
                "summary": "AI 응답이 비어 있습니다.",
                "strengths": [],
                "improvements": [],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected_types,
            }

        parsed_candidate = _extract_json_block(message_text)
        if parsed_candidate:
            try:
                structured = json.loads(parsed_candidate)
            except json.JSONDecodeError:
                structured = {"summary": message_text}
        else:
            try:
                structured = json.loads(message_text)
            except json.JSONDecodeError:
                structured = {"summary": message_text}

        score_value = _normalize_score_points(structured.get("score"))
        if score_value is None:
            score_value = 0.0
        correct = bool(structured.get("correct")) if structured.get("correct") is not None else score_value >= 70.0

        found_types = _normalize_found_types(structured.get("found_types"), expected_set)
        if not found_types and expected_types:
            # Fallback: infer from report text if model omitted found_types.
            report_lower = (report or "").lower()
            for trap_type in expected_types:
                token = trap_type.replace("_", " ")
                if trap_type in report_lower or token in report_lower:
                    found_types.append(trap_type)

        missed_types = [item for item in expected_types if item not in set(found_types)]

        return {
            "summary": str(structured.get("summary") or message_text).strip(),
            "strengths": _normalize_points(structured.get("strengths")),
            "improvements": _normalize_points(structured.get("improvements")),
            "score": score_value,
            "correct": correct,
            "found_types": found_types,
            "missed_types": missed_types,
        }

    def analyze_context_inference_report(
        self,
        *,
        snippet: str,
        prompt: str,
        report: str,
        expected_facets: list[str],
        reference_report: str,
        inference_type: str,
        language: str,
        difficulty: str,
    ) -> Dict[str, object]:
        expected = _expected_facet_tokens(expected_facets)
        expected_set = set(expected)

        if not self.client:
            report_lower = (report or "").lower()
            found_types = []
            for facet in expected:
                token = facet.replace("_", " ")
                if facet in report_lower or token in report_lower:
                    found_types.append(facet)
            missed_types = [item for item in expected if item not in set(found_types)]
            score = round((len(found_types) / max(len(expected), 1)) * 100.0, 1)
            return {
                "summary": "AI API 키가 없어 기본 채점 로직으로 평가했습니다.",
                "strengths": ["핵심 맥락을 정확히 짚었습니다."] if found_types else [],
                "improvements": ["입력 조건, 인과관계, 상태 변화를 더 구체적으로 작성하세요."],
                "score": score,
                "correct": score >= 70.0,
                "found_types": found_types,
                "missed_types": missed_types,
            }

        contents = (
            "당신은 시니어 아키텍처 리뷰어입니다. 사용자의 맥락 추론 리포트를 채점하세요.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"summary": 문자열, "strengths": 문자열 배열, "improvements": 문자열 배열, '
            '"score": 숫자, "correct": 불리언, "found_types": 문자열 배열}\n'
            "- score 산식은 아래 항목을 합산해 0~100으로 계산하세요.\n"
            "  1) 맥락 정확도 40점\n"
            "  2) 인과 설명 30점\n"
            "  3) 상태/영향 예측 20점\n"
            "  4) 완결성/명료성 10점\n"
            "- correct는 score>=70 기준으로 판단하세요.\n"
            "- found_types는 expected facets 중 사용자가 맞춘 항목만 넣으세요.\n\n"
            f"언어: {language}\n"
            f"난이도: {difficulty}\n"
            f"출제 타입: {inference_type}\n"
            f"expected_facets: {expected}\n\n"
            f"문제 질문:\n{prompt}\n\n"
            f"코드 snippet:\n{snippet}\n\n"
            f"사용자 리포트:\n{report}\n\n"
            f"모범 추론 리포트:\n{reference_report}\n"
        )

        try:
            response = self._analyze_with_thinking(contents)
        except Exception as exc:
            return {
                "summary": f"AI 호출에 실패했습니다: {exc}",
                "strengths": [],
                "improvements": ["잠시 후 다시 시도하세요."],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected,
            }

        message_text = (getattr(response, "text", "") or "").strip()
        if not message_text and getattr(response, "candidates", None):
            parts = []
            for candidate in response.candidates:  # type: ignore[attr-defined]
                for part in getattr(candidate, "content", {}).get("parts", []):
                    if isinstance(part, dict):
                        parts.append(part.get("text", ""))
            message_text = "\n".join(filter(None, parts)).strip()

        if not message_text:
            return {
                "summary": "AI 응답이 비어 있습니다.",
                "strengths": [],
                "improvements": [],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected,
            }

        parsed_candidate = _extract_json_block(message_text)
        if parsed_candidate:
            try:
                structured = json.loads(parsed_candidate)
            except json.JSONDecodeError:
                structured = {"summary": message_text}
        else:
            try:
                structured = json.loads(message_text)
            except json.JSONDecodeError:
                structured = {"summary": message_text}

        score_value = _normalize_score_points(structured.get("score"))
        if score_value is None:
            score_value = 0.0
        correct = bool(structured.get("correct")) if structured.get("correct") is not None else score_value >= 70.0

        found_types = _normalize_found_types(structured.get("found_types"), expected_set)
        if not found_types and expected:
            report_lower = (report or "").lower()
            for facet in expected:
                token = facet.replace("_", " ")
                if facet in report_lower or token in report_lower:
                    found_types.append(facet)

        missed_types = [item for item in expected if item not in set(found_types)]

        return {
            "summary": str(structured.get("summary") or message_text).strip(),
            "strengths": _normalize_points(structured.get("strengths")),
            "improvements": _normalize_points(structured.get("improvements")),
            "score": score_value,
            "correct": correct,
            "found_types": found_types,
            "missed_types": missed_types,
        }

    def analyze_refactoring_choice_report(
        self,
        *,
        scenario: str,
        prompt: str,
        constraints: list[str],
        options: list[dict[str, str]],
        selected_option: str,
        best_option: str,
        report: str,
        decision_facets: list[str],
        reference_report: str,
        option_reviews: list[dict[str, str]],
        language: str,
        difficulty: str,
    ) -> Dict[str, object]:
        expected = _expected_refactoring_facets(decision_facets)
        expected_set = set(expected)
        selected = _normalize_option_id(selected_option)
        best = _normalize_option_id(best_option)

        if not self.client:
            report_lower = (report or "").lower()
            found_types = []
            for facet in expected:
                token = facet.replace("_", " ")
                if facet in report_lower or token in report_lower:
                    found_types.append(facet)

            normalized_constraints = [str(item or "").strip().lower() for item in constraints if str(item or "").strip()]
            matched_constraints = 0
            for row in normalized_constraints:
                if row and row in report_lower:
                    matched_constraints += 1

            selection_points = 40.0 if selected == best and selected in {"A", "B", "C"} else 0.0
            tradeoff_points = round((len(found_types) / max(len(expected), 1)) * 30.0, 1)
            constraint_points = round((matched_constraints / max(len(normalized_constraints), 1)) * 20.0, 1)
            text_length = len((report or "").strip())
            clarity_points = 10.0 if text_length >= 120 else 5.0 if text_length >= 40 else 0.0
            score = round(min(100.0, selection_points + tradeoff_points + constraint_points + clarity_points), 1)
            correct = score >= 70.0
            missed_types = [item for item in expected if item not in set(found_types)]
            return {
                "summary": "AI API 키가 없어 기본 채점 로직으로 평가했습니다.",
                "strengths": ["제약 기반 근거를 구조적으로 제시했습니다."] if found_types else [],
                "improvements": ["제약조건과 트레이드오프를 facet 기준으로 더 구체적으로 연결하세요."],
                "score": score,
                "correct": correct,
                "found_types": found_types,
                "missed_types": missed_types,
            }

        contents = (
            "당신은 시니어 소프트웨어 아키텍트입니다. Refactoring Choice 제출을 채점하세요.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"summary": 문자열, "strengths": 문자열 배열, "improvements": 문자열 배열, '
            '"score": 숫자, "correct": 불리언, "found_types": 문자열 배열}\n'
            "- score 산식은 아래 항목을 합산해 0~100으로 계산하세요.\n"
            "  1) 최적안 선택 정확도 40점\n"
            "  2) 트레이드오프 근거 품질 30점\n"
            "  3) 제약조건 정합성 20점\n"
            "  4) 완결성/명료성 10점\n"
            "- correct는 score>=70 기준으로 판단하세요.\n"
            "- found_types는 decision_facets 중 사용자 리포트가 충족한 항목만 넣으세요.\n\n"
            f"언어: {language}\n"
            f"난이도: {difficulty}\n"
            f"scenario:\n{scenario}\n\n"
            f"문제 prompt:\n{prompt}\n\n"
            f"constraints: {json.dumps(constraints, ensure_ascii=False)}\n"
            f"options: {json.dumps(options, ensure_ascii=False)}\n"
            f"selected_option: {selected}\n"
            f"best_option: {best}\n"
            f"decision_facets: {expected}\n"
            f"option_reviews: {json.dumps(option_reviews, ensure_ascii=False)}\n\n"
            f"사용자 리포트:\n{report}\n\n"
            f"모범 의사결정 메모:\n{reference_report}\n"
        )

        try:
            response = self._analyze_with_thinking(contents)
        except Exception as exc:
            return {
                "summary": f"AI 호출에 실패했습니다: {exc}",
                "strengths": [],
                "improvements": ["잠시 후 다시 시도하세요."],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected,
            }

        message_text = (getattr(response, "text", "") or "").strip()
        if not message_text and getattr(response, "candidates", None):
            parts = []
            for candidate in response.candidates:  # type: ignore[attr-defined]
                for part in getattr(candidate, "content", {}).get("parts", []):
                    if isinstance(part, dict):
                        parts.append(part.get("text", ""))
            message_text = "\n".join(filter(None, parts)).strip()

        if not message_text:
            return {
                "summary": "AI 응답이 비어 있습니다.",
                "strengths": [],
                "improvements": [],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected,
            }

        parsed_candidate = _extract_json_block(message_text)
        if parsed_candidate:
            try:
                structured = json.loads(parsed_candidate)
            except json.JSONDecodeError:
                structured = {"summary": message_text}
        else:
            try:
                structured = json.loads(message_text)
            except json.JSONDecodeError:
                structured = {"summary": message_text}

        score_value = _normalize_score_points(structured.get("score"))
        if score_value is None:
            score_value = 0.0
        correct = bool(structured.get("correct")) if structured.get("correct") is not None else score_value >= 70.0

        found_types = _normalize_found_types(structured.get("found_types"), expected_set)
        if not found_types and expected:
            report_lower = (report or "").lower()
            for facet in expected:
                token = facet.replace("_", " ")
                if facet in report_lower or token in report_lower:
                    found_types.append(facet)

        missed_types = [item for item in expected if item not in set(found_types)]

        return {
            "summary": str(structured.get("summary") or message_text).strip(),
            "strengths": _normalize_points(structured.get("strengths")),
            "improvements": _normalize_points(structured.get("improvements")),
            "score": score_value,
            "correct": correct,
            "found_types": found_types,
            "missed_types": missed_types,
        }

    def analyze_code_blame_report(
        self,
        *,
        error_log: str,
        prompt: str,
        commits: list[dict[str, str]],
        selected_commits: list[str],
        culprit_commits: list[str],
        report: str,
        decision_facets: list[str],
        reference_report: str,
        commit_reviews: list[dict[str, str]],
        language: str,
        difficulty: str,
    ) -> Dict[str, object]:
        expected = _expected_code_blame_facets(decision_facets)
        expected_set = set(expected)
        allowed_option_ids = {str(row.get("optionId") or "").strip().upper() for row in commits if isinstance(row, dict)}
        selected = _normalize_code_blame_option_ids(selected_commits, allowed_option_ids)
        culprits = _normalize_code_blame_option_ids(culprit_commits, allowed_option_ids)

        if not self.client:
            report_lower = (report or "").lower()
            found_types = []
            for facet in expected:
                token = facet.replace("_", " ")
                if facet in report_lower or token in report_lower:
                    found_types.append(facet)
            missed_types = [item for item in expected if item not in set(found_types)]

            overlap = len(set(selected) & set(culprits))
            if set(selected) == set(culprits) and selected:
                culprit_points = 40.0
            elif overlap > 0:
                culprit_points = round(25.0 * (overlap / max(len(culprits), 1)), 1)
            else:
                culprit_points = 0.0

            facet_points = round((len(found_types) / max(len(expected), 1)) * 35.0, 1)
            log_tokens = [token for token in re.findall(r"[a-zA-Z_]{4,}", error_log.lower())[:12] if token]
            log_points = 15.0 if any(token in report_lower for token in log_tokens) else 0.0
            length = len((report or "").strip())
            clarity_points = 10.0 if length >= 120 else 5.0 if length >= 50 else 0.0
            score = round(min(100.0, culprit_points + facet_points + log_points + clarity_points), 1)
            return {
                "summary": "AI API 키가 없어 기본 채점 로직으로 평가했습니다.",
                "strengths": ["로그와 diff 근거를 함께 제시했습니다."] if found_types else [],
                "improvements": ["로그-커밋 인과관계와 장애 영향 범위를 더 구체적으로 작성하세요."],
                "score": score,
                "correct": score >= 70.0,
                "found_types": found_types,
                "missed_types": missed_types,
            }

        contents = (
            "당신은 시니어 장애 분석가입니다. Code Blame Game 제출을 채점하세요.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"summary": 문자열, "strengths": 문자열 배열, "improvements": 문자열 배열, '
            '"score": 숫자, "correct": 불리언, "found_types": 문자열 배열}\n'
            "- 자유채점으로 0~100 점수를 부여하세요.\n"
            "- correct는 score>=70 기준으로 판단하세요.\n"
            "- found_types는 decision_facets 중 사용자가 충족한 항목만 넣으세요.\n\n"
            f"언어: {language}\n"
            f"난이도: {difficulty}\n"
            f"문제 prompt:\n{prompt}\n\n"
            f"error_log:\n{error_log}\n\n"
            f"commits: {json.dumps(commits, ensure_ascii=False)}\n"
            f"selected_commits: {json.dumps(selected, ensure_ascii=False)}\n"
            f"culprit_commits: {json.dumps(culprits, ensure_ascii=False)}\n"
            f"decision_facets: {json.dumps(expected, ensure_ascii=False)}\n"
            f"commit_reviews: {json.dumps(commit_reviews, ensure_ascii=False)}\n\n"
            f"사용자 리포트:\n{report}\n\n"
            f"모범 추론 리포트:\n{reference_report}\n"
        )

        try:
            response = self._analyze_with_thinking(contents)
        except Exception as exc:
            return {
                "summary": f"AI 호출에 실패했습니다: {exc}",
                "strengths": [],
                "improvements": ["잠시 후 다시 시도하세요."],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected,
            }

        message_text = (getattr(response, "text", "") or "").strip()
        if not message_text and getattr(response, "candidates", None):
            parts = []
            for candidate in response.candidates:  # type: ignore[attr-defined]
                for part in getattr(candidate, "content", {}).get("parts", []):
                    if isinstance(part, dict):
                        parts.append(part.get("text", ""))
            message_text = "\n".join(filter(None, parts)).strip()

        if not message_text:
            return {
                "summary": "AI 응답이 비어 있습니다.",
                "strengths": [],
                "improvements": [],
                "score": 0.0,
                "correct": False,
                "found_types": [],
                "missed_types": expected,
            }

        parsed_candidate = _extract_json_block(message_text)
        if parsed_candidate:
            try:
                structured = json.loads(parsed_candidate)
            except json.JSONDecodeError:
                structured = {"summary": message_text}
        else:
            try:
                structured = json.loads(message_text)
            except json.JSONDecodeError:
                structured = {"summary": message_text}

        score_value = _normalize_score_points(structured.get("score"))
        if score_value is None:
            score_value = 0.0
        correct = bool(structured.get("correct")) if structured.get("correct") is not None else score_value >= 70.0

        found_types = _normalize_found_types(structured.get("found_types"), expected_set)
        if not found_types and expected:
            report_lower = (report or "").lower()
            for facet in expected:
                token = facet.replace("_", " ")
                if facet in report_lower or token in report_lower:
                    found_types.append(facet)

        missed_types = [item for item in expected if item not in set(found_types)]

        return {
            "summary": str(structured.get("summary") or message_text).strip(),
            "strengths": _normalize_points(structured.get("strengths")),
            "improvements": _normalize_points(structured.get("improvements")),
            "score": score_value,
            "correct": correct,
            "found_types": found_types,
            "missed_types": missed_types,
        }

    def _analyze_with_thinking(self, contents: str):
        if not self.client:  # pragma: no cover
            raise RuntimeError("AI 클라이언트가 초기화되지 않았습니다.")

        token = self.metrics.start_ai_call(provider="google", operation="analyze")
        config_with_thinking = types.GenerateContentConfig(
            temperature=1.0,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        try:
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config_with_thinking,
                )
            except Exception as exc:
                if "thinking" not in str(exc).lower():
                    raise
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(temperature=1.0),
                )

            self.metrics.end_ai_call(token, success=True)
            return response
        except Exception:
            self.metrics.end_ai_call(token, success=False)
            raise

    def _extract_response_text(self, response: Any) -> str:
        text = (getattr(response, "text", "") or "").strip()
        if text:
            return text

        if getattr(response, "candidates", None):
            parts: list[str] = []
            for candidate in response.candidates:  # type: ignore[attr-defined]
                for part in getattr(candidate, "content", {}).get("parts", []):
                    if isinstance(part, dict):
                        parts.append(part.get("text", ""))
            return "\n".join(filter(None, parts)).strip()
        return ""

    def _generate_learning_report_once(self, contents: str):
        if not self.client:
            raise RuntimeError(f"{LEARNING_REPORT_ERROR_CODE}: ai_client_not_configured")

        token = self.metrics.start_ai_call(provider="google", operation="learning_report_generation")
        config = types.GenerateContentConfig(
            temperature=0.7,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        )
        try:
            response = self.client.models.generate_content(
                model=LEARNING_REPORT_MODEL,
                contents=contents,
                config=config,
            )
            self.metrics.end_ai_call(token, success=True)
            return response
        except Exception:
            self.metrics.end_ai_call(token, success=False)
            raise

    def _generate_learning_report_with_retry(self, contents: str):
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self._generate_learning_report_once(contents)
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = exc
                if attempt == 0:
                    continue
        raise RuntimeError(f"{LEARNING_REPORT_ERROR_CODE}: generation_failed") from last_error

    def generate_learning_solution_report(
        self,
        *,
        history_context: str,
        metric_snapshot: Dict[str, object],
    ) -> Dict[str, object]:
        if not self.client:
            raise RuntimeError(f"{LEARNING_REPORT_ERROR_CODE}: ai_client_not_configured")

        system_prompt = (
            "당신은 코딩 학습 코치입니다. 학습자 평가가 아니라 향후 실행 가능한 학습 솔루션을 제시하세요. "
            "반드시 아래 JSON 형식으로만 답변하세요.\n"
            '{"goal": 문자열, "solutionSummary": 문자열, "priorityActions": 문자열 배열, '
            '"phasePlan": 문자열 배열, "dailyHabits": 문자열 배열, "focusTopics": 문자열 배열, '
            '"metricsToTrack": 문자열 배열, "checkpoints": 문자열 배열, "riskMitigation": 문자열 배열}\n'
            "- 모든 항목은 한국어로 작성하세요.\n"
            "- 학습자 평가/판정 문구 대신 실행 계획 중심으로 작성하세요.\n"
            "- 각 배열에는 중복 없이 구체적인 실행 항목을 제시하세요."
        )

        contents = (
            f"{system_prompt}\n\n"
            f"=== 지표 스냅샷 ===\n{json.dumps(metric_snapshot, ensure_ascii=False)}\n\n"
            f"=== 최근 학습 기록 ===\n{history_context}"
        )

        response = self._generate_learning_report_with_retry(contents)
        text = self._extract_response_text(response)
        if not text:
            raise RuntimeError(f"{LEARNING_REPORT_ERROR_CODE}: empty_response")

        payload = _extract_json_block(text) or text
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{LEARNING_REPORT_ERROR_CODE}: invalid_json") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"{LEARNING_REPORT_ERROR_CODE}: invalid_payload")

        return {
            "goal": _normalize_text_field(data.get("goal"), "단기 목표를 재정의하고 학습 루틴을 고정하세요."),
            "solutionSummary": _normalize_text_field(
                data.get("solutionSummary"),
                "최근 기록을 바탕으로 주간 실행 계획을 수립하고 반복 학습 루프를 구축하세요.",
            ),
            "priorityActions": _normalize_plan_items(data.get("priorityActions")),
            "phasePlan": _normalize_plan_items(data.get("phasePlan")),
            "dailyHabits": _normalize_plan_items(data.get("dailyHabits")),
            "focusTopics": _normalize_plan_items(data.get("focusTopics")),
            "metricsToTrack": _normalize_plan_items(data.get("metricsToTrack")),
            "checkpoints": _normalize_plan_items(data.get("checkpoints")),
            "riskMitigation": _normalize_plan_items(data.get("riskMitigation")),
        }

    def generate_report(self, history_context: str) -> Dict[str, object]:
        """Backward-compatible wrapper for callers that still use the legacy name."""
        return self.generate_learning_solution_report(
            history_context=history_context,
            metric_snapshot={
                "attempts": 0,
                "accuracy": None,
                "avgScore": None,
                "trend": "학습 데이터가 부족합니다.",
            },
        )

    def evaluate_tier(self, context: str, current_tier: str) -> Dict[str, object]:
        """AI에게 승급/유지/강등 여부를 판단시킨다."""

        if not self.client:
            return {
                "tier": current_tier,
                "reason": "AI API 키가 없어 기존 티어를 유지합니다.",
            }

        system_prompt = (
            "당신은 코딩 학습자의 티어(초급/중급/고급)를 판단하는 멘토입니다. "
            "반드시 아래 JSON 형식으로만 답변하세요.\n"
            '{"tier": "beginner|intermediate|advanced", "reason": 문자열}\n'
            "- 최근 10문제 기록을 기반으로 판단하세요.\n"
            "- 쉬운 문제(초급)만 풀었다면 승급하지 말고 유지 또는 강등을 선택하세요.\n"
            "- 근거는 reason에 간단히 요약하세요."
        )

        contents = f"{system_prompt}\n\n=== 현재 티어 ===\n{current_tier}\n\n=== 최근 기록 ===\n{context}"

        try:
            response = self._analyze_with_thinking(contents)
        except Exception as exc:
            return {
                "tier": current_tier,
                "reason": f"AI 호출 실패: {exc}",
            }

        text = (getattr(response, "text", "") or "").strip()
        if not text and getattr(response, "candidates", None):
            parts = []
            for candidate in response.candidates:
                for part in getattr(candidate, "content", {}).get("parts", []):
                    if isinstance(part, dict):
                        parts.append(part.get("text", ""))
            text = "\n".join(filter(None, parts)).strip()

        parsed = _extract_json_block(text)
        if parsed:
            try:
                data = json.loads(parsed)
            except json.JSONDecodeError:
                data = {"tier": current_tier, "reason": text[:200]}
        else:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {"tier": current_tier, "reason": text[:200]}

        tier = data.get("tier") if isinstance(data, dict) else None
        reason = data.get("reason") if isinstance(data, dict) else None
        if tier not in {"beginner", "intermediate", "advanced"}:
            tier = current_tier
        if not reason:
            reason = "AI 판단 근거가 없습니다."
        return {"tier": tier, "reason": reason}


def _parse_from_summary(summary: str) -> tuple[List[str], List[str]]:
    strengths: List[str] = []
    improvements: List[str] = []

    if not summary:
        return strengths, improvements

    lines = [line.strip() for line in summary.splitlines() if line.strip()]

    strength_keywords = ("강점", "장점", "강조", "strength", "strengths")
    improvement_keywords = ("개선", "보완", "약점", "improvement", "improvements", "weakness", "weaknesses")

    def _is_header(text: str, keywords: tuple[str, ...]) -> bool:
        normalized = text.casefold()
        return any(normalized.startswith(keyword) for keyword in keywords)

    def _collect(start_index: int) -> List[str]:
        collected: List[str] = []
        for line in lines[start_index + 1 :]:
            cleaned_line = line.strip("-•· ").strip()
            if _is_header(cleaned_line, strength_keywords + improvement_keywords):
                break
            if cleaned_line:
                collected.append(cleaned_line)
        return collected

    for idx, line in enumerate(lines):
        cleaned = line.strip("-•· ").strip()
        if _is_header(cleaned, strength_keywords):
            tail = cleaned.split(":", 1)[1].strip() if ":" in cleaned else ""
            items = (
                [item.strip() for item in re.split(r"[•·;,-]+\s*", tail) if item.strip()]
                if tail
                else _collect(idx)
            )
            strengths.extend(items)
        elif _is_header(cleaned, improvement_keywords):
            tail = cleaned.split(":", 1)[1].strip() if ":" in cleaned else ""
            items = (
                [item.strip() for item in re.split(r"[•·;,-]+\s*", tail) if item.strip()]
                if tail
                else _collect(idx)
            )
            improvements.extend(items)

    return strengths, improvements


def _normalize_points(value) -> List[str]:
    """Return cleaned list of bullet strings from an API field."""

    def _split(text: str) -> List[str]:
        parts = re.split(r"[•·\n;]+", text)
        return [part.strip() for part in parts if part.strip()]

    if isinstance(value, list):
        items: List[str] = []
        for entry in value:
            cleaned = entry.strip() if isinstance(entry, str) else str(entry).strip()
            if cleaned:
                items.extend(_split(cleaned))
        return items
    if isinstance(value, str):
        return _split(value.strip())
    return []


def _normalize_text_field(value: object, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _normalize_plan_items(value: object, *, max_items: int = 7) -> List[str]:
    rows = _normalize_points(value)
    deduped: List[str] = []
    for row in rows:
        if row in deduped:
            continue
        deduped.append(row)
        if len(deduped) >= max_items:
            break
    return deduped


def _normalize_score_points(value) -> float | None:
    """Convert raw score values into a 0~100 point scale."""

    if value is None:
        return None

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if numeric != numeric:  # NaN guard
        return None

    if 0 <= numeric <= 1:
        numeric *= 100

    if numeric < 0:
        numeric = 0.0
    if numeric > 100:
        numeric = 100.0
    return numeric


def _extract_json_block(text: str) -> str | None:
    """Return the JSON snippet contained inside markdown-style fences."""

    if not text:
        return None

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()

    bracket_start = text.find("{")
    bracket_end = text.rfind("}")
    if bracket_start != -1 and bracket_end != -1 and bracket_start < bracket_end:
        return text[bracket_start : bracket_end + 1].strip()

    return None


def _first_sentence(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    try:
        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        return parts[0].strip() if parts else cleaned
    except re.error:
        return cleaned


def _expected_trap_types(trap_catalog: list[dict[str, str]]) -> list[str]:
    rows: list[str] = []
    for entry in trap_catalog:
        if not isinstance(entry, dict):
            continue
        trap_type = str(entry.get("type") or "").strip().lower()
        if not trap_type:
            continue
        if trap_type in rows:
            continue
        rows.append(trap_type)
    return rows


def _expected_facet_tokens(expected_facets: list[str]) -> list[str]:
    rows: list[str] = []
    for facet in expected_facets:
        token = str(facet or "").strip().lower()
        if not token:
            continue
        if token in rows:
            continue
        rows.append(token)
    return rows


_REFACTORING_CHOICE_FACET_TAXONOMY: set[str] = {
    "performance",
    "memory",
    "readability",
    "maintainability",
    "security",
    "testability",
}
_CODE_BLAME_FACET_TAXONOMY: set[str] = {
    "log_correlation",
    "root_cause_diff",
    "failure_mechanism",
    "blast_radius",
    "fix_strategy",
    "verification",
}


def _expected_refactoring_facets(decision_facets: list[str]) -> list[str]:
    rows: list[str] = []
    for facet in decision_facets:
        token = str(facet or "").strip().lower()
        if not token or token not in _REFACTORING_CHOICE_FACET_TAXONOMY:
            continue
        if token in rows:
            continue
        rows.append(token)
    if not rows:
        rows.extend(["performance", "readability", "maintainability"])
    return rows


def _expected_code_blame_facets(decision_facets: list[str]) -> list[str]:
    rows: list[str] = []
    for facet in decision_facets:
        token = str(facet or "").strip().lower()
        if not token or token not in _CODE_BLAME_FACET_TAXONOMY:
            continue
        if token in rows:
            continue
        rows.append(token)
    if len(rows) < 3:
        for fallback in (
            "log_correlation",
            "root_cause_diff",
            "failure_mechanism",
            "blast_radius",
            "fix_strategy",
            "verification",
        ):
            if fallback in rows:
                continue
            rows.append(fallback)
            if len(rows) >= 3:
                break
    if len(rows) > 4:
        rows = rows[:4]
    return rows


def _normalize_option_id(value: object) -> str:
    token = str(value or "").strip().upper()
    if token in {"A", "B", "C"}:
        return token
    return "A"


def _normalize_code_blame_option_ids(value: object, allowed: set[str]) -> list[str]:
    rows: list[str] = []
    if not isinstance(value, list):
        return rows
    for entry in value:
        token = str(entry or "").strip().upper()
        if not token or token not in allowed:
            continue
        if token in rows:
            continue
        rows.append(token)
    return rows


def _normalize_found_types(value: object, expected: set[str]) -> list[str]:
    if not expected:
        return []
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for entry in value:
        trap_type = str(entry or "").strip().lower()
        if not trap_type or trap_type not in expected:
            continue
        if trap_type in rows:
            continue
        rows.append(trap_type)
    return rows

