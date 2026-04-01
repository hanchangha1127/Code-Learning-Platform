from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
import math
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Report, ReportType

_WHITESPACE_RE = re.compile(r"\s+")
_LATEST_REPORT_BATCH_SIZE = 25
_SEOUL_TZ = timezone(timedelta(hours=9), name="KST")

_MODE_LABELS: dict[str, str] = {
    "analysis": "코드 분석",
    "diagnostic": "진단",
    "practice": "맞춤 문제",
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
}

_MODE_LABEL_ALIASES: dict[str, str] = {
    **_MODE_LABELS,
    "코드 설명": "코드 분석",
    "빈칸 채우기": "코드 블록",
    "출력 예측": "코드 계산",
    "코드 정렬": "코드 배치",
    "감사관": "감사관 모드",
    "리팩토링 선택": "최적의 선택",
    "최적안 선택": "최적의 선택",
    "코드 블레임": "범인 찾기",
    "멀티 파일 분석": "다중 파일 분석",
    "풀스택 분석": "풀스택 코드 분석",
    "진단 문제": "진단",
    "연습": "맞춤 문제",
}

_OUTCOME_LABELS: dict[str, str] = {
    "passed": "정답",
    "correct": "정답",
    "success": "정답",
    "failed": "오답",
    "incorrect": "오답",
    "wrong": "오답",
    "error": "에러",
    "pending": "대기",
    "processing": "처리 중",
}

_DIFFICULTY_LABELS: dict[str, str] = {
    "beginner": "초급",
    "easy": "초급",
    "intermediate": "중급",
    "medium": "중급",
    "advanced": "고급",
    "hard": "고급",
}

_LANGUAGE_LABELS: dict[str, str] = {
    "python": "파이썬",
    "javascript": "자바스크립트",
    "typescript": "타입스크립트",
    "java": "자바",
    "c": "C",
    "c++": "C++",
    "cpp": "C++",
    "csharp": "C#",
    "cs": "C#",
    "go": "Go",
    "rust": "Rust",
    "php": "PHP",
    "golfscript": "골프스크립트",
    "gs": "골프스크립트",
}

_WRONG_TYPE_LABELS: dict[str, str] = {
    "syntax_error": "문법 오류",
    "logic_error": "로직 오류",
    "runtime_error": "실행 오류",
    "timeout_error": "시간 초과",
    "analysis_error": "분석 오류",
    "unknown_error": "기본기 보강",
    "input_validation": "입력 검증",
    "authorization_bypass": "권한 검증 누락",
    "injection_risk": "주입 위험",
    "state_consistency": "상태 일관성",
    "boundary": "경계값 처리",
    "boundary_error": "경계값 오류",
}


def _normalize_text(value: Any, *, limit: int = 220) -> str:
    text = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 0)].rstrip()}…"


