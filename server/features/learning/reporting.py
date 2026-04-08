from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from server.features.learning.content import LANGUAGES

_REPORT_CONTEXT_LIMIT = 15
_REPORT_SIGNAL_LIMIT = 5


def trend_summary(recent_accuracy: float | None, previous_accuracy: float | None) -> str:
    if recent_accuracy is None or previous_accuracy is None:
        return "비교할 데이터가 부족합니다."
    change = round(recent_accuracy - previous_accuracy, 1)
    if change > 0:
        return f"최근 정확도가 과거 대비 {change}%p 상승했습니다."
    if change < 0:
        return f"최근 정확도가 과거 대비 {abs(change)}%p 하락했습니다."
    return "최근 정확도가 과거와 동일합니다."


def _mode_from_event(item: Dict[str, Any]) -> str:
    if item.get("type") == "code_calc_event":
        return "code-calc"
    if item.get("type") == "code_error_event":
        return "code-error"
    if item.get("type") == "code_arrange_event":
        return "code-arrange"
    if item.get("type") == "auditor_event":
        return "auditor"
    if item.get("type") == "context_inference_event":
        return "context-inference"
    if item.get("type") == "refactoring_choice_event":
        return "refactoring-choice"
    if item.get("type") == "code_blame_event":
        return "code-blame"
    if item.get("type") == "single_file_analysis_event":
        return "single-file-analysis"
    if item.get("type") == "multi_file_analysis_event":
        return "multi-file-analysis"
    if item.get("type") == "fullstack_analysis_event":
        return "fullstack-analysis"
    return item.get("mode") or "practice"


def _build_prompt(mode: str, instance: Dict[str, Any]) -> str:
    prompt = instance.get("prompt")
    if prompt:
        return prompt
    if mode == "code-block":
        return "빈칸을 채워 올바른 선택지를 고르세요."
    if mode == "code-calc":
        return "코드를 실행했을 때 출력될 값을 예측하세요."
    if mode == "code-error":
        return "오류가 있는 코드 블록을 선택하세요."
    if mode == "code-arrange":
        return "코드 블록을 올바른 순서로 배열하세요."
    if mode == "auditor":
        return "코드의 치명적 함정을 찾아 감사 리포트를 작성하세요."
    if mode == "context-inference":
        return "코드 맥락을 추론해 리포트를 작성하세요."
    if mode == "refactoring-choice":
        return "A/B/C 옵션 중 최적의 코드를 선택하고 근거를 작성하세요."
    if mode == "code-blame":
        return "에러 로그와 커밋 diff를 비교해 범인 커밋을 추리하세요."
    if mode == "single-file-analysis":
        return "단일 파일 코드를 분석하고 개선 리포트를 작성하세요."
    if mode == "multi-file-analysis":
        return "여러 파일의 상호작용을 분석하고 개선 리포트를 작성하세요."
    if mode == "fullstack-analysis":
        return "프런트엔드와 백엔드 흐름을 함께 분석하고 개선 리포트를 작성하세요."
    return "문제를 해결해 주세요."


def _extract_code(instance: Dict[str, Any]) -> str | None:
    code = instance.get("code")
    if code:
        return code
    files = instance.get("files")
    if isinstance(files, list):
        rendered: list[str] = []
        for item in files[:6]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("name") or "").strip()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            rendered.append(f"File: {path}\n{content}" if path else content)
        if rendered:
            return "\n\n".join(rendered)
    snippet = instance.get("snippet")
    if snippet:
        return snippet
    error_log = instance.get("error_log")
    if error_log:
        return error_log
    blocks = instance.get("blocks")
    if isinstance(blocks, list):
        if blocks and isinstance(blocks[0], dict):
            return "\n".join(block.get("code", "") for block in blocks)
        return "\n".join(str(block) for block in blocks)
    return None


