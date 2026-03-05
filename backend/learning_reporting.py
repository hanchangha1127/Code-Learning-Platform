from __future__ import annotations

from typing import Any, Callable, Dict, List

from backend.content import LANGUAGES


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
    return "문제를 해결해 주세요."


def _extract_code(instance: Dict[str, Any]) -> str | None:
    code = instance.get("code")
    if code:
        return code
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

    return None


def _build_summary(event: Dict[str, Any], instance: Dict[str, Any], mode: str) -> str:
    feedback = event.get("feedback")
    if isinstance(feedback, dict) and feedback.get("summary"):
        return feedback.get("summary") or ""

    title = instance.get("title")
    if title:
        return title

    return {
        "code-block": "빈칸 채우기",
        "code-calc": "코드 계산",
        "code-error": "오류 찾기",
        "code-arrange": "코드 정렬",
        "auditor": "감사관 모드",
        "context-inference": "맥락 추론",
        "refactoring-choice": "최적의 선택",
        "code-blame": "범인 찾기",
        "diagnostic": "진단 문제",
        "practice": "맞춤 문제",
    }.get(mode, "학습 기록")


def user_history(
    service: Any,
    username: str,
    *,
    duration_seconds: Callable[[str | None, str | None], float | None],
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

    return sorted(enriched_events, key=lambda item: item.get("created_at", ""), reverse=True)


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

    durations: List[float] = []
    recent_window = history[:5]
    previous_window = history[5:10]
    recent_accuracy = accuracy_from_events(recent_window)
    previous_accuracy = accuracy_from_events(previous_window)

    accuracy_change = None
    if recent_accuracy is not None and previous_accuracy is not None:
        accuracy_change = round(recent_accuracy - previous_accuracy, 1)

    recent_history = history[:10]
    context_lines = []
    for idx, event in enumerate(recent_history, 1):
        problem_title = event.get("problem_title") or "제목 없음"
        is_correct = "정답" if event.get("correct") else "오답"
        score = event.get("score") or 0
        feedback_summary = (event.get("feedback") or {}).get("summary", "")

        duration = event.get("duration_seconds")
        if duration is None:
            instance = service._get_problem_instance(storage, event.get("problem_id"))
            duration = duration_seconds((instance or {}).get("created_at"), event.get("created_at"))

        if duration is not None:
            durations.append(duration)

        duration_label = f"{int(duration)}초" if duration is not None else "시간 미기록"
        context_lines.append(
            f"{idx}. [{is_correct}] {problem_title} (점수: {score})\n"
            f"   피드백 요약: {feedback_summary}\n"
            f"   소요시간: {duration_label}"
        )

    history_context = "\n".join(context_lines) if context_lines else "최근 학습 기록이 없습니다."
    ai_report = service.ai_client.generate_report(history_context)

    languages: Dict[str, int] = {}
    for event in history:
        lang = event.get("language")
        if lang:
            languages[lang] = languages.get(lang, 0) + 1

    preferred_languages = [
        {"language": LANGUAGES.get(lang, {"title": lang}).get("title"), "count": count}
        for lang, count in sorted(languages.items(), key=lambda item: item[1], reverse=True)
    ]

    avg_duration = round(sum(durations) / len(durations), 2) if durations else None

    return {
        "username": username,
        "attempts": attempts,
        "correctAnswers": correct_count,
        "accuracy": accuracy,
        "averageDurationSeconds": avg_duration,
        "trend": {
            "recentAttempts": len(recent_window),
            "recentAccuracy": recent_accuracy,
            "previousAttempts": len(previous_window),
            "previousAccuracy": previous_accuracy,
            "accuracyChange": accuracy_change,
            "summary": trend_summary(recent_accuracy, previous_accuracy),
        },
        "recent_history": history[:5],
        "common_strengths": [(s, 1) for s in ai_report.get("strengths", [])],
        "common_improvements": [(i, 1) for i in ai_report.get("improvements", [])],
        "preferred_languages": preferred_languages[:5],
        "recommendations": ai_report.get("recommendations", []),
        "ai_summary": ai_report.get("summary"),
    }

