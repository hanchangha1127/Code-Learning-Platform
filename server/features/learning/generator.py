"""Gemini 기반 문제 생성 로직."""

from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional

from google import genai
from google.genai import types

from server.features.learning.content import normalize_language_id
from server.features.learning.generator_normalize import (
    _CODE_BLAME_FACET_TAXONOMY,
    _REFACTORING_CHOICE_FACET_TAXONOMY,
    _fallback_code_for_language,
    _language_file_extension,
    _normalize_advanced_analysis_files,
    _normalize_analysis_prompt,
    _normalize_analysis_reference,
    _normalize_auditor_trap_catalog,
    _normalize_code_blame_commit_reviews,
    _normalize_code_blame_commits,
    _normalize_code_blame_facets,
    _normalize_code_blame_option_ids,
    _normalize_code_block_objective,
    _normalize_context_inference_facets,
    _normalize_refactoring_choice_facets,
    _normalize_refactoring_choice_option_reviews,
    _normalize_refactoring_choice_options,
    _strip_comments,
)
from server.core.runtime_config import get_settings
from server.infra.admin_metrics import get_admin_metrics


@dataclass
class GeneratedProblem:
    problem_id: str
    title: str
    code: str
    prompt: str
    reference: str
    difficulty: str
    mode: str


def _extract_json_blob(text: str) -> str:
    """Return the most likely JSON document contained in *text*."""

    cleaned = text.strip()
    if not cleaned:
        return cleaned

    code_block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned)
    if code_block:
        return code_block.group(1).strip()

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and first < last:
        return cleaned[first : last + 1].strip()

    return cleaned


def _response_text(response: Any) -> str:
    text = (getattr(response, "text", "") or "").strip()
    if text:
        return text
    if not getattr(response, "candidates", None):
        return ""

    parts: list[str] = []
    for candidate in response.candidates:  # type: ignore[attr-defined]
        content = getattr(candidate, "content", None)
        if isinstance(content, dict):
            candidate_parts = content.get("parts", [])
        else:
            candidate_parts = getattr(content, "parts", []) or []
        for part in candidate_parts:
            if isinstance(part, dict):
                parts.append(part.get("text", ""))
            else:
                parts.append(getattr(part, "text", ""))
    return "\n".join(filter(None, parts)).strip()


def _history_block(history_context: object, header: str, guidance: str) -> str:
    context = str(history_context or "").strip()
    if not context:
        return ""
    return f"{header}\n{context}\n{guidance}\n"


def _join_prompt_sections(*sections: object) -> str:
    return "".join(str(section) for section in sections if section)


def _base_payload(
    problem_id: str,
    mode: str,
    difficulty: object,
    language_id: str,
    **payload: Any,
) -> dict[str, Any]:
    base = {
        "problem_id": problem_id,
        "mode": mode,
        "difficulty": difficulty,
        "language": language_id,
    }
    base.update(payload)
    return base