def _build_answer(event: Dict[str, Any], instance: Dict[str, Any]) -> str | None:
    if event.get("explanation"):
        return event.get("explanation")

    event_type = event.get("type")
    if event_type == "code_calc_event":
        submitted = (event.get("submitted_output") or "").strip()
        return f"제출 출력: {submitted}" if submitted else None

    if event_type == "code_error_event":
        selected = event.get("selected_index")
        if selected is not None:
            return f"선택 블록: {int(selected) + 1}번"
        return None

    if event_type == "code_arrange_event":
        order = event.get("submitted_order") or []
        if order:
            return f"블록 {len(order)}개 순서 제출"
        return None

    if event_type == "learning_event" and event.get("mode") == "code-block":
        selected = event.get("selected_option")
        options = instance.get("options") or []
        if isinstance(selected, int) and 0 <= selected < len(options):
            return f"선택: {options[selected]}"
        if selected is not None:
            return f"선택 옵션: {selected}"

    if event_type == "auditor_event":
        submitted = (event.get("report") or "").strip()
        return submitted or None
    if event_type == "context_inference_event":
        submitted = (event.get("report") or "").strip()
        return submitted or None
    if event_type == "refactoring_choice_event":
        submitted = (event.get("report") or "").strip()
        return submitted or None
    if event_type == "code_blame_event":
        submitted = (event.get("report") or "").strip()
        return submitted or None
    if event_type == "single_file_analysis_event":
        submitted = (event.get("report") or "").strip()
        return submitted or None
    if event_type == "multi_file_analysis_event":
        submitted = (event.get("report") or "").strip()
        return submitted or None
    if event_type == "fullstack_analysis_event":
        submitted = (event.get("report") or "").strip()
        return submitted or None

    return None


def _build_summary(event: Dict[str, Any], instance: Dict[str, Any], mode: str) -> str:
    feedback = event.get("feedback")
    if isinstance(feedback, dict) and feedback.get("summary"):
        return feedback.get("summary") or ""

    title = instance.get("title")
    if title:
        return title

    return {
        "code-block": "코드 블록",
        "code-calc": "코드 계산",
        "code-error": "오류 찾기",
        "code-arrange": "코드 배치",
        "auditor": "감사관 모드",
        "context-inference": "맥락 추론",
        "refactoring-choice": "최적의 선택",
        "code-blame": "범인 찾기",
        "single-file-analysis": "단일 파일 분석",
        "multi-file-analysis": "다중 파일 분석",
        "fullstack-analysis": "풀스택 코드 분석",
        "diagnostic": "진단 문제",
        "practice": "맞춤 문제",
    }.get(mode, "학습 기록")


def _clip_detail_text(value: Any, limit: int = 600) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 18, 0)].rstrip()}...(truncated)"


def _normalize_detail_list(value: Any, *, limit: int = 6, item_limit: int = 160) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        if isinstance(item, dict):
            normalized = _clip_detail_text(
                item.get("label")
                or item.get("optionId")
                or item.get("path")
                or item.get("title")
                or item.get("summary")
                or item.get("code")
                or item.get("content")
                or item,
                item_limit,
            )
        else:
            normalized = _clip_detail_text(item, item_limit)
        if not normalized or normalized in rows:
            continue
        rows.append(normalized)
        if len(rows) >= limit:
            break
    return rows