def _normalize_list(value: Any, *, limit: int = 3, item_limit: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []

    rows: list[str] = []
    for item in value:
        text = _normalize_text(item, limit=item_limit)
        if not text or text in rows:
            continue
        rows.append(text)
        if len(rows) >= limit:
            break
    return rows


def _normalize_evidence_items(value: Any, *, limit: int = 3, item_limit: int = 120) -> list[str]:
    if isinstance(value, Mapping):
        rows: list[str] = []
        for key, item in value.items():
            text = _normalize_text(item, limit=item_limit)
            if not text:
                continue
            rows.append(_normalize_text(f"{key}: {text}", limit=item_limit))
            if len(rows) >= limit:
                break
        return rows
    if isinstance(value, list):
        return _normalize_list(value, limit=limit, item_limit=item_limit)

    text = _normalize_text(value, limit=item_limit)
    return [text] if text else []


def _display_mode_label(value: Any) -> str:
    text = _normalize_text(value, limit=80)
    if not text:
        return ""
    return _MODE_LABEL_ALIASES.get(text) or _MODE_LABEL_ALIASES.get(text.lower()) or text


def _display_outcome_label(value: Any) -> str:
    text = _normalize_text(value, limit=40)
    if not text:
        return ""
    return _OUTCOME_LABELS.get(text.lower(), text)


def _display_difficulty_label(value: Any) -> str:
    text = _normalize_text(value, limit=40)
    if not text:
        return ""
    return _DIFFICULTY_LABELS.get(text.lower(), text)


def _display_language_label(value: Any) -> str:
    text = _normalize_text(value, limit=40)
    if not text:
        return ""
    return _LANGUAGE_LABELS.get(text.lower(), text)


def _display_wrong_type_label(value: Any) -> str:
    text = _normalize_text(value, limit=60)
    if not text:
        return ""
    return _WRONG_TYPE_LABELS.get(text.lower(), text)


def _extract_solution_plan(report: Report) -> dict[str, Any]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    solution_plan = stats.get("solutionPlan")
    if isinstance(solution_plan, dict):
        return solution_plan
    return {}


def _extract_metric_snapshot(report: Report) -> dict[str, Any]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    metric_snapshot = stats.get("metricSnapshot")
    if isinstance(metric_snapshot, dict):
        return metric_snapshot
    return {}


def _extract_detail_records(report: Report) -> list[dict[str, Any]]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    detail_records = stats.get("detailRecords")
    if not isinstance(detail_records, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in detail_records:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _format_metric_number(value: Any, *, suffix: str = "") -> str:
    if value is None or value == "":
        return "-"
    return f"{value}{suffix}"


def _to_seoul_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_SEOUL_TZ)


def serialize_report_created_at(value: datetime | None) -> str | None:
    localized = _to_seoul_datetime(value)
    if localized is None:
        return None
    return localized.isoformat(timespec="seconds")


def _short_trend(value: Any) -> str:
    text = _normalize_text(value, limit=80).lower()
    if not text:
        return "데이터 보강 필요"
    if "개선" in text or "improv" in text:
        return "개선"
    if "하락" in text or "감소" in text or "declin" in text:
        return "하락"
    if "안정" in text or "stable" in text:
        return "안정"
    if "부족" in text:
        return "데이터 부족"
    return _normalize_text(value, limit=32)


def _build_summary_text(
    *,
    metric_snapshot: Mapping[str, Any],
    solution_summary: str,
) -> str:
    attempts = metric_snapshot.get("attempts")
    accuracy = metric_snapshot.get("accuracy")
    avg_score = metric_snapshot.get("avgScore")
    trend = _short_trend(metric_snapshot.get("trend"))

    summary_parts: list[str] = []
    metric_bits: list[str] = []

    if attempts not in (None, ""):
        metric_bits.append(f"최근 {attempts}회 학습")
    if accuracy not in (None, ""):
        metric_bits.append(f"정확도 {_format_metric_number(accuracy, suffix='%')}")
    if avg_score not in (None, ""):
        metric_bits.append(f"평균 점수 {_format_metric_number(avg_score)}")

    if metric_bits:
        summary_parts.append(", ".join(metric_bits) + " 기준입니다.")
    if trend and trend not in ("-", ""):
        summary_parts.append(f"현재 추세는 {trend}입니다.")
    if solution_summary:
        summary_parts.append(solution_summary)

    return _normalize_text(" ".join(summary_parts), limit=260) or "최근 학습 기록을 바탕으로 다음 학습 우선순위를 정리했습니다."


def _build_next_steps(
    *,
    focus_actions: list[str],
    learning_habits: list[str],
    checkpoints: list[str],
) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()

    for item in [*focus_actions, *learning_habits, *checkpoints]:
        normalized = _normalize_text(item, limit=120)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(normalized)
        if len(rows) >= 3:
            break

    return rows


def _build_study_guide_text(
    *,
    metric_snapshot: Mapping[str, Any],
    focus_actions: list[str],
    learning_habits: list[str],
    checkpoints: list[str],
) -> str:
    trend = _short_trend(metric_snapshot.get("trend"))
    accuracy = metric_snapshot.get("accuracy")

    opener = "다음 학습은 범위를 넓히기보다 지금 흔들리는 포인트를 짧게 반복하는 편이 좋습니다."
    try:
        accuracy_value = float(accuracy) if accuracy not in (None, "") else None
    except (TypeError, ValueError):
        accuracy_value = None

    if trend == "하락":
        opener = "지금은 새 유형을 늘리기보다 최근 오답 유형을 다시 묶어 복기하는 편이 좋습니다."
    elif trend == "개선":
        opener = "지금 흐름이 좋아서 현재 방식은 유지하되 검증 루틴을 더해 안정화하는 편이 좋습니다."
    elif accuracy_value is not None and accuracy_value < 60:
        opener = "정확도가 아직 낮아서 문제 수를 늘리기보다 한 문제당 복기 밀도를 높이는 편이 좋습니다."

    sentences = [opener]
    if focus_actions:
        sentences.append(f"우선순위는 {', '.join(focus_actions[:2])} 순서로 두세요.")
    if learning_habits:
        sentences.append(f"학습 루틴은 {', '.join(learning_habits[:2])} 정도로 가볍게 고정하면 좋습니다.")
    if checkpoints:
        sentences.append(f"다음 확인 기준은 {', '.join(checkpoints[:2])} 입니다.")

    return _normalize_text(" ".join(sentences), limit=300) or opener


def _build_detail_record_header(record: Mapping[str, Any], index: int) -> str:
    title = (
        _normalize_text(record.get("title"), limit=60)
        or _display_mode_label(record.get("mode"))
        or _display_mode_label(record.get("modeLabel"))
        or "문제 풀이 기록"
    )
    return f"사례 {index}: {title}"


def _build_detail_record_lines(record: Mapping[str, Any]) -> list[str]:
    question_context = record.get("questionContext") if isinstance(record.get("questionContext"), Mapping) else {}
    evaluation = record.get("evaluation") if isinstance(record.get("evaluation"), Mapping) else {}

    summary_bits = [
        _display_outcome_label(record.get("result")),
        f"점수 {_format_metric_number(record.get('score'))}",
        f"시간 {_format_metric_number(record.get('durationSeconds'), suffix='초')}",
        _display_difficulty_label(record.get("difficulty")),
        _display_language_label(record.get("language")),
        _display_wrong_type_label(evaluation.get("wrongType") or record.get("wrongType")),
    ]
    lines = [
        _normalize_text(" · ".join(bit for bit in summary_bits if bit), limit=220),
    ]

    question_bits: list[str] = []
    for value in (
        question_context.get("prompt"),
        question_context.get("scenario"),
        question_context.get("codeOrContext"),
        question_context.get("errorLog"),
    ):
        text = _normalize_text(value, limit=120)
        if text:
            question_bits.append(text)
    option_bits = _normalize_evidence_items(question_context.get("options"), limit=3, item_limit=80)
    commit_bits = _normalize_evidence_items(question_context.get("commits"), limit=3, item_limit=80)
    if question_bits or option_bits or commit_bits:
        lines.append(_normalize_text(f"문제 맥락: {' / '.join([*question_bits, *option_bits, *commit_bits])}", limit=300))

    learner_response = _normalize_text(record.get("learnerResponse"), limit=180)
    expected_answer = _normalize_text(record.get("expectedAnswer"), limit=180)
    if learner_response:
        lines.append(f"작성 답안: {learner_response}")
    if expected_answer:
        lines.append(f"기대 답안: {expected_answer}")

    evaluation_bits: list[str] = []
    for value in (
        evaluation.get("feedbackSummary"),
        evaluation.get("comparison"),
        evaluation.get("referenceExplanation"),
    ):
        text = _normalize_text(value, limit=120)
        if text:
            evaluation_bits.append(text)
    if evaluation_bits:
        lines.append(_normalize_text(f"평가: {' / '.join(evaluation_bits)}", limit=280))

    for label, value in (
        ("강점", evaluation.get("strengths")),
        ("보완", evaluation.get("improvements")),
        ("놓친 포인트", evaluation.get("missedPoints")),
        ("맞춘 포인트", evaluation.get("matchedPoints")),
        ("오답 유형 분포", evaluation.get("wrongTypeCounts")),
        ("선택지 검토", evaluation.get("optionReviews")),
        ("커밋 검토", evaluation.get("commitReviews")),
    ):
        items = _normalize_evidence_items(value, limit=3, item_limit=110)
        if items:
            lines.append(f"{label}: {', '.join(items)}")

    return [line for line in lines if line]


def build_report_brief(
    *,
    solution_plan: Mapping[str, Any] | None,
    metric_snapshot: Mapping[str, Any] | None,
    fallback_title: str = "학습 리포트",
    fallback_summary: str = "",
) -> dict[str, Any]:
    plan = solution_plan if isinstance(solution_plan, Mapping) else {}
    metrics = metric_snapshot if isinstance(metric_snapshot, Mapping) else {}

    title = (
        _normalize_text(plan.get("goal"), limit=90)
        or _normalize_text(fallback_title, limit=90)
        or "학습 리포트"
    )
    solution_summary = (
        _normalize_text(plan.get("solutionSummary"), limit=140)
        or _normalize_text(fallback_summary, limit=140)
    )

    focus_actions = _normalize_list(
        plan.get("priorityActions") or plan.get("recommendations"),
        limit=3,
        item_limit=120,
    )
    learning_habits = _normalize_list(
        plan.get("dailyHabits") or plan.get("focusTopics"),
        limit=3,
        item_limit=120,
    )
    checkpoints = _normalize_list(
        plan.get("checkpoints") or plan.get("metricsToTrack"),
        limit=3,
        item_limit=120,
    )
    next_steps = _build_next_steps(
        focus_actions=focus_actions,
        learning_habits=learning_habits,
        checkpoints=checkpoints,
    )

    headline_source = focus_actions[0] if focus_actions else solution_summary
    headline = _normalize_text(headline_source, limit=100) or "이번 주 학습 우선순위를 정리했습니다."
    summary = _build_summary_text(metric_snapshot=metrics, solution_summary=solution_summary)
    study_guide = _build_study_guide_text(
        metric_snapshot=metrics,
        focus_actions=focus_actions,
        learning_habits=learning_habits,
        checkpoints=checkpoints,
    )

    return {
        "title": title,
        "headline": headline,
        "summary": summary,
        "studyGuide": study_guide,
        "metrics": [
            {
                "label": "시도 수",
                "value": _format_metric_number(metrics.get("attempts"), suffix="회"),
            },
            {
                "label": "정확도",
                "value": _format_metric_number(metrics.get("accuracy"), suffix="%"),
            },
            {
                "label": "평균 점수",
                "value": _format_metric_number(metrics.get("avgScore")),
            },
            {
                "label": "추세",
                "value": _short_trend(metrics.get("trend")),
            },
        ],
        "focusActions": focus_actions,
        "learningHabits": learning_habits,
        "checkpoints": checkpoints,
        "nextSteps": next_steps,
    }


def build_report_brief_from_report(report: Report) -> dict[str, Any]:
    stats = report.stats if isinstance(report.stats, dict) else {}
    cached = stats.get("reportBrief")
    generated = build_report_brief(
        solution_plan=_extract_solution_plan(report),
        metric_snapshot=_extract_metric_snapshot(report),
        fallback_title=report.title,
        fallback_summary=report.summary,
    )
    if isinstance(cached, dict):
        return {**generated, **cached}
    return generated


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _build_wrong_type_rows(metric_snapshot: Mapping[str, Any]) -> list[tuple[str, float]]:
    raw_items = metric_snapshot.get("topWrongTypes")
    if not isinstance(raw_items, list):
        raw_items = metric_snapshot.get("repeatedWrongTypes")

    rows: list[tuple[str, float]] = []
    for item in raw_items or []:
        if not isinstance(item, Mapping):
            continue
        label = _normalize_text(item.get("type") or item.get("label"), limit=24)
        count = _coerce_float(item.get("count"))
        if not label or count is None or count <= 0:
            continue
        rows.append((label, count))
        if len(rows) >= 4:
            break
    return rows


def _extract_chart_window(metric_snapshot: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = metric_snapshot.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _build_chart_rows(raw_items: Any) -> list[tuple[str, float]]:
    if not isinstance(raw_items, list):
        return []

    rows: list[tuple[str, float]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        label = _normalize_text(item.get("type") or item.get("label"), limit=24)
        count = _coerce_float(item.get("count"))
        if not label or count is None or count <= 0:
            continue
        rows.append((label, count))
        if len(rows) >= 4:
            break
    return rows


def _has_milestone_report_contract(report: Report) -> bool:
    metric_snapshot = _extract_metric_snapshot(report)
    if not isinstance(metric_snapshot, Mapping):
        return False
    attempts = metric_snapshot.get("attempts")
    trend = metric_snapshot.get("trend")
    if not isinstance(attempts, int):
        return False
    if not isinstance(trend, str) or not trend.strip():
        return False
    return True


def _is_metadata_milestone_candidate(report: Report | None) -> bool:
    if report is None:
        return False
    stats = report.stats if isinstance(report.stats, dict) else {}
    source = str(stats.get("source") or "").strip().lower()
    return source != "platform"


def _is_latest_milestone_candidate(report: Report | None) -> bool:
    return _is_metadata_milestone_candidate(report) and report is not None and _has_milestone_report_contract(report)


def _select_latest_milestone_report(reports: list[Report], *, require_detail_contract: bool = False) -> Report | None:
    predicate = _is_latest_milestone_candidate if require_detail_contract else _is_metadata_milestone_candidate
    for report in reports:
        if predicate(report):
            return report
    return None


def _load_latest_milestone_report(
    db: Session,
    user_id: int,
    *,
    require_detail_contract: bool = False,
) -> Report | None:
    query = (
        db.query(Report)
        .filter(Report.user_id == user_id, Report.report_type == ReportType.milestone)
        .order_by(Report.created_at.desc(), Report.id.desc())
    )
    offset = 0
    while True:
        reports = query.limit(_LATEST_REPORT_BATCH_SIZE).offset(offset).all()
        if not reports:
            return None
        candidate = _select_latest_milestone_report(reports, require_detail_contract=require_detail_contract)
        if candidate is not None:
            return candidate
        if len(reports) < _LATEST_REPORT_BATCH_SIZE:
            return None
        offset += _LATEST_REPORT_BATCH_SIZE


def get_latest_report_detail(db: Session, user_id: int) -> dict[str, Any] | None:
    report = _load_latest_milestone_report(db, user_id, require_detail_contract=True)
    if report is None:
        return None

    solution_plan = _extract_solution_plan(report)
    metric_snapshot = _extract_metric_snapshot(report)
    brief = build_report_brief_from_report(report)
    goal = _normalize_text(solution_plan.get("goal"), limit=200) or _normalize_text(report.title, limit=200)
    summary = _normalize_text(solution_plan.get("solutionSummary"), limit=400) or _normalize_text(report.summary, limit=400)
    priority_actions = _normalize_list(
        solution_plan.get("priorityActions") or report.recommendations,
        limit=6,
        item_limit=220,
    )
    phase_plan = _normalize_list(solution_plan.get("phasePlan"), limit=6, item_limit=220)
    daily_habits = _normalize_list(solution_plan.get("dailyHabits"), limit=6, item_limit=220)
    focus_topics = _normalize_list(solution_plan.get("focusTopics"), limit=6, item_limit=220)
    metrics_to_track = _normalize_list(solution_plan.get("metricsToTrack"), limit=6, item_limit=220)
    checkpoints = _normalize_list(solution_plan.get("checkpoints"), limit=6, item_limit=220)
    risk_mitigation = _normalize_list(solution_plan.get("riskMitigation"), limit=6, item_limit=220)

    return {
        "reportId": int(report.id),
        "createdAt": serialize_report_created_at(report.created_at),
        "goal": goal,
        "solutionSummary": summary,
        "priorityActions": priority_actions,
        "phasePlan": phase_plan,
        "dailyHabits": daily_habits,
        "focusTopics": focus_topics,
        "metricsToTrack": metrics_to_track,
        "checkpoints": checkpoints,
        "riskMitigation": risk_mitigation,
        "metricSnapshot": metric_snapshot,
        "reportBrief": brief,
        "pdfDownloadUrl": build_report_pdf_download_url(report.id),
    }


def build_report_pdf_download_url(report_id: int | None) -> str | None:
    if report_id is None:
        return None
    return f"/platform/reports/{int(report_id)}/pdf"


def _format_created_at(value: datetime | None) -> str:
    localized = _to_seoul_datetime(value)
    if localized is None:
        return "-"
    return localized.strftime("%Y-%m-%d %H:%M KST")


def _coerce_chart_number(value: Any, *, min_value: float | None = None, max_value: float | None = None) -> float | None:
    if isinstance(value, bool):
        return None
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if min_value is not None:
        number = max(number, min_value)
    if max_value is not None:
        number = min(number, max_value)
    return number


def _round_chart_max(value: float, *, minimum: float = 5.0) -> float:
    target = max(float(value or 0), minimum)
    if target <= 10:
        return math.ceil(target)
    if target <= 25:
        return math.ceil(target / 5.0) * 5.0
    if target <= 100:
        return math.ceil(target / 10.0) * 10.0
    return math.ceil(target / 25.0) * 25.0


def _build_feedback_chart_specs(
    metric_snapshot: Mapping[str, Any] | None,
    detail_records: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    metrics = metric_snapshot if isinstance(metric_snapshot, Mapping) else {}
    records = detail_records if isinstance(detail_records, list) else []
    specs: list[dict[str, Any]] = []

    outcome_window = _extract_chart_window(metrics, "chartOutcomeWindow")
    outcome_counts = outcome_window.get("counts") if isinstance(outcome_window.get("counts"), Mapping) else metrics
    outcome_scope = _normalize_text(outcome_window.get("label"), limit=60)
    outcome_items: list[tuple[str, float]] = []
    for label, key in (
        ("정답", "passed"),
        ("오답", "failed"),
        ("에러", "error"),
        ("대기", "pending"),
        ("처리 중", "processing"),
    ):
        value = _coerce_chart_number(outcome_counts.get(key), min_value=0)
        if value is None or value <= 0:
            continue
        outcome_items.append((label, value))
    if outcome_items:
        dominant_label, dominant_value = max(outcome_items, key=lambda item: item[1])
        total_outcomes = sum(value for _, value in outcome_items)
        scope_prefix = f"{outcome_scope} 기준. " if outcome_scope else ""
        specs.append(
            {
                "kind": "bar",
                "title": "최근 풀이 결과 분포",
                "caption": _normalize_text(
                    f"{scope_prefix}최근 결과 중 {dominant_label} 비중이 가장 큽니다. "
                    f"({int(round(dominant_value))} / {int(round(total_outcomes))})",
                    limit=180,
                ),
                "labels": [label for label, _ in outcome_items],
                "values": [value for _, value in outcome_items],
                "valueMax": _round_chart_max(max(value for _, value in outcome_items)),
                "color": "#2563eb",
            }
        )

    score_trend_window = _extract_chart_window(metrics, "chartScoreTrend")
    score_records = score_trend_window.get("records") if isinstance(score_trend_window.get("records"), list) else records
    score_scope = _normalize_text(score_trend_window.get("label"), limit=60)
    score_points: list[tuple[str, float]] = []
    attempt_context: list[str] = []
    recent_records = list(score_records[:10])
    recent_records.reverse()
    for record in recent_records:
        if not isinstance(record, Mapping):
            continue
        score = _coerce_chart_number(record.get("score"), min_value=0, max_value=100)
        if score is None:
            result = _normalize_text(record.get("result"), limit=32).lower()
            if result in {"correct", "passed", "success"}:
                score = 100.0
            elif result in {"wrong", "failed", "error"}:
                score = 0.0
        if score is None:
            continue
        attempt_label = f"{len(score_points) + 1}회"
        mode_label = (
            _display_mode_label(record.get("mode"))
            or _display_mode_label(record.get("modeLabel"))
            or _normalize_text(record.get("title"), limit=16)
            or attempt_label
        )
        score_points.append((attempt_label, score))
        attempt_context.append(_normalize_text(f"{attempt_label} {mode_label}", limit=40))
    if len(score_points) >= 2:
        first_score = score_points[0][1]
        last_score = score_points[-1][1]
        if last_score >= first_score + 5:
            trend_note = "최근 시도 점수가 올라가는 흐름입니다."
        elif last_score <= first_score - 5:
            trend_note = "최근 시도 점수가 내려가서 복기 강도를 높일 필요가 있습니다."
        else:
            trend_note = "점수 흐름이 비슷해서 같은 실수를 줄이는 것이 다음 상승 포인트입니다."
        specs.append(
            {
                "kind": "line",
                "title": "최근 점수 추이",
                "caption": _normalize_text(
                    f"{f'{score_scope} 기준. ' if score_scope else ''}{trend_note} 시도 순서: {', '.join(attempt_context)}",
                    limit=180,
                ),
                "labels": [label for label, _ in score_points],
                "values": [value for _, value in score_points],
                "valueMin": max(math.floor(min(value for _, value in score_points) / 10.0) * 10.0 - 10.0, 0.0),
                "valueMax": min(
                    max(math.ceil(max(value for _, value in score_points) / 10.0) * 10.0 + 10.0, 40.0),
                    100.0,
                ),
                "color": "#0f766e",
            }
        )

    wrong_type_window = _extract_chart_window(metrics, "chartWrongTypes")
    wrong_type_scope = _normalize_text(wrong_type_window.get("label"), limit=60)
    wrong_type_rows = [
        (_normalize_text(_display_wrong_type_label(label), limit=16), count)
        for label, count in (_build_chart_rows(wrong_type_window.get("rows")) or _build_wrong_type_rows(metrics))
        if _display_wrong_type_label(label) and count > 0
    ]
    if wrong_type_rows:
        top_wrong_label, top_wrong_count = max(wrong_type_rows, key=lambda item: item[1])
        specs.append(
            {
                "kind": "bar",
                "title": "반복 오답 유형",
                "caption": _normalize_text(
                    f"{f'{wrong_type_scope} 기준. ' if wrong_type_scope else ''}가장 자주 반복된 오답 유형은 {top_wrong_label}이며 "
                    f"총 {int(round(top_wrong_count))}회 나타났습니다.",
                    limit=180,
                ),
                "labels": [label for label, _ in wrong_type_rows],
                "values": [value for _, value in wrong_type_rows],
                "valueMax": _round_chart_max(max(value for _, value in wrong_type_rows)),
                "color": "#dc2626",
            }
        )

    return specs


def _load_reportlab_components() -> dict[str, Any]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.shapes import Drawing, Rect, String
        from reportlab.graphics.widgets.markers import makeMarker
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError("report_pdf_generation_unavailable") from exc

    return {
        "colors": colors,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "mm": mm,
        "Drawing": Drawing,
        "Rect": Rect,
        "String": String,
        "VerticalBarChart": VerticalBarChart,
        "HorizontalLineChart": HorizontalLineChart,
        "makeMarker": makeMarker,
        "pdfmetrics": pdfmetrics,
        "UnicodeCIDFont": UnicodeCIDFont,
        "PageBreak": PageBreak,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def _ensure_pdf_font(components: Mapping[str, Any]) -> str:
    pdfmetrics = components["pdfmetrics"]
    unicode_cid_font = components["UnicodeCIDFont"]
    candidate_fonts = ("HYGothic-Medium", "HYSMyeongJo-Medium")

    for font_name in candidate_fonts:
        try:
            pdfmetrics.getFont(font_name)
        except KeyError:
            try:
                pdfmetrics.registerFont(unicode_cid_font(font_name))
            except Exception:
                continue
        return font_name

    return "Helvetica"


def _append_feedback_charts(
    *,
    story: list[Any],
    components: Mapping[str, Any],
    font_name: str,
    base_style: Any,
    section_style: Any,
    metric_snapshot: Mapping[str, Any] | None,
    detail_records: list[dict[str, Any]] | None,
) -> bool:
    chart_specs = _build_feedback_chart_specs(metric_snapshot, detail_records)
    if not chart_specs:
        return False

    colors = components["colors"]
    mm = components["mm"]
    drawing_cls = components["Drawing"]
    rect_cls = components["Rect"]
    string_cls = components["String"]
    vertical_bar_chart = components["VerticalBarChart"]
    horizontal_line_chart = components["HorizontalLineChart"]
    make_marker = components["makeMarker"]
    paragraph = components["Paragraph"]
    spacer = components["Spacer"]

    chart_width = 168 * mm
    chart_height = 48 * mm
    inner_x = 12 * mm
    inner_y = 10 * mm
    inner_width = 142 * mm
    inner_height = 24 * mm

    for spec in chart_specs:
        drawing = drawing_cls(chart_width, chart_height)
        drawing.add(
            rect_cls(
                0,
                0,
                chart_width,
                chart_height,
                strokeColor=colors.HexColor("#dbe4ee"),
                fillColor=colors.HexColor("#f8fafc"),
            )
        )
        drawing.add(
            string_cls(
                8 * mm,
                chart_height - (6 * mm),
                _normalize_text(spec.get("title"), limit=40),
                fontName=font_name,
                fontSize=10,
                fillColor=colors.HexColor("#0f172a"),
            )
        )

        labels = [_normalize_text(label, limit=14) or "-" for label in spec.get("labels") or []]
        values = [float(value) for value in spec.get("values") or []]
        if not labels or not values:
            continue

        if spec.get("kind") == "line":
            chart = horizontal_line_chart()
            chart.x = inner_x
            chart.y = inner_y
            chart.width = inner_width
            chart.height = inner_height
            chart.data = [tuple(values)]
            chart.joinedLines = 1
            chart.lines[0].strokeColor = colors.HexColor(spec.get("color") or "#0f766e")
            chart.lines[0].strokeWidth = 2
            chart.lines[0].symbol = make_marker("FilledCircle")
            chart.lines[0].symbol.fillColor = colors.HexColor(spec.get("color") or "#0f766e")
            chart.categoryAxis.categoryNames = labels
            chart.categoryAxis.labels.fontName = font_name
            chart.categoryAxis.labels.fontSize = 7
            chart.categoryAxis.labels.fillColor = colors.HexColor("#475569")
            chart.valueAxis.labels.fontName = font_name
            chart.valueAxis.labels.fontSize = 6.5
            chart.valueAxis.labels.fillColor = colors.HexColor("#475569")
            chart.valueAxis.visibleGrid = 1
            chart.valueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
            chart.valueAxis.valueMin = float(spec.get("valueMin") or 0.0)
            chart.valueAxis.valueMax = float(spec.get("valueMax") or 100.0)
            span = max(chart.valueAxis.valueMax - chart.valueAxis.valueMin, 10.0)
            chart.valueAxis.valueStep = max(math.ceil(span / 4.0 / 5.0) * 5.0, 5.0)
        else:
            chart = vertical_bar_chart()
            chart.x = inner_x
            chart.y = inner_y
            chart.width = inner_width
            chart.height = inner_height
            chart.data = [tuple(values)]
            chart.categoryAxis.categoryNames = labels
            chart.categoryAxis.labels.fontName = font_name
            chart.categoryAxis.labels.fontSize = 7
            chart.categoryAxis.labels.fillColor = colors.HexColor("#475569")
            chart.categoryAxis.labels.angle = 15
            chart.categoryAxis.labels.boxAnchor = "n"
            chart.valueAxis.labels.fontName = font_name
            chart.valueAxis.labels.fontSize = 6.5
            chart.valueAxis.labels.fillColor = colors.HexColor("#475569")
            chart.valueAxis.visibleGrid = 1
            chart.valueAxis.gridStrokeColor = colors.HexColor("#e2e8f0")
            chart.valueAxis.valueMin = 0
            chart.valueAxis.valueMax = float(spec.get("valueMax") or _round_chart_max(max(values)))
            chart.valueAxis.valueStep = max(math.ceil(chart.valueAxis.valueMax / 4.0), 1.0)
            chart.barLabelFormat = "%0.0f"
            chart.barLabels.nudge = 6
            chart.barLabels.fontName = font_name
            chart.barLabels.fontSize = 6.5
            chart.barLabels.fillColor = colors.HexColor("#334155")
            chart.bars[0].fillColor = colors.HexColor(spec.get("color") or "#2563eb")
            chart.bars[0].strokeColor = colors.HexColor(spec.get("color") or "#2563eb")

        drawing.add(chart)
        story.append(drawing)
        caption = _normalize_text(spec.get("caption"), limit=140)
        if caption:
            story.append(paragraph(escape(caption), base_style))
        story.append(spacer(1, 2 * mm))
    return True


def _build_compact_report_pdf_bytes(report: Report) -> bytes:
    components = _load_reportlab_components()
    colors = components["colors"]
    paragraph_style = components["ParagraphStyle"]
    get_sample_style_sheet = components["getSampleStyleSheet"]
    page_break = components["PageBreak"]
    simple_doc_template = components["SimpleDocTemplate"]
    spacer = components["Spacer"]
    paragraph = components["Paragraph"]
    table = components["Table"]
    table_style = components["TableStyle"]
    a4 = components["A4"]
    mm = components["mm"]

    font_name = _ensure_pdf_font(components)
    brief = build_report_brief_from_report(report)
    solution_plan = _extract_solution_plan(report)
    metric_snapshot = _extract_metric_snapshot(report)
    detail_records = _extract_detail_records(report)
    created_at = _format_created_at(report.created_at)
    styles = get_sample_style_sheet()

    base_style = paragraph_style(
        "ReportBaseCompact",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=5,
    )
    title_style = paragraph_style(
        "ReportTitleCompact",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=19,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    meta_style = paragraph_style(
        "ReportMetaCompact",
        parent=base_style,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=10,
    )
    section_style = paragraph_style(
        "ReportSectionCompact",
        parent=base_style,
        fontName=font_name,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=6,
        spaceAfter=5,
    )
    bullet_style = paragraph_style(
        "ReportBulletCompact",
        parent=base_style,
        leftIndent=10,
        bulletIndent=0,
        spaceAfter=3,
    )
    metric_card_style = paragraph_style(
        "ReportMetricCardCompact",
        parent=base_style,
        fontName=font_name,
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=0,
    )
    table_header_style = paragraph_style(
        "ReportTableHeaderCompact",
        parent=base_style,
        fontName=font_name,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=0,
    )
    table_cell_style = paragraph_style(
        "ReportTableCellCompact",
        parent=base_style,
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1f2937"),
        wordWrap="CJK",
        splitLongWords=1,
        spaceAfter=0,
    )

    title_text = "\ud559\uc2b5 \ub9ac\ud3ec\ud2b8"
    study_guide = _normalize_text(
        brief.get("studyGuide") or solution_plan.get("solutionSummary"),
        limit=320,
    ) or "\ucd5c\uadfc \ud559\uc2b5 \ud750\ub984\uc744 \uae30\uc900\uc73c\ub85c \ub2e4\uc74c \ud559\uc2b5 \uc9c0\uce68\uc744 \uc815\ub9ac\ud588\uc2b5\ub2c8\ub2e4."
    next_steps = _normalize_list(
        brief.get("nextSteps") or solution_plan.get("priorityActions") or report.recommendations,
        limit=3,
        item_limit=140,
    )
    focus_actions = _normalize_list(
        brief.get("focusActions") or solution_plan.get("focusTopics"),
        limit=3,
        item_limit=140,
    )
    learning_habits = _normalize_list(
        brief.get("learningHabits") or solution_plan.get("dailyHabits"),
        limit=3,
        item_limit=140,
    )
    checkpoints = _normalize_list(
        brief.get("checkpoints") or solution_plan.get("checkpoints") or solution_plan.get("metricsToTrack"),
        limit=3,
        item_limit=140,
    )
    metric_items = list(brief.get("metrics") or [])
    if not metric_items:
        metric_items = [
            {"label": "\ud480\uc774 \uc218", "value": _format_metric_number(metric_snapshot.get("attempts"), suffix="\ud68c")},
            {"label": "\uc815\ud655\ub3c4", "value": _format_metric_number(metric_snapshot.get("accuracy"), suffix="%")},
            {"label": "\ud3c9\uade0 \uc810\uc218", "value": _format_metric_number(metric_snapshot.get("avgScore"), suffix="\uc810")},
            {"label": "\ud750\ub984", "value": _normalize_text(metric_snapshot.get("trend"), limit=32) or "-"},
        ]
    metric_items = metric_items[:4]
    compact_records = detail_records[:3]

    story: list[Any] = [
        paragraph(escape(title_text), title_style),
        paragraph(
            escape(f"\ub9ac\ud3ec\ud2b8 ID {int(report.id)} | \uc0dd\uc131 \uc2dc\uac01 {created_at}"),
            meta_style,
        ),
    ]
    story.append(spacer(1, 4 * mm))

    metric_card_rows: list[list[Any]] = []
    pending_cells: list[Any] = []
    for item in metric_items:
        label = _normalize_text(item.get("label"), limit=24) or "-"
        value = _normalize_text(item.get("value"), limit=40) or "-"
        pending_cells.append(
            paragraph(
                f"<font size='8.5'>{escape(label)}</font><br/><font size='13'><b>{escape(value)}</b></font>",
                metric_card_style,
            )
        )
        if len(pending_cells) == 2:
            metric_card_rows.append(pending_cells)
            pending_cells = []
    if pending_cells:
        while len(pending_cells) < 2:
            pending_cells.append(paragraph("", metric_card_style))
        metric_card_rows.append(pending_cells)

    metrics_table = table(metric_card_rows, colWidths=[81 * mm, 81 * mm])
    metrics_table.setStyle(
        table_style(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    guide_table = table([[paragraph(escape(study_guide), base_style)]], colWidths=[162 * mm])
    guide_table.setStyle(
        table_style(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend(
        [
            paragraph("\ud559\uc2b5 \uac00\uc774\ub4dc", section_style),
            guide_table,
            spacer(1, 3 * mm),
        ]
    )

    for section_title, section_items, empty_text in (
        (
            "\uc2e4\ud589 \uc9c0\uc2dc",
            next_steps or focus_actions,
            "\ubc14\ub85c \uc2e4\ud589\ud560 \ud56d\ubaa9\uc740 \ub2e4\uc74c \ud480\uc774 \ub370\uc774\ud130\uc640 \ud568\uaed8 \ub2e4\uc2dc \uc81c\uc548\ud569\ub2c8\ub2e4.",
        ),
        (
            "\ud559\uc2b5 \ub8e8\ud2f4",
            learning_habits,
            "\ud480\uc774 \ub8e8\ud2f4\uc740 \ucd5c\uadfc \uae30\ub85d\uc744 \ub354 \uc313\uc740 \ub4a4 \uc81c\uc548\ud569\ub2c8\ub2e4.",
        ),
        (
            "\ub2e4\uc74c \uccb4\ud06c\ud3ec\uc778\ud2b8",
            checkpoints,
            "\ub2e4\uc74c \uccb4\ud06c\ud3ec\uc778\ud2b8\ub294 \ucd94\uac00 \ud480\uc774 \ub370\uc774\ud130\uac00 \uc313\uc774\uba74 \uc81c\uc2dc\ud569\ub2c8\ub2e4.",
        ),
    ):
        story.append(paragraph(section_title, section_style))
        if section_items:
            for item in section_items[:3]:
                story.append(paragraph(escape(item), bullet_style, bulletText="-"))
        else:
            story.append(paragraph(escape(empty_text), base_style))
        story.append(spacer(1, 2 * mm))

    story.extend(
        [
            page_break(),
            paragraph("\ud575\uc2ec \uc9c0\ud45c", section_style),
            metrics_table,
            spacer(1, 3 * mm),
            paragraph("\uc2dc\uac01 \ud53c\ub4dc\ubc31", section_style),
            paragraph(
                "\ucc28\ud2b8 3\uc885\uc73c\ub85c \ucd5c\uadfc \ud480\uc774 \ud750\ub984\uacfc \ubc18\ubcf5 \uc624\ub2f5 \ud328\ud134\uc744 \uc694\uc57d\ud588\uc2b5\ub2c8\ub2e4.",
                base_style,
            ),
            spacer(1, 2 * mm),
        ]
    )

    has_charts = _append_feedback_charts(
        story=story,
        components=components,
        font_name=font_name,
        base_style=base_style,
        section_style=section_style,
        metric_snapshot=metric_snapshot,
        detail_records=detail_records,
    )
    if not has_charts:
        story.append(
            paragraph(
                "\uc2dc\uac01 \ucc28\ud2b8\ub97c \uad6c\uc131\ud560 \uc218 \uc788\ub294 \ucd5c\uadfc \ub370\uc774\ud130\uac00 \ucda9\ubd84\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.",
                base_style,
            )
        )

    story.extend([page_break(), paragraph("\ucd5c\uadfc \ud480\uc774 \uc0ac\ub840", section_style)])
    if compact_records:
        detail_summary_rows = [
            [
                paragraph("\uc0ac\ub840", table_header_style),
                paragraph("\ud575\uc2ec \uc694\uc57d", table_header_style),
            ]
        ]
        for index, record in enumerate(compact_records, start=1):
            header = _build_detail_record_header(record, index)
            summary_line = _normalize_text(
                " | ".join(line for line in _build_detail_record_lines(record)[:2] if line),
                limit=180,
            )
            detail_summary_rows.append(
                [
                    paragraph(escape(header), table_cell_style),
                    paragraph(escape(summary_line or "-"), table_cell_style),
                ]
            )

        detail_summary_table = table(detail_summary_rows, colWidths=[36 * mm, 126 * mm], repeatRows=1)
        detail_summary_table.setStyle(
            table_style(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(detail_summary_table)
    else:
        story.append(paragraph("\ucd5c\uadfc \ud480\uc774 \uc0ac\ub840 \uc694\uc57d\uc740 \uc544\uc9c1 \uc5c6\uc2b5\ub2c8\ub2e4.", base_style))

    buffer = BytesIO()
    document = simple_doc_template(
        buffer,
        pagesize=a4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title_text,
        author="Code Learning Platform",
    )
    document.build(story)
    return buffer.getvalue()


def build_report_pdf_bytes(report: Report) -> bytes:
    return _build_compact_report_pdf_bytes(report)
    components = _load_reportlab_components()
    colors = components["colors"]
    paragraph_style = components["ParagraphStyle"]
    get_sample_style_sheet = components["getSampleStyleSheet"]
    simple_doc_template = components["SimpleDocTemplate"]
    spacer = components["Spacer"]
    paragraph = components["Paragraph"]
    table = components["Table"]
    table_style = components["TableStyle"]
    a4 = components["A4"]
    mm = components["mm"]

    font_name = _ensure_pdf_font(components)
    brief = build_report_brief_from_report(report)
    solution_plan = _extract_solution_plan(report)
    metric_snapshot = _extract_metric_snapshot(report)
    detail_records = _extract_detail_records(report)
    created_at = _format_created_at(report.created_at)
    styles = get_sample_style_sheet()

    base_style = paragraph_style(
        "ReportBase",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10.5,
        leading=16,
        textColor=colors.HexColor("#1f2937"),
        spaceAfter=6,
    )
    title_style = paragraph_style(
        "ReportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=26,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
    )
    meta_style = paragraph_style(
        "ReportMeta",
        parent=base_style,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=12,
    )
    section_style = paragraph_style(
        "ReportSection",
        parent=base_style,
        fontName=font_name,
        fontSize=12.5,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=6,
    )
    bullet_style = paragraph_style(
        "ReportBullet",
        parent=base_style,
        leftIndent=10,
        bulletIndent=0,
        spaceAfter=4,
    )
    table_header_style = paragraph_style(
        "ReportTableHeader",
        parent=base_style,
        fontName=font_name,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=0,
    )
    table_cell_style = paragraph_style(
        "ReportTableCell",
        parent=base_style,
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1f2937"),
        wordWrap="CJK",
        splitLongWords=1,
        spaceAfter=0,
    )

    story: list[Any] = [
        paragraph(escape(brief.get("title") or "학습 리포트"), title_style),
        paragraph(
            escape(f"리포트 ID {int(report.id)} · 생성 시각 {created_at}"),
            meta_style,
        ),
        paragraph(escape(brief.get("headline") or ""), section_style),
        paragraph(escape(brief.get("summary") or ""), base_style),
        spacer(1, 5 * mm),
    ]

    story.extend(
        [
            paragraph("학습 가이드", section_style),
            paragraph(escape(_normalize_text(brief.get("studyGuide"), limit=340) or "다음 학습 가이드를 준비 중입니다."), base_style),
            spacer(1, 3 * mm),
        ]
    )

    _append_feedback_charts(
        story=story,
        components=components,
        font_name=font_name,
        base_style=base_style,
        section_style=section_style,
        metric_snapshot=metric_snapshot,
        detail_records=detail_records,
    )

    metric_rows = [["지표", "값"]]
    for item in brief.get("metrics") or []:
        label = _normalize_text(item.get("label"), limit=24)
        value = _normalize_text(item.get("value"), limit=40)
        metric_rows.append([label or "-", value or "-"])

    metrics_table = table(metric_rows, colWidths=[42 * mm, 120 * mm])
    metrics_table.setStyle(
        table_style(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("LEADING", (0, 0), (-1, -1), 14),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dbeafe")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.extend(
        [
            paragraph("핵심 지표", section_style),
            metrics_table,
            spacer(1, 4 * mm),
        ]
    )

    plan_sections = (
        (
            "실행 우선순위",
            _normalize_list(solution_plan.get("priorityActions") or report.recommendations, limit=5, item_limit=220),
            "우선 실행 항목이 아직 정리되지 않았습니다.",
        ),
        (
            "단계 계획",
            _normalize_list(solution_plan.get("phasePlan"), limit=5, item_limit=220),
            "단계별 계획이 아직 정리되지 않았습니다.",
        ),
        (
            "하루 루틴",
            _normalize_list(solution_plan.get("dailyHabits"), limit=5, item_limit=220),
            "학습 루틴이 아직 정리되지 않았습니다.",
        ),
        (
            "집중 주제",
            _normalize_list(solution_plan.get("focusTopics"), limit=5, item_limit=220),
            "집중 주제가 아직 정리되지 않았습니다.",
        ),
        (
            "추적 지표",
            _normalize_list(solution_plan.get("metricsToTrack"), limit=5, item_limit=220),
            "추적할 지표가 아직 정리되지 않았습니다.",
        ),
        (
            "체크포인트",
            _normalize_list(solution_plan.get("checkpoints"), limit=5, item_limit=220),
            "확인할 체크포인트가 아직 없습니다.",
        ),
        (
            "리스크 대응",
            _normalize_list(solution_plan.get("riskMitigation"), limit=5, item_limit=220),
            "리스크 대응 전략이 아직 정리되지 않았습니다.",
        ),
    )

    story.append(paragraph("상세 학습 계획", section_style))
    for section_title, section_items, empty_text in plan_sections:
        story.append(paragraph(section_title, section_style))
        if section_items:
            for item in section_items:
                story.append(paragraph(escape(item), bullet_style, bulletText="•"))
        else:
            story.append(paragraph(escape(empty_text), base_style))

    story.append(spacer(1, 3 * mm))

    story.append(paragraph("최근 풀이 사례", section_style))
    if detail_records:
        detail_summary_rows = [
            [
                paragraph("사례", table_header_style),
                paragraph("핵심 요약", table_header_style),
            ]
        ]
        for index, record in enumerate(detail_records[:4], start=1):
            header = _build_detail_record_header(record, index)
            summary_line = _normalize_text(
                " · ".join(line for line in _build_detail_record_lines(record)[:2] if line),
                limit=240,
            )
            detail_summary_rows.append(
                [
                    paragraph(escape(header), table_cell_style),
                    paragraph(escape(summary_line or "-"), table_cell_style),
                ]
            )

        detail_summary_table = table(detail_summary_rows, colWidths=[34 * mm, 128 * mm], repeatRows=1)
        detail_summary_table.setStyle(
            table_style(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(detail_summary_table)
        story.append(spacer(1, 3 * mm))

        story.append(paragraph("사례별 세부", section_style))
        for index, record in enumerate(detail_records[:4], start=1):
            story.append(paragraph(escape(_build_detail_record_header(record, index)), section_style))
            for line in _build_detail_record_lines(record):
                story.append(paragraph(escape(line), bullet_style, bulletText="•"))
            story.append(spacer(1, 2 * mm))
    else:
        story.append(paragraph(escape("세부 풀이 기록이 아직 저장되지 않았습니다."), base_style))

    for section_title, section_items, empty_text in (
        ("실행 순서", brief.get("nextSteps") or [], "바로 실행할 단계가 아직 정리되지 않았습니다."),
        ("지금 집중할 것", brief.get("focusActions") or [], "우선 실행 항목이 아직 정리되지 않았습니다."),
        ("학습 루틴", brief.get("learningHabits") or [], "추천 루틴이 아직 정리되지 않았습니다."),
        ("다음 체크포인트", brief.get("checkpoints") or [], "확인할 체크포인트가 아직 없습니다."),
    ):
        story.append(paragraph(section_title, section_style))
        if section_items:
            for item in section_items:
                story.append(paragraph(escape(item), bullet_style, bulletText="•"))
        else:
            story.append(paragraph(escape(empty_text), base_style))

    buffer = BytesIO()
    document = simple_doc_template(
        buffer,
        pagesize=a4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=brief.get("title") or "학습 리포트",
        author="Code Learning Platform",
    )
    document.build(story)
    return buffer.getvalue()


def generate_report_pdf_download(db: Session, user_id: int, report_id: int) -> tuple[str, bytes]:
    report = (
        db.query(Report)
        .filter(Report.id == report_id, Report.user_id == user_id)
        .first()
    )
    if report is None:
        raise LookupError("report_not_found")

    filename = f"learning-report-{int(report.id)}.pdf"
    return filename, build_report_pdf_bytes(report)


def get_latest_report_download_metadata(db: Session, user_id: int) -> dict[str, Any]:
    report = _load_latest_milestone_report(db, user_id)

    if report is None:
        return {
            "available": False,
            "reportId": None,
            "createdAt": None,
            "goal": "",
            "summary": "",
            "pdfDownloadUrl": None,
        }

    brief = build_report_brief_from_report(report)
    return {
        "available": True,
        "reportId": int(report.id),
        "createdAt": serialize_report_created_at(report.created_at),
        "goal": _normalize_text(brief.get("title"), limit=120) or _normalize_text(report.title, limit=120),
        "summary": _normalize_text(brief.get("summary"), limit=220) or _normalize_text(report.summary, limit=220),
        "pdfDownloadUrl": build_report_pdf_download_url(report.id),
    }