class ProblemGenerator:
    """Google Gemini API를 호출해 맞춤 문제를 생성한다."""

    def __init__(self) -> None:
        settings = get_settings()
        raw_key = settings.google_api_key or settings.ai_api_key
        self.api_key = raw_key.strip() if raw_key and raw_key.strip() else None
        self.model = settings.google_model
        self.timeout_ms = max(settings.google_timeout_seconds, 1) * 1000
        self.client = None
        if self.api_key:
            self.client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=self.timeout_ms),
            )
        self.metrics = get_admin_metrics()

    def _require_client(self, message: str = "AI API 설정이 없어 실행할 수 없습니다.") -> None:
        if not self.client:
            raise ValueError(message)

    def _request_json(
        self,
        contents: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
        empty_message: str = "AI 응답이 비어 있습니다.",
        parse_error_prefix: str = "AI 응답 파싱 실패",
        include_parse_snippet: bool = False,
        use_generation_request: bool = True,
    ) -> dict[str, Any]:
        try:
            response = (
                self._run_generation_request(contents, on_text_delta=on_text_delta)
                if use_generation_request
                else self._generate_with_thinking(contents)
            )
        except Exception as exc:  # pragma: no cover - network dependent path
            raise ValueError(f"AI API 호출 실패: {exc}") from exc

        text = _response_text(response)
        if not text:
            raise ValueError(empty_message)

        try:
            data = json.loads(_extract_json_blob(text))
        except json.JSONDecodeError as exc:
            if include_parse_snippet:
                snippet = text[:200].replace("\n", " ")
                raise ValueError(f"{parse_error_prefix}: {exc}; 응답 일부: {snippet!r}") from exc
            raise ValueError(f"{parse_error_prefix}: {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"{parse_error_prefix}: JSON object여야 합니다.")
        return data

    def _generate_workspace_analysis_problem_sync(
        self,
        *,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str],
        on_text_delta: Optional[Callable[[str], None]],
        intro: str,
        language_label: str,
        history_header: str,
        history_guidance: str,
        requirements: list[str],
        min_files: int,
        max_files: int,
        default_role: str,
        checklist_limit: int,
        checklist_min_count: int,
        checklist_fallback: list[str],
        reference_fallback: str,
        title_fallback: str,
        summary_fallback: str,
        prompt_fallback: str,
        workspace_fallback: str,
    ) -> Dict[str, Any]:
        self._require_client()

        contents = _join_prompt_sections(
            f"{intro}\n",
            "반드시 JSON으로만 답변하세요.\n",
            '{"title": 문자열, "summary": 문자열, "prompt": 문자열, "workspace": 문자열, '
            '"checklist": 문자열 배열, '
            '"files": [{"path": 문자열, "name": 문자열, "language": 문자열, "role": 문자열, "content": 문자열}], '
            '"reference_report": 문자열, '
            '"difficulty": 문자열}\n\n',
            f"문제 ID: {problem_id}\n",
            f"트랙: {track_id}\n",
            f"{language_label}: {language_id}\n",
            f"난이도: {difficulty}\n",
            _history_block(history_context, history_header, history_guidance),
            "요구사항:\n",
            "".join(f"- {item}\n" for item in requirements),
        )

        data = self._request_json(
            contents,
            on_text_delta=on_text_delta,
            empty_message="AI 응답이 비어 있습니다.",
            parse_error_prefix="AI 응답 파싱 실패",
        )

        files = _normalize_advanced_analysis_files(
            data.get("files"),
            min_count=min_files,
            max_count=max_files,
            default_language=language_id,
            default_role=default_role,
        )
        checklist = [
            str(item or "").strip()
            for item in (data.get("checklist") or [])
            if str(item or "").strip()
        ][:checklist_limit]
        if len(checklist) < checklist_min_count:
            checklist = checklist_fallback

        reference_report = str(data.get("reference_report") or "").strip() or reference_fallback
        return _base_payload(
            problem_id,
            mode,
            data.get("difficulty", difficulty),
            language_id,
            title=str(data.get("title") or "").strip() or title_fallback,
            summary=str(data.get("summary") or "").strip() or summary_fallback,
            prompt=str(data.get("prompt") or "").strip() or prompt_fallback,
            workspace=str(data.get("workspace") or "").strip() or workspace_fallback,
            checklist=checklist,
            files=files,
            reference_report=reference_report,
        )
    def generate_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
        retry_context: Optional[Dict[str, str]] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> GeneratedProblem:
        self._require_client(
            "AI API 키가 없어 문제를 생성할 수 없습니다. 환경 변수 GOOGLE_API_KEY를 등록한 뒤 다시 시도해주세요."
        )

        retry_instruction = ""
        if retry_context:
            retry_instruction = (
                "*** 중요: 직전 문제에서 오답을 제출했습니다. ***\n"
                "비슷한 개념을 확인할 수 있도록 변형 문제를 만들어 주세요.\n"
                f"직전 문제 제목: {retry_context.get('title')}\n"
                f"직전 문제 코드:\n{retry_context.get('code')}\n"
                f"직전 문제 질문: {retry_context.get('prompt')}\n"
            )

        history_block = ""
        if not retry_instruction:
            history_block = _history_block(
                history_context,
                "최근 문제 기록:",
                "최근 기록과 겹치지 않는 주제/로직/시나리오로 문제를 만들어 주세요.",
            )

        contents = _join_prompt_sections(
            "당신은 코드 이해 진단을 위한 문제를 만드는 AI 보조입니다. "
            "반드시 JSON 형태로만 답변하세요\n"
            '{"title": 문자열, "code": 문자열, "prompt": 문자열, "reference": 문자열, "difficulty": 문자열}\n\n'
            f"문제 ID: {problem_id}\n"
            f"학습 모드: {mode}\n"
            f"학습 분야: {track_id}\n"
            f"언어: {language_id}\n"
            f"난이도: {difficulty}\n"
            f"{history_block}"
            f"{retry_instruction}"
            "기존 문제와 동일한 주제는 피하고, 새로운 로직/상황으로 출제하세요. "
            "요구사항:\n"
            "- code에는 주석(#, //, /* */)을 포함하지 마세요.\n"
            "- code에는 docstring(삼중 따옴표) 같은 설명 텍스트를 넣지 마세요.\n"
            "- code에는 불필요한 설명 문장(영어/한국어)을 넣지 마세요.\n"
            "- prompt는 학습자가 자연스럽게 설명할 수 있도록 명확하게 작성하세요.\n"
            "- prompt는 최종 출력값/반환값만 맞히게 하지 말고, 변수 상태 변화, 조건 분기, 핵심 로직의 목적을 설명하게 작성하세요.\n"
            "- '무엇이 출력되나요?', '최종 출력값은?', '실행 결과만 쓰세요', '반환값은?' 같은 질문은 금지합니다.\n"
            "- reference는 모범 해설 요약을 한국어로 작성하되, 최종 결과만 적지 말고 흐름과 근거를 함께 설명하세요.",
        )
        data = self._request_json(
            contents,
            on_text_delta=on_text_delta,
            empty_message="AI 응답이 비어 있어 문제를 생성하지 못했습니다.",
            parse_error_prefix="AI 응답을 JSON으로 해석하지 못했습니다",
            include_parse_snippet=True,
        )

        code_clean = _strip_comments(data.get("code", ""), language_id)

        return GeneratedProblem(
            problem_id=problem_id,
            title=data.get("title", "AI 생성 문제"),
            code=code_clean,
            prompt=_normalize_analysis_prompt(data.get("prompt")),
            reference=_normalize_analysis_reference(data.get("reference", "")),
            difficulty=data.get("difficulty", difficulty),
            mode=mode,
        )
    def generate_code_block_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        self._require_client()

        contents = _join_prompt_sections(
            "당신은 코딩 학습자를 위한 '빈칸 채우기' 문제를 만드는 AI입니다. "
            "반드시 JSON 형태로만 답변하세요.\n"
            '{"title": 문자열, "objective": 문자열, "code": 문자열, "correct_option": 문자열, "wrong_options": ["오답1", "오답2"], "explanation": 문자열}\n\n'
            f"언어: {language_id}\n"
            f"난이도: {difficulty}\n",
            _history_block(
                history_context,
                "최근 출제된 코드 블록 문제들:",
                "위 목록과 동일한 주제/코드 구조/빈칸 위치를 피하고, 완전히 다른 개념과 흐름으로 새 문제를 만들어 주세요.",
            ),
            "요구사항:\n"
            "- 모든 설명과 선택지는 한국어로 작성하세요. 영어 문장이나 주석을 넣지 마세요.\n"
            "- code 필드는 10~20줄 사이의 코드 snippet을 생성하되, 핵심 로직 부분을 '[BLANK]'로 비워주세요.\n"
            "- code에는 주석을 포함하지 말고, 불필요한 영어 텍스트를 넣지 마세요.\n"
            "- correct_option은 정답 1개를 문자열로 제공하세요.\n"
            "- wrong_options는 오답 2개를 리스트로 제공하세요. 오답은 그럴듯해야 합니다.\n"
            "- explanation 필드는 한국어로 정답인 이유를 간략히 설명해주세요.\n"
            "- title 필드는 문제의 주제를 한국어로 요약하세요.\n"
            "- objective 필드는 코드가 무엇을 완성하려는지 한 문장으로 설명하세요.\n"
            "- title/objective에는 [BLANK]에 들어갈 정확한 코드 문자열을 그대로 쓰지 마세요.",
        )
        data = self._request_json(contents, on_text_delta=on_text_delta)

        code_clean = _strip_comments(data.get("code", ""), language_id).strip()

        correct_option = data.get("correct_option")
        wrong_options = data.get("wrong_options")

        if not isinstance(correct_option, str):
            correct_option = ""
        if not isinstance(wrong_options, list):
            wrong_options = []
        wrong_options = [item for item in wrong_options if isinstance(item, str)]

        # Backward compatible: older schema used options + answer_index.
        if not correct_option:
            legacy_options = data.get("options") or []
            if isinstance(legacy_options, list):
                legacy_options = [item for item in legacy_options if isinstance(item, str)]
            else:
                legacy_options = []

            try:
                legacy_answer_index = int(data.get("answer_index", 0))
            except (TypeError, ValueError):
                legacy_answer_index = 0

            if 0 <= legacy_answer_index < len(legacy_options):
                correct_option = legacy_options[legacy_answer_index]
                wrong_options = [opt for idx, opt in enumerate(legacy_options) if idx != legacy_answer_index]

        # 기본 안전장치: 옵션 3개, BLANK 포함 코드, 설명/정답 유효성 확보
        correct_option = (correct_option or "").strip()
        wrong_clean: list[str] = []
        for opt in wrong_options:
            cleaned = (opt or "").strip()
            if not cleaned or cleaned == correct_option or cleaned in wrong_clean:
                continue
            wrong_clean.append(cleaned)

        while len(wrong_clean) < 2:
            filler = f"오답 {chr(ord('A') + len(wrong_clean))}"
            if filler != correct_option and filler not in wrong_clean:
                wrong_clean.append(filler)

        options = [correct_option or "정답", wrong_clean[0], wrong_clean[1]]
        random.shuffle(options)
        answer_index = options.index(correct_option or "정답")

        if "[BLANK]" not in code_clean:
            # BLANK가 누락되면 간단한 루프 예제로 대체
            code_clean = (
                "numbers = [1, 2, 3, 4]\n"
                "total = 0\n"
                "for num in numbers:\n"
                "    total = [BLANK]\n"
                "print(total)"
            )

        explanation = data.get("explanation") or "정답인 이유를 간단히 설명합니다."
        title_raw = str(data.get("title") or "").strip()
        title_safe = title_raw if title_raw and (not correct_option or correct_option not in title_raw) else "코드 빈칸 채우기"
        objective = _normalize_code_block_objective(
            data.get("objective") or data.get("goal") or data.get("summary") or title_raw,
            fallback=title_raw,
            correct_option=correct_option,
        )

        return _base_payload(
            problem_id,
            mode,
            difficulty,
            language_id,
            title=title_safe,
            objective=objective,
            code=code_clean,
            options=options,
            answer_index=answer_index,
            explanation=explanation,
        )
    def generate_code_error_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate code with one incorrect 3-line block among several 3-line blocks."""

        self._require_client()

        contents = _join_prompt_sections(
            "당신은 학습자가 잘못된 코드 블록을 찾는 연습 문제를 만듭니다.\n"
            "반드시 JSON 으로만 답변하세요.\n"
            '{"title": 문자열, "blocks": ["3줄 블록1", "3줄 블록2", ...], "wrong_block_index": 0, "explanation": 문자열}\n\n'
            f"언어: {language_id}\n"
            f"난이도: {difficulty}\n",
            _history_block(
                history_context,
                "최근 출제된 코드 오류 찾기 기록입니다. 동일한 주제/패턴/실수 유형을 피해서 새로운 문제를 만드세요.",
                "",
            ),
            "요구사항:\n"
            "- 전체 코드는 3줄씩 묶인 블록으로 제공하며 최소 3개 이상 블록을 제공하세요.\n"
            "- 각 블록은 선택한 언어 문법을 사용하세요. 주석/불필요한 영어 문장을 넣지 맙니다.\n"
            "- wrong_block_index는 0부터 시작하며, 단 하나의 블록만 잘못된 코드입니다. 나머지는 정상 동작 코드여야 합니다.\n"
            "- explanation에는 왜 해당 블록이 잘못되었는지, 올바른 형태는 무엇인지 한국어로 설명하세요.\n",
        )
        data = self._request_json(contents, use_generation_request=False)

        blocks = data.get("blocks") or []
        if not isinstance(blocks, list):
            blocks = []
        # Ensure each block is stripped and non-empty
        clean_blocks = []
        for blk in blocks:
            if not isinstance(blk, str):
                continue
            stripped = _strip_comments(blk, language_id).strip("\n")
            if stripped:
                clean_blocks.append(stripped)

        if len(clean_blocks) < 3:
            raise ValueError("블록 수가 부족합니다.")

        try:
            wrong_index = int(data.get("wrong_block_index", 0))
        except (TypeError, ValueError):
            wrong_index = 0
        wrong_index = max(0, min(wrong_index, len(clean_blocks) - 1))

        return _base_payload(
            problem_id,
            mode,
            difficulty,
            language_id,
            title=data.get("title") or "코드 오류 찾기",
            blocks=clean_blocks,
            wrong_block_index=wrong_index,
            explanation=data.get("explanation") or "",
        )

    def generate_auditor_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        trap_count: int,
        history_context: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        self._require_client()

        requested_traps = max(1, int(trap_count or 1))

        contents = _join_prompt_sections(
            "당신은 코드 리뷰 훈련을 위한 감사관 모드 문제를 생성하는 AI입니다.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"title": 문자열, "code": 문자열, "prompt": 문자열, '
            '"trap_catalog": [{"type": 문자열, "description": 문자열}], '
            '"reference_report": 문자열, "difficulty": 문자열}\n\n'
            f"문제 ID: {problem_id}\n"
            f"트랙: {track_id}\n"
            f"언어: {language_id}\n"
            f"난이도: {difficulty}\n"
            f"필수 함정 개수: {requested_traps}\n",
            _history_block(
                history_context,
                "최근 감사관 모드 문제 기록입니다. 동일한 취약점 조합/코드 패턴을 피하고 새로운 시나리오로 생성하세요.",
                "",
            ),
            "요구사항:\n"
            f"- trap_catalog는 정확히 {requested_traps}개의 치명적 함정을 담으세요.\n"
            "- 함정 유형은 로직 결함과 보안 취약점을 혼합하세요.\n"
            "- code는 실제 코드처럼 자연스럽고 실행 가능한 형태로 작성하세요.\n"
            "- code에 정답/취약점 힌트성 주석을 넣지 마세요.\n"
            "- prompt는 리뷰어에게 감사 리포트를 요구하는 한국어 문장으로 작성하세요.\n"
            "- reference_report는 모범 감사 리포트를 한국어로 작성하세요.\n",
        )
        data = self._request_json(contents, on_text_delta=on_text_delta)

        code_clean = _strip_comments(data.get("code", ""), language_id).strip()
        prompt = str(data.get("prompt") or "").strip()
        if not prompt:
            prompt = "코드에서 치명적 함정을 찾아 감사 리포트를 작성하세요."

        trap_catalog = _normalize_auditor_trap_catalog(
            data.get("trap_catalog"),
            trap_count=requested_traps,
        )
        reference_report = str(data.get("reference_report") or "").strip()
        if not reference_report:
            trap_lines = [f"- {item['type']}: {item['description']}" for item in trap_catalog]
            reference_report = "다음 항목을 중심으로 감사 리포트를 작성해야 합니다.\n" + "\n".join(trap_lines)

        return _base_payload(
            problem_id,
            mode,
            data.get("difficulty", difficulty),
            language_id,
            title=data.get("title") or "감사관 코드 리뷰 문제",
            code=code_clean,
            prompt=prompt,
            trap_catalog=trap_catalog,
            reference_report=reference_report,
        )

    def generate_context_inference_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        inference_type: str,
        complexity_profile: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._require_client()

        normalized_type = str(inference_type or "pre_condition").strip().lower()
        if normalized_type not in {"pre_condition", "post_condition"}:
            normalized_type = "pre_condition"

        type_instruction = (
            "질문은 함수 실행 전에 입력/상태를 추론하게 만드세요."
            if normalized_type == "pre_condition"
            else "질문은 로직 실행 후 상태/부작용 변화를 추론하게 만드세요."
        )

        contents = _join_prompt_sections(
            "당신은 코드 학습 플랫폼의 맥락 추론 문제 생성기입니다.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"title": 문자열, "snippet": 문자열, "prompt": 문자열, '
            '"inference_type": "pre_condition|post_condition", "expected_facets": 문자열 배열, '
            '"reference_report": 문자열, "difficulty": 문자열}\n\n'
            f"문제 ID: {problem_id}\n"
            f"트랙: {track_id}\n"
            f"언어: {language_id}\n"
            f"난이도: {difficulty}\n"
            f"출제 타입: {normalized_type}\n"
            f"복잡도 프로파일: {complexity_profile}\n",
            _history_block(
                history_context,
                "최근 맥락 추론 문제 기록입니다. 동일한 시나리오/질문을 피하고 새로운 시스템 문맥으로 생성하세요.",
                "",
            ),
            "요구사항:\n"
            "- snippet은 전체 프로그램이 아니라 부분 코드(6~24줄)로 작성하세요.\n"
            "- prompt는 단일 질문 1개만 제공하세요.\n"
            f"- {type_instruction}\n"
            "- expected_facets에는 정답 핵심 포인트를 3~6개의 짧은 토큰으로 작성하세요.\n"
            "- reference_report는 제출 직후 공개할 모범 추론 리포트를 한국어로 작성하세요.\n"
            "- snippet에 정답을 직접 암시하는 주석/문장을 넣지 마세요.\n",
        )
        data = self._request_json(contents, use_generation_request=False)

        snippet = _strip_comments(data.get("snippet", ""), language_id).rstrip()
        if not snippet:
            snippet = _strip_comments(data.get("code", ""), language_id).rstrip()
        prompt = str(data.get("prompt") or "").strip()
        if not prompt:
            prompt = "주어진 코드 조각을 바탕으로 시스템 맥락을 추론해 리포트를 작성하세요."

        result_type = str(data.get("inference_type") or normalized_type).strip().lower()
        if result_type not in {"pre_condition", "post_condition"}:
            result_type = normalized_type

        expected_facets = _normalize_context_inference_facets(data.get("expected_facets"))
        reference_report = str(data.get("reference_report") or "").strip()
        if not reference_report:
            reference_lines = [f"- {facet}" for facet in expected_facets[:5]]
            reference_report = "다음 맥락 포인트를 모두 다루는 추론 리포트를 작성해야 합니다.\n" + "\n".join(reference_lines)

        return _base_payload(
            problem_id,
            mode,
            data.get("difficulty", difficulty),
            language_id,
            title=data.get("title") or "맥락 추론 문제",
            snippet=snippet,
            prompt=prompt,
            inference_type=result_type,
            expected_facets=expected_facets,
            reference_report=reference_report,
            complexity_profile=complexity_profile,
        )

    def generate_refactoring_choice_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        complexity_profile: str,
        constraint_count: int,
        history_context: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        self._require_client()

        normalized_constraint_count = max(2, int(constraint_count or 3))

        contents = _join_prompt_sections(
            "당신은 코드 학습 플랫폼의 Refactoring Choice 문제 생성기입니다.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"title": 문자열, "scenario": 문자열, "constraints": 문자열 배열, '
            '"options": [{"option_id":"A|B|C","title":문자열,"code":문자열}], '
            '"prompt": 문자열, "decision_facets": 문자열 배열, "best_option":"A|B|C", '
            '"option_reviews":[{"option_id":"A|B|C","summary":문자열}], '
            '"reference_report": 문자열, "difficulty": 문자열}\n\n'
            f"문제 ID: {problem_id}\n"
            f"트랙: {track_id}\n"
            f"언어: {language_id}\n"
            f"난이도: {difficulty}\n"
            f"복잡도 프로파일: {complexity_profile}\n"
            f"필수 제약 개수: {normalized_constraint_count}\n"
            f"facet taxonomy: {list(_REFACTORING_CHOICE_FACET_TAXONOMY)}\n",
            _history_block(
                history_context,
                "최근 최적의 선택 문제 기록입니다. 동일한 제약/코드 스타일 조합을 피하고 새로운 시나리오를 생성하세요.",
                "",
            ),
            "요구사항:\n"
            f"- constraints는 정확히 {normalized_constraint_count}개를 생성하세요.\n"
            "- options는 정확히 A/B/C 3개를 제공하고, 동일 기능을 수행하지만 trade-off가 달라야 합니다.\n"
            "- best_option은 반드시 하나만 지정하세요.\n"
            "- decision_facets는 taxonomy에서 3~4개만 고르세요.\n"
            "- option_reviews는 A/B/C 각각 1개씩 요약을 제공하세요.\n"
            "- prompt는 학습자에게 최적안을 선택하고 근거를 작성하게 지시하세요.\n"
            "- reference_report는 제출 직후 공개할 의사결정 메모 형식으로 작성하세요.\n"
            "- 코드에는 정답을 직접 노출하는 주석을 넣지 마세요.\n",
        )
        data = self._request_json(contents, on_text_delta=on_text_delta)

        title = str(data.get("title") or "").strip() or "최적의 선택 문제"
        scenario = str(data.get("scenario") or "").strip()
        prompt = str(data.get("prompt") or "").strip() or "A/B/C 옵션 중 최적안을 선택하고 근거를 작성하세요."

        constraints = [
            str(item or "").strip()
            for item in (data.get("constraints") or [])
            if str(item or "").strip()
        ]
        if len(constraints) > normalized_constraint_count:
            constraints = constraints[:normalized_constraint_count]
        while len(constraints) < normalized_constraint_count:
            constraints.append(f"제약 조건 {len(constraints) + 1}")

        options = _normalize_refactoring_choice_options(data.get("options"))
        for option in options:
            option["code"] = _strip_comments(option.get("code", ""), language_id).rstrip()

        decision_facets = _normalize_refactoring_choice_facets(data.get("decision_facets"))
        best_option = str(data.get("best_option") or "A").strip().upper()
        if best_option not in {"A", "B", "C"}:
            best_option = "A"

        option_reviews = _normalize_refactoring_choice_option_reviews(data.get("option_reviews"))
        reference_report = str(data.get("reference_report") or "").strip()
        if not reference_report:
            reference_report = (
                f"권장 선택지는 {best_option}입니다.\n"
                "제약 조건과 trade-off를 기준으로 성능/유지보수/안전성을 비교해 의사결정을 설명하세요."
            )

        return _base_payload(
            problem_id,
            mode,
            data.get("difficulty", difficulty),
            language_id,
            title=title,
            scenario=scenario,
            constraints=constraints,
            options=options,
            prompt=prompt,
            decision_facets=decision_facets,
            best_option=best_option,
            option_reviews=option_reviews,
            reference_report=reference_report,
            complexity_profile=complexity_profile,
        )

    def generate_code_blame_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        candidate_count: int,
        culprit_count: int,
        decision_facets: list[str],
        history_context: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        self._require_client()

        normalized_candidate_count = max(3, min(5, int(candidate_count or 3)))
        normalized_culprit_count = 2 if int(culprit_count or 1) >= 2 else 1
        option_ids = list(("A", "B", "C", "D", "E")[:normalized_candidate_count])
        normalized_facets = _normalize_code_blame_facets(decision_facets)

        contents = _join_prompt_sections(
            "당신은 코드 학습 플랫폼의 Code Blame Game 문제 생성기입니다.\n"
            "반드시 JSON으로만 답변하세요.\n"
            '{"title": 문자열, "error_log": 문자열, '
            '"commits": [{"option_id":"A|B|C|D|E","title":문자열,"diff":문자열}], '
            '"prompt": 문자열, "decision_facets": 문자열 배열, '
            '"culprit_commits": 문자열 배열, '
            '"commit_reviews":[{"option_id":"A|B|C|D|E","summary":문자열}], '
            '"reference_report": 문자열, "difficulty": 문자열}\n\n'
            f"문제 ID: {problem_id}\n"
            f"트랙: {track_id}\n"
            f"언어: {language_id}\n"
            f"난이도: {difficulty}\n"
            f"후보 커밋 수: {normalized_candidate_count}\n"
            f"범인 커밋 수: {normalized_culprit_count}\n"
            f"사용 option_id: {option_ids}\n"
            f"facet taxonomy: {list(_CODE_BLAME_FACET_TAXONOMY)}\n"
            f"권장 decision_facets: {normalized_facets}\n",
            _history_block(
                history_context,
                "최근 범인 찾기 문제 기록입니다. 동일한 장애 로그/커밋 패턴을 피하고 새로운 시나리오를 생성하세요.",
                "",
            ),
            "요구사항:\n"
            f"- commits는 option_id {option_ids}를 사용해 정확히 {normalized_candidate_count}개를 제공하세요.\n"
            "- 각 diff는 실제 git diff처럼 보이되, 범인 여부를 직접 노출하는 문장을 넣지 마세요.\n"
            f"- culprit_commits는 {normalized_culprit_count}개를 선택하고 commits의 option_id만 사용하세요.\n"
            "- error_log는 서버 장애 로그 형태로 작성하세요.\n"
            "- decision_facets는 taxonomy에서 3~4개를 고르세요.\n"
            "- commit_reviews는 모든 커밋에 대해 1개씩 요약을 제공하세요.\n"
            "- prompt는 학습자에게 범인 커밋 선택 + 근거 리포트를 요구하세요.\n"
            "- reference_report는 제출 직후 공개할 모범 추론 리포트를 작성하세요.\n",
        )
        data = self._request_json(contents, on_text_delta=on_text_delta)

        title = str(data.get("title") or "").strip() or "범인 찾기 문제"
        error_log = str(data.get("error_log") or data.get("errorLog") or "").rstrip()
        prompt = str(data.get("prompt") or "").strip() or "에러 로그와 diff를 비교해 범인 커밋을 추리하세요."

        commits = _normalize_code_blame_commits(data.get("commits"), normalized_candidate_count)
        option_ids = [row["optionId"] for row in commits]
        culprit_commits = _normalize_code_blame_option_ids(data.get("culprit_commits"), option_ids)
        if normalized_culprit_count == 1:
            culprit_commits = culprit_commits[:1]
        else:
            culprit_commits = culprit_commits[:2]
        if not culprit_commits:
            culprit_commits = option_ids[: min(normalized_culprit_count, len(option_ids))]
        if normalized_culprit_count == 2 and len(culprit_commits) < 2 and len(option_ids) >= 2:
            culprit_commits = option_ids[:2]

        final_facets = _normalize_code_blame_facets(data.get("decision_facets") or normalized_facets)
        commit_reviews = _normalize_code_blame_commit_reviews(data.get("commit_reviews"), option_ids)
        reference_report = str(data.get("reference_report") or "").strip()
        if not reference_report:
            culprit_label = ", ".join(culprit_commits)
            reference_report = (
                f"범인 커밋은 {culprit_label}입니다.\n"
                "로그 증거와 diff 변경점을 연결해 장애 메커니즘, 영향 범위, 복구/검증 전략을 설명하세요."
            )

        return _base_payload(
            problem_id,
            mode,
            data.get("difficulty", difficulty),
            language_id,
            title=title,
            error_log=error_log,
            commits=commits,
            prompt=prompt,
            decision_facets=final_facets,
            culprit_commits=culprit_commits,
            commit_reviews=commit_reviews,
            reference_report=reference_report,
        )

    def generate_single_file_analysis_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        return self._generate_workspace_analysis_problem_sync(
            problem_id=problem_id,
            track_id=track_id,
            language_id=language_id,
            difficulty=difficulty,
            mode=mode,
            history_context=history_context,
            on_text_delta=on_text_delta,
            intro="당신은 코드 학습 플랫폼의 단일 파일 분석 문제 생성기입니다.",
            language_label="주 언어",
            history_header="최근 단일 파일 분석 문제 기록입니다. 동일한 파일 구조와 질문을 피하고 새로운 문제를 생성하세요.",
            history_guidance="",
            requirements=[
                "files는 정확히 1개만 제공하세요.",
                "content는 14~40줄 사이의 실제 코드처럼 보이는 단일 파일이어야 합니다.",
                "prompt는 이 파일을 읽고 어떤 로직/상태/예외 흐름을 설명해야 하는지 한국어로 지시하세요.",
                "checklist는 분석 포인트 3~4개를 한국어 문자열 배열로 작성하세요.",
                "reference_report는 제출 직후 공개할 모범 분석 리포트를 한국어로 작성하세요.",
                "summary는 문제 시나리오를 1~2문장으로 요약하세요.",
                "코드에는 정답을 직접 노출하는 주석을 넣지 마세요.",
            ],
            min_files=1,
            max_files=1,
            default_role="entrypoint",
            checklist_limit=4,
            checklist_min_count=3,
            checklist_fallback=[
                "핵심 진입 함수와 반환 값을 추적하세요.",
                "상태 변경과 예외 처리 분기를 정리하세요.",
                "테스트가 필요한 경계 조건을 요약하세요.",
            ],
            reference_fallback=(
                "이 파일의 핵심 진입 함수부터 반환 지점까지 제어 흐름을 순서대로 설명하고, "
                "상태가 바뀌는 지점과 예외 처리 분기를 함께 정리하세요."
            ),
            title_fallback="단일 파일 분석 문제",
            summary_fallback="단일 파일의 핵심 제어 흐름을 설명하세요.",
            prompt_fallback="코드를 읽고 핵심 제어 흐름을 설명하세요.",
            workspace_fallback="single-file-analysis.workspace",
        )

    def generate_multi_file_analysis_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        return self._generate_workspace_analysis_problem_sync(
            problem_id=problem_id,
            track_id=track_id,
            language_id=language_id,
            difficulty=difficulty,
            mode=mode,
            history_context=history_context,
            on_text_delta=on_text_delta,
            intro="당신은 코드 학습 플랫폼의 다중 파일 분석 문제 생성기입니다.",
            language_label="언어",
            history_header="최근 다중 파일 분석 문제 기록입니다. 동일한 호출 흐름과 구성요소를 피하고 새 시나리오를 생성하세요.",
            history_guidance="",
            requirements=[
                "files는 2~6개 사이로 생성하세요.",
                "모든 파일은 같은 언어 계열을 사용하세요.",
                "파일 역할은 controller/service/repository/helper/entity 중 실제에 맞게 작성하세요.",
                "prompt는 파일 간 호출 흐름과 책임 분리를 설명하게 지시하세요.",
                "checklist는 분석 포인트 3~5개를 한국어 배열로 작성하세요.",
                "reference_report는 제출 직후 공개할 모범 분석 리포트를 한국어로 작성하세요.",
                "코드에는 정답을 직접 노출하는 주석을 넣지 마세요.",
            ],
            min_files=2,
            max_files=6,
            default_role="module",
            checklist_limit=5,
            checklist_min_count=3,
            checklist_fallback=[
                "진입점에서 실제 비즈니스 로직까지 호출 순서를 정리하세요.",
                "파일별 책임과 결합 지점을 분리해서 설명하세요.",
                "중복 책임이나 테스트 취약 구간을 찾으세요.",
            ],
            reference_fallback=(
                "파일 간 호출 흐름을 진입점부터 순서대로 정리하고, 각 파일의 책임과 결합 지점을 구분해 설명하세요. "
                "특히 controller, service, repository 사이에서 데이터가 어떻게 이동하는지 포함하세요."
            ),
            title_fallback="다중 파일 분석 문제",
            summary_fallback="여러 파일 사이의 호출 흐름을 추적하세요.",
            prompt_fallback="파일 간 호출 흐름과 책임 분리를 설명하세요.",
            workspace_fallback="multi-file-analysis.workspace",
        )

    def generate_fullstack_analysis_problem_sync(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        return self._generate_workspace_analysis_problem_sync(
            problem_id=problem_id,
            track_id=track_id,
            language_id=language_id,
            difficulty=difficulty,
            mode=mode,
            history_context=history_context,
            on_text_delta=on_text_delta,
            intro="당신은 코드 학습 플랫폼의 풀스택 코드 분석 문제 생성기입니다.",
            language_label="주 백엔드 언어",
            history_header="최근 풀스택 분석 문제 기록입니다. 동일한 화면/API 흐름을 피하고 새로운 엔드투엔드 시나리오를 생성하세요.",
            history_guidance="",
            requirements=[
                "files는 3~8개 사이로 생성하세요.",
                "frontend 역할 파일과 backend 역할 파일을 모두 포함하세요.",
                "frontend는 typescript/tsx/javascript 중 하나를, backend는 주 백엔드 언어를 사용하세요.",
                "prompt는 사용자 액션이 API 호출과 상태 반영으로 이어지는 전체 흐름을 설명하게 지시하세요.",
                "checklist는 이벤트 시작점, API 경유, 상태 반영, 장애 지점 분석을 포함한 4~5개 포인트로 작성하세요.",
                "reference_report는 제출 직후 공개할 모범 분석 리포트를 한국어로 작성하세요.",
                "코드에는 정답을 직접 노출하는 주석을 넣지 마세요.",
            ],
            min_files=3,
            max_files=8,
            default_role="backend",
            checklist_limit=5,
            checklist_min_count=4,
            checklist_fallback=[
                "사용자 액션이 어디서 시작되는지 확인하세요.",
                "API 호출과 서버 진입점을 연결해서 설명하세요.",
                "응답이 상태와 UI에 어떻게 반영되는지 추적하세요.",
                "장애가 생길 수 있는 경계와 복구 포인트를 정리하세요.",
            ],
            reference_fallback=(
                "사용자 액션이 프런트엔드에서 어떻게 시작되고 API 호출을 거쳐 서버 처리와 데이터 저장으로 이어지는지 설명하세요. "
                "그 뒤 응답이 상태와 UI에 어떻게 반영되는지, 실패 시 어떤 경계와 복구 포인트가 있는지도 포함하세요."
            ),
            title_fallback="풀스택 코드 분석 문제",
            summary_fallback="프런트엔드와 백엔드 사이의 전체 호출 흐름을 분석하세요.",
            prompt_fallback="사용자 액션부터 UI 반영까지의 전체 흐름을 설명하세요.",
            workspace_fallback="fullstack-analysis.workspace",
        )

    async def generate(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
        retry_context: Optional[Dict[str, str]] = None,
    ) -> GeneratedProblem:
        return await asyncio.to_thread(
            self.generate_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            history_context,
            retry_context,
        )

    async def generate_code_block_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_code_block_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            history_context,
        )

    async def generate_code_error_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_code_error_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            history_context,
        )

    async def generate_auditor_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        trap_count: int,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_auditor_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            trap_count,
            history_context,
        )

    async def generate_context_inference_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        inference_type: str,
        complexity_profile: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_context_inference_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            inference_type,
            complexity_profile,
            history_context,
        )

    async def generate_refactoring_choice_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        complexity_profile: str,
        constraint_count: int,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_refactoring_choice_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            complexity_profile,
            constraint_count,
            history_context,
        )

    async def generate_code_blame_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        candidate_count: int,
        culprit_count: int,
        decision_facets: list[str],
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_code_blame_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            candidate_count,
            culprit_count,
            decision_facets,
            history_context,
        )

    async def generate_single_file_analysis_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_single_file_analysis_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            history_context,
        )

    async def generate_multi_file_analysis_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_multi_file_analysis_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            history_context,
        )

    async def generate_fullstack_analysis_problem(
        self,
        problem_id: str,
        track_id: str,
        language_id: str,
        difficulty: str,
        mode: str,
        history_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_fullstack_analysis_problem_sync,
            problem_id,
            track_id,
            language_id,
            difficulty,
            mode,
            history_context,
        )

    def _run_generation_request(
        self,
        contents: str,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ):
        try:
            return self._generate_with_thinking(contents, on_text_delta=on_text_delta)
        except TypeError as exc:
            if "on_text_delta" not in str(exc):
                raise
            return self._generate_with_thinking(contents)

    def _generate_with_thinking(
        self,
        contents: str,
        on_text_delta: Optional[Callable[[str], None]] = None,
    ):
        if not self.client:  # pragma: no cover
            raise RuntimeError("AI 클라이언트가 초기화되지 않았습니다")

        token = self.metrics.start_ai_call(provider="google", operation="problem_generation")
        config_with_thinking = types.GenerateContentConfig(
            temperature=1.0,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        try:
            def _stream_content(config: types.GenerateContentConfig):
                assembled_text = ""
                for chunk in self.client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=config,
                ):
                    chunk_text = _response_text(chunk)
                    if not chunk_text:
                        continue
                    if chunk_text.startswith(assembled_text):
                        delta = chunk_text[len(assembled_text) :]
                        assembled_text = chunk_text
                    else:
                        delta = chunk_text
                        assembled_text += delta
                    if delta and callable(on_text_delta):
                        on_text_delta(delta)
                return SimpleNamespace(text=assembled_text)

            try:
                if callable(on_text_delta):
                    response = _stream_content(config_with_thinking)
                else:
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config_with_thinking,
                    )
            except Exception as exc:
                if "thinking" not in str(exc).lower():
                    raise
                fallback_config = types.GenerateContentConfig(temperature=1.0)
                if callable(on_text_delta):
                    response = _stream_content(fallback_config)
                else:
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=fallback_config,
                    )

            self.metrics.end_ai_call(token, success=True)
            return response
        except Exception:
            self.metrics.end_ai_call(token, success=False)
            raise