def _normalize_counter_rows(
    counter: Counter[str],
    *,
    limit: int = _REPORT_SIGNAL_LIMIT,
    item_limit: int = 160,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, count in counter.most_common(limit):
        normalized = _clip_detail_text(label, item_limit)
        if not normalized or count <= 0:
            continue
        rows.append({"label": normalized, "count": int(count)})
    return rows


def _build_history_context_from_records(detail_records: List[Dict[str, Any]]) -> str:
    if not detail_records:
        return "최근 학습 기록이 없습니다."

    lines: list[str] = []
    for idx, record in enumerate(detail_records[:_REPORT_CONTEXT_LIMIT], 1):
        evaluation = record.get("evaluation") if isinstance(record.get("evaluation"), dict) else {}
        question_context = record.get("questionContext") if isinstance(record.get("questionContext"), dict) else {}

        header = (
            f"{idx}. [{record.get('modeLabel') or record.get('mode') or 'practice'}] "
            f"{record.get('title') or '제목 없음'}"
        )
        meta_parts = [
            f"result={record.get('result') or '-'}",
            f"score={record.get('score') if record.get('score') is not None else 'N/A'}",
        ]
        if record.get("difficulty"):
            meta_parts.append(f"difficulty={record['difficulty']}")
        if record.get("language"):
            meta_parts.append(f"language={record['language']}")
        if record.get("durationSeconds") is not None:
            meta_parts.append(f"duration={record['durationSeconds']}s")
        lines.append(header)
        lines.append(f"   {' | '.join(meta_parts)}")

        prompt = _clip_detail_text(question_context.get("prompt"), 180)
        if prompt:
            lines.append(f"   question={prompt}")
        learner = _clip_detail_text(record.get("learnerResponse"), 260)
        if learner:
            lines.append(f"   learner={learner}")
        expected = _clip_detail_text(record.get("expectedAnswer"), 220)
        if expected:
            lines.append(f"   expected={expected}")

        feedback_summary = _clip_detail_text(
            evaluation.get("feedbackSummary") or evaluation.get("analysisSummary"),
            220,
        )
        if feedback_summary:
            lines.append(f"   feedback={feedback_summary}")
        comparison = _clip_detail_text(evaluation.get("comparison"), 260)
        if comparison:
            lines.append(f"   comparison={comparison}")
        missed_points = _normalize_detail_list(evaluation.get("missedPoints"), limit=3, item_limit=120)
        if missed_points:
            lines.append(f"   missed={'; '.join(missed_points)}")
        improvements = _normalize_detail_list(evaluation.get("improvements"), limit=3, item_limit=120)
        if improvements:
            lines.append(f"   improve={'; '.join(improvements)}")

    return "\n".join(lines)


def _build_evidence_from_records(detail_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    mode_counter: Counter[str] = Counter()
    result_counter: Counter[str] = Counter()
    missed_counter: Counter[str] = Counter()
    strength_counter: Counter[str] = Counter()
    improvement_counter: Counter[str] = Counter()
    duration_values: list[int] = []

    for record in detail_records:
        mode = _clip_detail_text(record.get("modeLabel") or record.get("mode"), 80)
        if mode:
            mode_counter[mode] += 1

        result = _clip_detail_text(record.get("result"), 40)
        if result:
            result_counter[result] += 1

        try:
            duration = record.get("durationSeconds")
            if duration is not None:
                duration_values.append(int(duration))
        except (TypeError, ValueError):
            pass

        evaluation = record.get("evaluation") if isinstance(record.get("evaluation"), dict) else {}
        for item in _normalize_detail_list(evaluation.get("missedPoints"), limit=6, item_limit=120):
            missed_counter[item] += 1
        for item in _normalize_detail_list(evaluation.get("strengths"), limit=6, item_limit=120):
            strength_counter[item] += 1
        for item in _normalize_detail_list(evaluation.get("improvements"), limit=6, item_limit=120):
            improvement_counter[item] += 1

    average_duration_seconds = None
    if duration_values:
        average_duration_seconds = round(sum(duration_values) / len(duration_values), 1)

    return {
        "recentModes": _normalize_counter_rows(mode_counter, item_limit=100),
        "recentResults": _normalize_counter_rows(result_counter, item_limit=60),
        "repeatedMissedPoints": _normalize_counter_rows(missed_counter, item_limit=120),
        "repeatedStrengths": _normalize_counter_rows(strength_counter, item_limit=120),
        "repeatedImprovements": _normalize_counter_rows(improvement_counter, item_limit=120),
        "averageDurationSeconds": average_duration_seconds,
        "detailRecordCount": len(detail_records),
    }


def _mode_label(mode: str) -> str:
    return {
        "analysis": "코드 분석",
        "code-block": "코드 블록",
        "code-calc": "코드 계산",
        "code-error": "오류 찾기",
        "code-arrange": "코드 배치",
        "auditor": "감사관 모드",
        "context-inference": "맥락 추론",
        "refactoring-choice": "최적의 선택",
        "code-blame": "범인 찾기",
        "single-file-analysis": "단일 파일 분석",
        "multi-file-analysis": "다중 파일 분석",
        "fullstack-analysis": "풀스택 코드 분석",
        "diagnostic": "진단",
        "practice": "맞춤 문제",
    }.get(mode, mode or "unknown")


def _build_legacy_expected_answer(event: Dict[str, Any]) -> str | None:
    mode = str(event.get("mode") or "").strip()
    if mode == "code-block":
        return _clip_detail_text(event.get("correct_option_text"))
    if mode == "code-calc":
        return _clip_detail_text(event.get("expected_output"))
    if mode == "code-error":
        correct_index = event.get("correct_index")
        try:
            return f"{int(correct_index) + 1}번 블록"
        except (TypeError, ValueError):
            return None
    if mode == "code-arrange":
        correct_order = event.get("correct_order")
        if isinstance(correct_order, list) and correct_order:
            return "정답 순서: " + " -> ".join(str(item) for item in correct_order[:8])
        return None
    if mode == "refactoring-choice":
        best_option = _clip_detail_text(event.get("best_option"), 40)
        if best_option:
            return f"권장 선택지: {best_option}"
    if mode == "code-blame":
        culprit_commits = _normalize_detail_list(event.get("culprit_commits"), limit=4, item_limit=40)
        if culprit_commits:
            return "범인 커밋: " + ", ".join(culprit_commits)
    reference_report = _clip_detail_text(event.get("reference_report"))
    if reference_report:
        return reference_report
    return None


def _build_legacy_response_comparison(event: Dict[str, Any]) -> str | None:
    mode = str(event.get("mode") or "").strip()
    is_correct = event.get("correct") is True

    if mode == "code-block":
        selected = _clip_detail_text(event.get("selected_option_text"))
        expected = _clip_detail_text(event.get("correct_option_text"))
        if selected and expected and not is_correct:
            return f"제출 선택지는 '{selected}'였고 정답은 '{expected}'였습니다."
        if selected and is_correct:
            return f"정답 선택지 '{selected}'를 맞혔습니다."

    if mode == "code-calc":
        submitted = _clip_detail_text(event.get("submitted_output"), 160)
        expected = _clip_detail_text(event.get("expected_output"), 160)
        if submitted and expected and not is_correct:
            return f"예상 출력 '{expected}' 대신 '{submitted}'를 제출했습니다."
        if submitted and is_correct:
            return f"출력 '{submitted}'를 정확히 예측했습니다."

    if mode == "code-error":
        selected_index = event.get("selected_index")
        correct_index = event.get("correct_index")
        try:
            selected_label = f"{int(selected_index) + 1}번 블록"
        except (TypeError, ValueError):
            selected_label = None
        try:
            correct_label = f"{int(correct_index) + 1}번 블록"
        except (TypeError, ValueError):
            correct_label = None
        if selected_label and correct_label and not is_correct:
            return f"{selected_label}을 골랐지만 실제 오류 블록은 {correct_label}였습니다."
        if selected_label and is_correct:
            return f"오류 블록 {selected_label}을 정확히 찾았습니다."

    if mode == "code-arrange":
        submitted_order = event.get("submitted_order")
        correct_order = event.get("correct_order")
        if isinstance(submitted_order, list) and isinstance(correct_order, list):
            mismatches = sum(1 for expected, submitted in zip(correct_order, submitted_order) if expected != submitted)
            if not is_correct:
                return f"블록 순서 {len(correct_order)}개 중 {mismatches}개 위치가 틀렸습니다."
            return f"블록 순서 {len(correct_order)}개를 모두 맞췄습니다."

    if mode == "refactoring-choice":
        selected_option = _clip_detail_text(event.get("selected_option"), 40)
        best_option = _clip_detail_text(event.get("best_option"), 40)
        if selected_option and best_option and selected_option != best_option:
            return f"사용자는 {selected_option}를 골랐고 권장 선택지는 {best_option}였습니다."
        if selected_option and best_option:
            return f"권장 선택지 {best_option}를 정확히 골랐습니다."

    if mode == "code-blame":
        selected_commits = _normalize_detail_list(event.get("selected_commits"), limit=4, item_limit=40)
        culprit_commits = _normalize_detail_list(event.get("culprit_commits"), limit=4, item_limit=40)
        if selected_commits and culprit_commits and set(selected_commits) != set(culprit_commits):
            return (
                f"사용자는 {', '.join(selected_commits)}를 지목했지만 "
                f"실제 범인 커밋은 {', '.join(culprit_commits)}였습니다."
            )
        if culprit_commits and is_correct:
            return f"범인 커밋 {', '.join(culprit_commits)}를 정확히 지목했습니다."

    feedback = event.get("feedback")
    if isinstance(feedback, dict):
        return _clip_detail_text(feedback.get("summary"))
    return None


def _build_legacy_detail_records(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    detail_records: List[Dict[str, Any]] = []
    for idx, event in enumerate(history[:_REPORT_CONTEXT_LIMIT], 1):
        mode = str(event.get("mode") or "").strip() or "practice"
        feedback = event.get("feedback") if isinstance(event.get("feedback"), dict) else {}
        score = event.get("score")
        duration = event.get("duration_seconds")
        try:
            duration_value = int(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_value = None

        question_context: Dict[str, Any] = {}
        prompt = _clip_detail_text(event.get("problem_prompt"))
        code = _clip_detail_text(event.get("problem_code"), 900)
        if prompt:
            question_context["prompt"] = prompt
        if code:
            question_context["codeOrContext"] = code

        options = _normalize_detail_list(event.get("problem_options"), limit=6, item_limit=200)
        if options:
            question_context["options"] = options

        commits = _normalize_detail_list(event.get("problem_commits"), limit=4, item_limit=220)
        if commits:
            question_context["commits"] = commits
        blocks = _normalize_detail_list(event.get("problem_blocks"), limit=8, item_limit=220)
        if blocks:
            question_context["blocks"] = blocks
        workspace_files = _normalize_detail_list(
            event.get("problem_files") or event.get("workspace_files"),
            limit=6,
            item_limit=220,
        )
        if workspace_files:
            question_context["workspaceFiles"] = workspace_files

        scenario = _clip_detail_text(event.get("problem_scenario"), 400)
        if scenario:
            question_context["scenario"] = scenario

        error_log = _clip_detail_text(event.get("problem_error_log"), 500)
        if error_log:
            question_context["errorLog"] = error_log

        learner_answer = _clip_detail_text(event.get("explanation"), 700)
        expected_answer = _build_legacy_expected_answer(event)
        comparison = _build_legacy_response_comparison(event)

        evaluation: Dict[str, Any] = {}
        feedback_summary = _clip_detail_text(feedback.get("summary"), 280)
        if feedback_summary:
            evaluation["feedbackSummary"] = feedback_summary

        strengths = _normalize_detail_list(feedback.get("strengths"))
        if strengths:
            evaluation["strengths"] = strengths

        improvements = _normalize_detail_list(feedback.get("improvements"))
        if improvements:
            evaluation["improvements"] = improvements

        found_types = _normalize_detail_list(event.get("found_types"))
        if found_types:
            evaluation["matchedPoints"] = found_types

        missed_types = _normalize_detail_list(event.get("missed_types"))
        if missed_types:
            evaluation["missedPoints"] = missed_types

        if comparison:
            evaluation["comparison"] = comparison

        reference_report = _clip_detail_text(event.get("reference_report"), 700)
        if reference_report:
            evaluation["referenceExplanation"] = reference_report
        option_reviews = _normalize_detail_list(event.get("option_reviews"), limit=6, item_limit=180)
        if option_reviews:
            evaluation["optionReviews"] = option_reviews
        commit_reviews = _normalize_detail_list(event.get("commit_reviews"), limit=6, item_limit=180)
        if commit_reviews:
            evaluation["commitReviews"] = commit_reviews

        record: Dict[str, Any] = {
            "attempt": idx,
            "mode": mode,
            "modeLabel": _mode_label(mode),
            "title": _clip_detail_text(event.get("problem_title"), 160) or "제목 없음",
            "result": "correct" if event.get("correct") is True else "incorrect",
            "summary": _clip_detail_text(event.get("summary"), 240),
            "questionContext": question_context,
            "evaluation": evaluation,
        }
        if learner_answer:
            record["learnerResponse"] = learner_answer
        if expected_answer:
            record["expectedAnswer"] = expected_answer
        if score is not None:
            record["score"] = score
        if duration_value is not None:
            record["durationSeconds"] = duration_value
        difficulty = _clip_detail_text(event.get("difficulty"), 40)
        if difficulty:
            record["difficulty"] = difficulty
        language = _clip_detail_text(event.get("language"), 40)
        if language:
            record["language"] = language
        created_at = _clip_detail_text(event.get("created_at"), 60)
        if created_at:
            record["submittedAt"] = created_at
        detail_records.append(record)
    return detail_records


def user_history(
    service: Any,
    username: str,
    *,
    duration_seconds: Callable[[str | None, str | None], float | None],
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    storage = service._get_user_storage(username)
    events = service._collect_attempt_events(storage)
    instances = service._instances_by_id(storage)

    enriched_events: List[Dict[str, Any]] = []
    for event in events:
        created_at = event.get("created_at")
        if not created_at:
            continue

        problem_id = event.get("problem_id")
        instance = instances.get(problem_id, {}) if problem_id else {}
        mode = _mode_from_event(event)

        problem_title = instance.get("title") or "제목 없음"
        problem_code = _extract_code(instance)
        problem_blocks = instance.get("blocks")
        problem_options = instance.get("options")
        problem_commits = instance.get("commits")
        problem_prompt = _build_prompt(mode, instance)
        duration_value = duration_seconds(instance.get("created_at"), created_at)

        enriched_event = dict(event)
        enriched_event["mode"] = mode
        enriched_event["problem_title"] = problem_title
        enriched_event["problem_code"] = problem_code

        if problem_blocks is not None:
            enriched_event["problem_blocks"] = problem_blocks
        if problem_options is not None:
            enriched_event["problem_options"] = problem_options
        if problem_commits is not None:
            enriched_event["problem_commits"] = problem_commits

        enriched_event["problem_prompt"] = problem_prompt
        enriched_event["duration_seconds"] = duration_value
        enriched_event["summary"] = _build_summary(event, instance, mode)
        enriched_event["explanation"] = _build_answer(event, instance)

        if event.get("type") == "auditor_event":
            enriched_event["found_types"] = event.get("found_types") or []
            enriched_event["missed_types"] = event.get("missed_types") or []
            enriched_event["reference_report"] = event.get("reference_report") or ""
        if event.get("type") == "context_inference_event":
            enriched_event["found_types"] = event.get("found_types") or []
            enriched_event["missed_types"] = event.get("missed_types") or []
            enriched_event["reference_report"] = event.get("reference_report") or ""
            enriched_event["inference_type"] = event.get("inference_type") or instance.get("inference_type")
        if event.get("type") == "refactoring_choice_event":
            enriched_event["found_types"] = event.get("found_types") or []
            enriched_event["missed_types"] = event.get("missed_types") or []
            enriched_event["reference_report"] = event.get("reference_report") or ""
            enriched_event["selected_option"] = event.get("selected_option") or ""
            enriched_event["best_option"] = event.get("best_option") or instance.get("best_option") or ""
            enriched_event["option_reviews"] = event.get("option_reviews") or instance.get("option_reviews") or []
            enriched_event["problem_scenario"] = instance.get("scenario") or ""
        if event.get("type") == "code_blame_event":
            enriched_event["found_types"] = event.get("found_types") or []
            enriched_event["missed_types"] = event.get("missed_types") or []
            enriched_event["reference_report"] = event.get("reference_report") or ""
            enriched_event["selected_commits"] = event.get("selected_commits") or []
            enriched_event["culprit_commits"] = event.get("culprit_commits") or instance.get("culprit_commits") or []
            enriched_event["commit_reviews"] = event.get("commit_reviews") or instance.get("commit_reviews") or []
            enriched_event["problem_error_log"] = instance.get("error_log") or ""

        if mode == "code-block" and isinstance(problem_options, list):
            selected_idx = event.get("selected_option")
            correct_idx = event.get("correct_answer_index")
            if correct_idx is None:
                answer_index = instance.get("answer_index")
                enriched_event["answer_index"] = answer_index
                correct_idx = answer_index

            try:
                selected_idx = int(selected_idx) if selected_idx is not None else None
            except (TypeError, ValueError):
                selected_idx = None

            try:
                correct_idx = int(correct_idx) if correct_idx is not None else None
            except (TypeError, ValueError):
                correct_idx = None

            if selected_idx is not None and 0 <= selected_idx < len(problem_options):
                enriched_event["selected_option_text"] = problem_options[selected_idx]
            if correct_idx is not None and 0 <= correct_idx < len(problem_options):
                enriched_event["correct_option_text"] = problem_options[correct_idx]

        enriched_events.append(enriched_event)

    ordered = sorted(enriched_events, key=lambda item: item.get("created_at", ""), reverse=True)
    if limit is None:
        return ordered
    try:
        effective_limit = max(int(limit), 1)
    except (TypeError, ValueError):
        return ordered
    return ordered[:effective_limit]


def learning_report(
    service: Any,
    username: str,
    *,
    accuracy_from_events: Callable[[List[dict]], float | None],
    duration_seconds: Callable[[str | None, str | None], float | None],
) -> Dict[str, Any]:
    storage = service._get_user_storage(username)
    history = service.user_history(username)
    attempts = len(history)
    correct_count = sum(1 for event in history if event.get("correct") is True)
    accuracy = round((correct_count / attempts) * 100, 1) if attempts else 0.0

    recent_window = history[:5]
    previous_window = history[5:10]
    recent_accuracy = accuracy_from_events(recent_window)
    previous_accuracy = accuracy_from_events(previous_window)

    recent_history: List[Dict[str, Any]] = []
    for event in history[:_REPORT_CONTEXT_LIMIT]:
        enriched_event = dict(event)
        if enriched_event.get("duration_seconds") is None:
            instance = service._get_problem_instance(storage, event.get("problem_id"))
            duration = duration_seconds((instance or {}).get("created_at"), event.get("created_at"))
            if duration is not None:
                enriched_event["duration_seconds"] = duration
        recent_history.append(enriched_event)
    detail_records = _build_legacy_detail_records(recent_history)
    history_context = _build_history_context_from_records(detail_records)
    score_values: list[float] = []
    for event in recent_history:
        score = event.get("score")
        try:
            if score is not None:
                score_values.append(float(score))
        except (TypeError, ValueError):
            pass
    evidence = _build_evidence_from_records(detail_records)
    metric_snapshot: Dict[str, Any] = {
        "attempts": attempts,
        "accuracy": accuracy if attempts > 0 else None,
        "avgScore": round(sum(score_values) / len(score_values), 1) if score_values else None,
        "trend": trend_summary(recent_accuracy, previous_accuracy),
        "correct": correct_count,
        "incorrect": max(attempts - correct_count, 0),
        **evidence,
    }
    solution_plan = service.ai_client.generate_learning_solution_report(
        history_context=history_context,
        metric_snapshot=metric_snapshot,
        detail_records=detail_records,
    )

    return {
        "reportId": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        **solution_plan,
        "metricSnapshot": metric_snapshot,
        "detailRecords": detail_records,
        "learningEvidence": evidence,
    }

