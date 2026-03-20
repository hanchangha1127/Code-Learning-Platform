from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.orm import Session, joinedload

from backend.ai_client import AIClient
from app.db.base import utcnow
from app.db.models import AIAnalysis, Report, ReportType, Submission, SubmissionStatus, UserProblemStat
from app.services.problem_stat_service import classify_wrong_answer_type
from app.services.report_pdf_service import build_report_brief, build_report_pdf_download_url

_learning_report_ai = AIClient()

_REPORT_CONTEXT_LIMIT = 15
_REPORT_SIGNAL_LIMIT = 5


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_wrong_type_counts(payload: Any) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not isinstance(payload, dict):
        return counter

    raw_types = payload.get("types")
    if not isinstance(raw_types, dict):
        return counter

    for wrong_type, count in raw_types.items():
        if not isinstance(wrong_type, str):
            continue
        parsed = _to_int(count)
        if parsed is None or parsed <= 0:
            continue
        counter[wrong_type] += parsed

    return counter


def _safe_enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _new_status_bucket() -> dict[str, Any]:
    return {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "error": 0,
        "processing": 0,
        "pending": 0,
        "_scores": [],
    }


def _accumulate_submission(bucket: dict[str, Any], submission: Submission) -> None:
    bucket["total"] += 1
    status_key = _safe_enum_value(submission.status)
    if status_key in ("passed", "failed", "error", "processing", "pending"):
        bucket[status_key] += 1

    if submission.score is not None:
        bucket["_scores"].append(submission.score)


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    scores = bucket.pop("_scores", [])
    total = bucket["total"]
    bucket["avg_score"] = int(sum(scores) / len(scores)) if scores else None
    bucket["accuracy"] = round((bucket["passed"] / total) * 100, 1) if total else None
    return bucket


def _window_metrics(submissions: list[Submission]) -> dict[str, Any]:
    metrics = _new_status_bucket()
    for submission in submissions:
        _accumulate_submission(metrics, submission)
    return _finalize_bucket(metrics)


def _build_trend(submissions_desc: list[Submission]) -> dict[str, Any]:
    total = len(submissions_desc)
    if total < 4:
        return {
            "label": "insufficient_data",
            "window_size": 0,
            "recent": None,
            "previous": None,
            "accuracy_delta": None,
            "avg_score_delta": None,
        }

    window_size = min(10, total // 2)
    recent = submissions_desc[:window_size]
    previous = submissions_desc[window_size : window_size * 2]

    recent_metrics = _window_metrics(recent)
    previous_metrics = _window_metrics(previous)

    recent_acc = recent_metrics.get("accuracy")
    prev_acc = previous_metrics.get("accuracy")
    recent_avg = recent_metrics.get("avg_score")
    prev_avg = previous_metrics.get("avg_score")

    accuracy_delta = None
    if recent_acc is not None and prev_acc is not None:
        accuracy_delta = round(recent_acc - prev_acc, 1)

    avg_score_delta = None
    if recent_avg is not None and prev_avg is not None:
        avg_score_delta = recent_avg - prev_avg

    label = "stable"
    if accuracy_delta is not None:
        if accuracy_delta >= 5:
            label = "improving"
        elif accuracy_delta <= -5:
            label = "declining"

    return {
        "label": label,
        "window_size": window_size,
        "recent": recent_metrics,
        "previous": previous_metrics,
        "accuracy_delta": accuracy_delta,
        "avg_score_delta": avg_score_delta,
    }


def _weakness_for_type(wrong_type: str) -> str:
    mapping = {
        "syntax_error": "문법 오류가 반복됩니다.",
        "runtime_error": "런타임 예외 처리 안정성이 낮습니다.",
        "logic_error": "정답 로직 검증이 부족합니다.",
        "timeout_error": "시간 복잡도/성능 최적화가 필요합니다.",
        "analysis_error": "분석 파이프라인 오류가 있었습니다.",
        "unknown_error": "오답 원인 분류가 불충분합니다.",
    }
    return mapping.get(wrong_type, f"{wrong_type} 유형 오답이 반복됩니다.")


def _recommendation_for_type(wrong_type: str) -> str:
    mapping = {
        "syntax_error": "제출 전 문법 체크(괄호, 콜론, 들여쓰기) 루틴을 고정하세요.",
        "runtime_error": "예외 케이스(빈 입력/범위 초과/null)를 먼저 테스트하세요.",
        "logic_error": "반례 3개를 직접 만들고 기대값과 실제값을 비교하세요.",
        "timeout_error": "입력 크기 기준으로 복잡도를 먼저 계산한 뒤 구현하세요.",
        "analysis_error": "잠시 후 재시도하거나 코드/입력을 단순화해 재분석하세요.",
        "unknown_error": "오답 제출의 분석 로그를 확인해 원인 태깅을 보강하세요.",
    }
    return mapping.get(wrong_type, "오답 원인을 세분화해서 재학습 계획을 세우세요.")


def _rank_weak_buckets(breakdown: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, stats in breakdown.items():
        rows.append(
            {
                "name": name,
                "total": stats.get("total", 0),
                "accuracy": stats.get("accuracy"),
                "avg_score": stats.get("avg_score"),
            }
        )

    rows = [row for row in rows if row["total"] >= 1]
    rows.sort(
        key=lambda row: (
            101 if row["accuracy"] is None else row["accuracy"],
            -(row["total"]),
        )
    )
    return rows[:3]


def _load_recent_submissions(db: Session, user_id: int, problem_count: int) -> list[Submission]:
    return (
        db.query(Submission)
        .options(joinedload(Submission.problem))
        .filter(Submission.user_id == user_id)
        .order_by(Submission.id.desc())
        .limit(problem_count)
        .all()
    )


def _load_recent_analyses(db: Session, user_id: int, sub_ids: list[int]) -> list[AIAnalysis]:
    if not sub_ids:
        return []
    return (
        db.query(AIAnalysis)
        .filter(AIAnalysis.user_id == user_id, AIAnalysis.submission_id.in_(sub_ids))
        .order_by(AIAnalysis.id.desc())
        .limit(50)
        .all()
    )


def _collect_wrong_type_counter(
    db: Session,
    user_id: int,
    problem_ids: list[int],
) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not problem_ids:
        return counter

    stats_rows = (
        db.query(UserProblemStat)
        .filter(
            UserProblemStat.user_id == user_id,
            UserProblemStat.problem_id.in_(problem_ids),
        )
        .all()
    )
    for row in stats_rows:
        counter.update(_extract_wrong_type_counts(row.wrong_answer_types))
    return counter


def _build_breakdowns(
    submissions: list[Submission],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    difficulty_buckets: dict[str, dict[str, Any]] = {}
    language_buckets: dict[str, dict[str, Any]] = {}

    for submission in submissions:
        problem = submission.problem
        difficulty_key = _safe_enum_value(problem.difficulty) if problem is not None else "unknown"
        language_key = (submission.language or (problem.language if problem is not None else "unknown")).lower()

        if difficulty_key not in difficulty_buckets:
            difficulty_buckets[difficulty_key] = _new_status_bucket()
        if language_key not in language_buckets:
            language_buckets[language_key] = _new_status_bucket()

        _accumulate_submission(difficulty_buckets[difficulty_key], submission)
        _accumulate_submission(language_buckets[language_key], submission)

    difficulty_breakdown = {
        key: _finalize_bucket(bucket)
        for key, bucket in difficulty_buckets.items()
    }
    language_breakdown = {
        key: _finalize_bucket(bucket)
        for key, bucket in language_buckets.items()
    }
    return difficulty_breakdown, language_breakdown


def _summarize_milestone(
    total: int,
    overall: dict[str, Any],
    top_wrong_types: list[dict[str, Any]],
    trend: dict[str, Any],
) -> tuple[str, str]:
    title = f"Milestone Report: last {total} submissions"
    if total == 0:
        return title, "아직 제출 이력이 없습니다. 첫 문제를 풀고 리포트를 생성해보세요."

    summary = (
        f"최근 {total}회 제출 기준 통과 {overall['passed']}, 실패 {overall['failed']}, 오류 {overall['error']}, "
        f"정확도 {overall['accuracy'] if overall['accuracy'] is not None else 'N/A'}%, "
        f"평균 점수 {overall['avg_score'] if overall['avg_score'] is not None else 'N/A'}입니다."
    )
    if top_wrong_types:
        summary += f" 상위 오답 유형은 '{top_wrong_types[0]['type']}' 입니다."
    if trend.get("label") == "improving":
        summary += " 최근 추세는 개선 중입니다."
    elif trend.get("label") == "declining":
        summary += " 최근 추세가 하락하고 있어 학습 전략 조정이 필요합니다."
    return title, summary


def _build_actions(
    *,
    total: int,
    overall: dict[str, Any],
    top_wrong_types: list[dict[str, Any]],
    trend: dict[str, Any],
    difficulty_breakdown: dict[str, dict[str, Any]],
    language_breakdown: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    strengths: list[str] = []
    weaknesses: list[str] = []
    recommendations: list[str] = []

    if total > 0 and (overall.get("accuracy") or 0) >= 70:
        strengths.append("정답률이 안정적으로 유지되고 있습니다.")
    if (overall.get("avg_score") or 0) >= 80:
        strengths.append("평균 점수가 높아 기본기 완성도가 좋습니다.")
    if trend.get("label") == "improving":
        strengths.append("최근 제출 추세가 개선되고 있습니다.")

    for item in top_wrong_types:
        wrong_type = item["type"]
        weaknesses.append(_weakness_for_type(wrong_type))
        recommendations.append(_recommendation_for_type(wrong_type))

    weak_difficulties = _rank_weak_buckets(difficulty_breakdown)
    weak_languages = _rank_weak_buckets(language_breakdown)

    if weak_difficulties:
        top_diff = weak_difficulties[0]
        weaknesses.append(f"{top_diff['name']} 난이도 구간에서 성과가 낮습니다.")
        recommendations.append(f"{top_diff['name']} 난이도 문제를 짧은 세트로 반복하세요.")

    if weak_languages:
        top_lang = weak_languages[0]
        weaknesses.append(f"{top_lang['name']} 언어 제출의 정확도가 낮습니다.")
        recommendations.append(f"{top_lang['name']} 언어 문법/표준 라이브러리 복습이 필요합니다.")

    if trend.get("label") == "declining":
        recommendations.append("최근 오답 코드 3개를 복기하고 재제출 기준 체크리스트를 만드세요.")

    if not recommendations:
        recommendations.append("다음 학습에서 다른 난이도/유형 문제를 섞어 일반화 성능을 점검하세요.")

    strengths = list(dict.fromkeys(strengths))
    weaknesses = list(dict.fromkeys(weaknesses))
    recommendations = list(dict.fromkeys(recommendations))
    return strengths, weaknesses, recommendations, weak_difficulties, weak_languages


def _trend_text_from_stats(trend: dict[str, Any]) -> str:
    label = str(trend.get("label") or "").strip().lower()
    if label == "improving":
        return "최근 정확도와 점수 추세가 개선 중입니다."
    if label == "declining":
        return "최근 정확도와 점수 추세가 하락 중입니다."
    if label == "stable":
        return "최근 학습 추세는 안정적입니다."
    return "추세를 판단할 데이터가 부족합니다."


def _clip_detail_text(value: Any, limit: int = 600) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 18, 0)].rstrip()}...(truncated)"


def _normalize_detail_list(value: Any, *, limit: int = 6, item_limit: int = 180) -> list[str]:
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
                or item.get("diff")
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


def _mode_from_problem_kind(kind: Any) -> str:
    value = _safe_enum_value(kind).strip().lower()
    return {
        "analysis": "analysis",
        "coding": "analysis",
        "code_block": "code-block",
        "code_arrange": "code-arrange",
        "code_calc": "code-calc",
        "code_error": "code-error",
        "auditor": "auditor",
        "context_inference": "context-inference",
        "refactoring_choice": "refactoring-choice",
        "code_blame": "code-blame",
    }.get(value, value or "analysis")


def _mode_from_problem(
    problem: Problem | None,
    *,
    problem_payload: dict[str, Any],
    answer_payload: dict[str, Any],
) -> str:
    for payload in (problem_payload, answer_payload):
        raw_mode = str(payload.get("mode") or "").strip()
        if raw_mode:
            return raw_mode

    workspace = str(problem_payload.get("workspace") or "").strip().lower()
    workspace_mode = {
        "single-file-analysis.workspace": "single-file-analysis",
        "multi-file-analysis.workspace": "multi-file-analysis",
        "fullstack-analysis.workspace": "fullstack-analysis",
    }.get(workspace)
    if workspace_mode:
        return workspace_mode

    external_id = str(getattr(problem, "external_id", "") or "").strip().lower()
    if external_id:
        prefix = external_id.split(":", 1)[0]
        inferred_mode = {
            "sfile": "single-file-analysis",
            "mfile": "multi-file-analysis",
            "fstack": "fullstack-analysis",
            "rchoice": "refactoring-choice",
            "cblame": "code-blame",
            "auditor": "auditor",
            "ccalc": "code-calc",
            "cblock": "code-block",
            "analysis": "analysis",
        }.get(prefix)
        if inferred_mode:
            return inferred_mode

    return _mode_from_problem_kind(problem.kind if problem is not None else "analysis")


def _mode_label(mode: str) -> str:
    return {
        "analysis": "코드 설명",
        "code-block": "빈칸 채우기",
        "code-arrange": "코드 정렬",
        "code-calc": "출력 예측",
        "code-error": "오류 찾기",
        "auditor": "감사관",
        "context-inference": "맥락 추론",
        "refactoring-choice": "리팩토링 선택",
        "code-blame": "코드 블레임",
        "single-file-analysis": "단일 파일 분석",
        "multi-file-analysis": "멀티 파일 분석",
        "fullstack-analysis": "풀스택 분석",
    }.get(mode, mode or "unknown")


def _latest_analyses_by_submission(analyses: list[AIAnalysis]) -> dict[int, AIAnalysis]:
    rows: dict[int, AIAnalysis] = {}
    for analysis in analyses:
        submission_id = getattr(analysis, "submission_id", None)
        if submission_id is None or submission_id in rows:
            continue
        rows[int(submission_id)] = analysis
    return rows


def _load_problem_stats_map(
    db: Session,
    user_id: int,
    problem_ids: list[int],
) -> dict[int, UserProblemStat]:
    if not problem_ids:
        return {}
    rows = (
        db.query(UserProblemStat)
        .filter(
            UserProblemStat.user_id == user_id,
            UserProblemStat.problem_id.in_(problem_ids),
        )
        .all()
    )
    return {int(row.problem_id): row for row in rows}


def _collect_wrong_type_counter_from_stats(stats_map: dict[int, UserProblemStat]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in stats_map.values():
        counter.update(_extract_wrong_type_counts(row.wrong_answer_types))
    return counter


def _extract_feedback_summary(analysis: AIAnalysis | None) -> str | None:
    if analysis is None:
        return None
    result_payload = analysis.result_payload if isinstance(analysis.result_payload, dict) else {}
    feedback = result_payload.get("feedback") if isinstance(result_payload.get("feedback"), dict) else {}
    return (
        _clip_detail_text(feedback.get("summary"), 280)
        or _clip_detail_text(analysis.result_summary, 280)
        or _clip_detail_text(analysis.result_detail, 280)
    )


def _collect_feedback_items(
    analyses_by_submission: dict[int, AIAnalysis],
    *,
    key: str,
    limit: int = 3,
    item_limit: int = 180,
) -> list[str]:
    rows: list[str] = []
    for analysis in analyses_by_submission.values():
        result_payload = analysis.result_payload if isinstance(analysis.result_payload, dict) else {}
        feedback = result_payload.get("feedback") if isinstance(result_payload.get("feedback"), dict) else {}
        value = feedback.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            normalized = _clip_detail_text(item, item_limit)
            if not normalized or normalized in rows:
                continue
            rows.append(normalized)
            if len(rows) >= limit:
                return rows
    return rows


def _normalize_counter_rows(
    counter: Counter[str],
    *,
    limit: int = _REPORT_SIGNAL_LIMIT,
    item_limit: int = 180,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, count in counter.most_common(limit):
        normalized_label = _clip_detail_text(label, item_limit)
        if not normalized_label or count <= 0:
            continue
        rows.append({"label": normalized_label, "count": int(count)})
    return rows


def _extract_duration_seconds(payload: dict[str, Any]) -> int | None:
    for key in ("durationSeconds", "duration_seconds", "elapsedSeconds", "elapsed_seconds"):
        value = payload.get(key)
        try:
            if value is None:
                continue
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            return parsed
    return None


def _build_learning_history_context_from_records(detail_records: list[dict[str, Any]]) -> str:
    if not detail_records:
        return "최근 제출 이력이 없습니다."

    lines: list[str] = []
    for idx, record in enumerate(detail_records[:_REPORT_CONTEXT_LIMIT], 1):
        evaluation = record.get("evaluation") if isinstance(record.get("evaluation"), dict) else {}
        question_context = record.get("questionContext") if isinstance(record.get("questionContext"), dict) else {}

        header = (
            f"{idx}. [{record.get('modeLabel') or record.get('mode') or 'practice'}] "
            f"{record.get('title') or 'Untitled'}"
        )
        meta_parts = [
            f"result={record.get('result') or '-'}",
            f"score={record.get('score') if record.get('score') is not None else 'N/A'}",
        ]
        if record.get("difficulty"):
            meta_parts.append(f"difficulty={record['difficulty']}")
        if record.get("language"):
            meta_parts.append(f"language={record['language']}")
        duration_seconds = record.get("durationSeconds")
        if duration_seconds is not None:
            meta_parts.append(f"duration={duration_seconds}s")
        attempts_on_problem = record.get("attemptsOnProblem")
        if attempts_on_problem is not None:
            meta_parts.append(f"attemptsOnProblem={attempts_on_problem}")
        lines.append(header)
        lines.append(f"   {' | '.join(meta_parts)}")

        prompt = _clip_detail_text(question_context.get("prompt"), 180)
        if prompt:
            lines.append(f"   question={prompt}")
        learner_response = _clip_detail_text(record.get("learnerResponse"), 260)
        if learner_response:
            lines.append(f"   learner={learner_response}")
        expected_answer = _clip_detail_text(record.get("expectedAnswer"), 220)
        if expected_answer:
            lines.append(f"   expected={expected_answer}")

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


def _build_learning_evidence_from_records(detail_records: list[dict[str, Any]]) -> dict[str, Any]:
    mode_counter: Counter[str] = Counter()
    result_counter: Counter[str] = Counter()
    wrong_type_counter: Counter[str] = Counter()
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

        duration_seconds = record.get("durationSeconds")
        try:
            if duration_seconds is not None:
                duration_values.append(int(duration_seconds))
        except (TypeError, ValueError):
            pass

        evaluation = record.get("evaluation") if isinstance(record.get("evaluation"), dict) else {}
        wrong_type = _clip_detail_text(evaluation.get("wrongType"), 80)
        if wrong_type:
            wrong_type_counter[wrong_type] += 1

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
        "repeatedWrongTypes": _normalize_counter_rows(wrong_type_counter, item_limit=80),
        "repeatedMissedPoints": _normalize_counter_rows(missed_counter, item_limit=120),
        "repeatedStrengths": _normalize_counter_rows(strength_counter, item_limit=120),
        "repeatedImprovements": _normalize_counter_rows(improvement_counter, item_limit=120),
        "averageDurationSeconds": average_duration_seconds,
        "detailRecordCount": len(detail_records),
    }


def _load_user_milestone_reports(db: Session, user_id: int) -> list[Report]:
    return (
        db.query(Report)
        .filter(
            Report.user_id == user_id,
            Report.report_type == ReportType.milestone,
        )
        .all()
    )


def _prune_old_milestone_reports(db: Session, *, user_id: int, keep_report_id: int | None) -> None:
    if keep_report_id is None:
        return

    for report in _load_user_milestone_reports(db, user_id):
        report_id = getattr(report, "id", None)
        if report_id is None or int(report_id) == int(keep_report_id):
            continue
        db.delete(report)


def _extract_reference_answer(
    *,
    mode: str,
    problem_payload: dict[str, Any],
    answer_payload: dict[str, Any],
    problem: Any,
    result_payload: dict[str, Any],
) -> str | None:
    if mode == "code-block":
        options = problem_payload.get("options")
        answer_index = problem_payload.get("answer_index")
        if not isinstance(options, list) and isinstance(getattr(problem, "options", None), list):
            options = getattr(problem, "options")
        if answer_index is None:
            answer_index = getattr(problem, "answer_index", None)
        try:
            normalized_index = int(answer_index) if answer_index is not None else None
        except (TypeError, ValueError):
            normalized_index = None
        if isinstance(options, list) and normalized_index is not None and 0 <= normalized_index < len(options):
            return _clip_detail_text(options[normalized_index], 220)

    if mode == "code-calc":
        return _clip_detail_text(answer_payload.get("expected_output") or problem_payload.get("expected_output"), 220)

    if mode == "code-error":
        correct_index = answer_payload.get("wrong_block_index") or problem_payload.get("wrong_block_index")
        try:
            return f"{int(correct_index) + 1}번 블록"
        except (TypeError, ValueError):
            return None

    if mode == "code-arrange":
        correct_order = answer_payload.get("correct_order") or problem_payload.get("correct_order")
        if isinstance(correct_order, list) and correct_order:
            return "정답 순서: " + " -> ".join(str(item) for item in correct_order[:8])

    if mode == "refactoring-choice":
        best_option = _clip_detail_text(
            result_payload.get("bestOption")
            or result_payload.get("best_option")
            or answer_payload.get("best_option")
            or problem_payload.get("best_option"),
            40,
        )
        if best_option:
            return f"권장 선택지: {best_option}"

    if mode == "code-blame":
        culprit_commits = _normalize_detail_list(
            result_payload.get("culpritCommits")
            or result_payload.get("culprit_commits")
            or answer_payload.get("culprit_commits")
            or problem_payload.get("culprit_commits"),
            limit=4,
            item_limit=40,
        )
        if culprit_commits:
            return "범인 커밋: " + ", ".join(culprit_commits)

    reference_report = (
        result_payload.get("referenceReport")
        or result_payload.get("reference_report")
        or answer_payload.get("reference_report")
        or problem_payload.get("reference_report")
        or getattr(problem, "reference_solution", None)
    )
    return _clip_detail_text(reference_report, 700)


def _extract_learner_response(
    *,
    mode: str,
    submission: Submission,
    submission_payload: dict[str, Any],
    problem_payload: dict[str, Any],
) -> str | None:
    if mode == "code-block":
        selected = submission_payload.get("selectedOption")
        if selected is None:
            selected = submission_payload.get("selected_option")
        options = problem_payload.get("options")
        try:
            selected_index = int(selected) if selected is not None else None
        except (TypeError, ValueError):
            selected_index = None
        if isinstance(options, list) and selected_index is not None and 0 <= selected_index < len(options):
            return _clip_detail_text(f"선택: {options[selected_index]}", 220)
        if selected is not None:
            return _clip_detail_text(f"선택 옵션: {selected}", 220)
        return None

    if mode == "code-arrange":
        order = submission_payload.get("order")
        if isinstance(order, list) and order:
            return _clip_detail_text("제출 순서: " + " -> ".join(str(item) for item in order[:8]), 260)
        return None

    if mode == "code-calc":
        value = submission_payload.get("output") or submission_payload.get("outputText") or submission_payload.get("output_text")
        if value is None:
            value = submission.code
        return _clip_detail_text(value, 220)

    if mode == "code-error":
        selected = submission_payload.get("selectedIndex")
        if selected is None:
            selected = submission_payload.get("selected_index")
        try:
            return f"{int(selected) + 1}번 블록"
        except (TypeError, ValueError):
            return _clip_detail_text(selected, 80)

    if mode == "code-blame":
        commits = _normalize_detail_list(
            submission_payload.get("selectedCommits") or submission_payload.get("selected_commits"),
            limit=4,
            item_limit=40,
        )
        report = _clip_detail_text(submission_payload.get("report") or submission.code, 700)
        if commits and report:
            return f"선택 커밋: {', '.join(commits)}\n리포트: {report}"
        if commits:
            return "선택 커밋: " + ", ".join(commits)
        return report

    if mode == "refactoring-choice":
        selected_option = _clip_detail_text(
            submission_payload.get("selectedOption") or submission_payload.get("selected_option"),
            40,
        )
        report = _clip_detail_text(submission_payload.get("report") or submission.code, 700)
        if selected_option and report:
            return f"선택지: {selected_option}\n리포트: {report}"
        if selected_option:
            return f"선택지: {selected_option}"
        return report

    return _clip_detail_text(submission.code, 900)


def _build_submission_comparison(
    *,
    mode: str,
    submission: Submission,
    submission_payload: dict[str, Any],
    problem_payload: dict[str, Any],
    answer_payload: dict[str, Any],
    result_payload: dict[str, Any],
    wrong_type: str | None,
    feedback_summary: str | None,
) -> str | None:
    is_correct = submission.status == SubmissionStatus.passed

    if mode == "code-block":
        selected = _extract_learner_response(
            mode=mode,
            submission=submission,
            submission_payload=submission_payload,
            problem_payload=problem_payload,
        )
        expected = _extract_reference_answer(
            mode=mode,
            problem_payload=problem_payload,
            answer_payload=answer_payload,
            problem=submission.problem,
            result_payload=result_payload,
        )
        if selected and expected and not is_correct:
            return f"{selected}를 골랐지만 정답은 {expected}였습니다."
        if selected and expected and is_correct:
            return f"{expected}를 정확히 골랐습니다."

    if mode == "code-calc":
        submitted = _clip_detail_text(
            submission_payload.get("output") or submission_payload.get("outputText") or submission_payload.get("output_text") or submission.code,
            220,
        )
        expected = _clip_detail_text(answer_payload.get("expected_output") or problem_payload.get("expected_output"), 220)
        if submitted and expected and not is_correct:
            return f"예상 출력 '{expected}' 대신 '{submitted}'를 제출했습니다."
        if submitted and expected and is_correct:
            return f"출력 '{submitted}'를 정확히 예측했습니다."

    if mode == "code-error":
        selected = _extract_learner_response(
            mode=mode,
            submission=submission,
            submission_payload=submission_payload,
            problem_payload=problem_payload,
        )
        expected = _extract_reference_answer(
            mode=mode,
            problem_payload=problem_payload,
            answer_payload=answer_payload,
            problem=submission.problem,
            result_payload=result_payload,
        )
        if selected and expected and not is_correct:
            return f"{selected}을 골랐지만 실제 오류 블록은 {expected}였습니다."
        if selected and expected and is_correct:
            return f"오류 블록 {expected}을 정확히 찾았습니다."

    if mode == "refactoring-choice":
        selected = _clip_detail_text(submission_payload.get("selectedOption") or submission_payload.get("selected_option"), 40)
        best_option = _clip_detail_text(
            result_payload.get("bestOption")
            or result_payload.get("best_option")
            or answer_payload.get("best_option")
            or problem_payload.get("best_option"),
            40,
        )
        if selected and best_option and selected != best_option:
            return f"사용자는 {selected}를 골랐고 권장 선택지는 {best_option}였습니다."
        if selected and best_option:
            return f"권장 선택지 {best_option}를 정확히 골랐습니다."

    if mode == "code-blame":
        selected_commits = _normalize_detail_list(
            submission_payload.get("selectedCommits") or submission_payload.get("selected_commits"),
            limit=4,
            item_limit=40,
        )
        culprit_commits = _normalize_detail_list(
            result_payload.get("culpritCommits")
            or result_payload.get("culprit_commits")
            or answer_payload.get("culprit_commits")
            or problem_payload.get("culprit_commits"),
            limit=4,
            item_limit=40,
        )
        if selected_commits and culprit_commits and set(selected_commits) != set(culprit_commits):
            return (
                f"사용자는 {', '.join(selected_commits)}를 지목했지만 "
                f"실제 범인 커밋은 {', '.join(culprit_commits)}였습니다."
            )
        if culprit_commits and is_correct:
            return f"범인 커밋 {', '.join(culprit_commits)}를 정확히 지목했습니다."

    if feedback_summary:
        return feedback_summary
    if wrong_type:
        return f"대표 오답 유형은 {wrong_type}입니다."
    return None


def _build_learning_detail_records(
    submissions: list[Submission],
    *,
    analyses_by_submission: dict[int, AIAnalysis],
    stats_by_problem: dict[int, UserProblemStat],
) -> list[dict[str, Any]]:
    detail_records: list[dict[str, Any]] = []
    for idx, submission in enumerate(submissions[:_REPORT_CONTEXT_LIMIT], 1):
        problem = submission.problem
        problem_payload = problem.problem_payload if problem and isinstance(problem.problem_payload, dict) else {}
        answer_payload = problem.answer_payload if problem and isinstance(problem.answer_payload, dict) else {}
        submission_payload = submission.submission_payload if isinstance(submission.submission_payload, dict) else {}
        analysis = analyses_by_submission.get(int(submission.id))
        result_payload = analysis.result_payload if analysis and isinstance(analysis.result_payload, dict) else {}
        feedback = result_payload.get("feedback") if isinstance(result_payload.get("feedback"), dict) else {}
        stat = stats_by_problem.get(int(submission.problem_id))
        wrong_payload = stat.wrong_answer_types if stat and isinstance(stat.wrong_answer_types, dict) else {}

        mode = _mode_from_problem(
            problem,
            problem_payload=problem_payload,
            answer_payload=answer_payload,
        )
        question_context: dict[str, Any] = {}
        prompt = _clip_detail_text(problem_payload.get("prompt") or (problem.description if problem is not None else ""), 700)
        if prompt:
            question_context["prompt"] = prompt
        starter_code = _clip_detail_text(
            problem_payload.get("starter_code")
            or problem_payload.get("code")
            or (problem.starter_code if problem is not None else ""),
            900,
        )
        if starter_code:
            question_context["codeOrContext"] = starter_code
        scenario = _clip_detail_text(problem_payload.get("scenario"), 400)
        if scenario:
            question_context["scenario"] = scenario
        error_log = _clip_detail_text(problem_payload.get("errorLog") or problem_payload.get("error_log"), 500)
        if error_log:
            question_context["errorLog"] = error_log
        options = _normalize_detail_list(problem_payload.get("options"), limit=6, item_limit=220)
        if options:
            question_context["options"] = options
        commits = _normalize_detail_list(problem_payload.get("commits"), limit=4, item_limit=220)
        if commits:
            question_context["commits"] = commits
        blocks = _normalize_detail_list(problem_payload.get("blocks"), limit=8, item_limit=220)
        if blocks:
            question_context["blocks"] = blocks
        workspace_files = _normalize_detail_list(
            problem_payload.get("files")
            or problem_payload.get("workspaceFiles")
            or problem_payload.get("workspace_files"),
            limit=6,
            item_limit=220,
        )
        if workspace_files:
            question_context["workspaceFiles"] = workspace_files

        learner_response = _extract_learner_response(
            mode=mode,
            submission=submission,
            submission_payload=submission_payload,
            problem_payload=problem_payload,
        )
        expected_answer = _extract_reference_answer(
            mode=mode,
            problem_payload=problem_payload,
            answer_payload=answer_payload,
            problem=problem,
            result_payload=result_payload,
        )
        wrong_type = wrong_payload.get("last_wrong_type")
        if not isinstance(wrong_type, str):
            wrong_type = classify_wrong_answer_type(
                submission.status,
                analysis_summary=analysis.result_summary if analysis else None,
                analysis_detail=analysis.result_detail if analysis else None,
            )
        comparison = _build_submission_comparison(
            mode=mode,
            submission=submission,
            submission_payload=submission_payload,
            problem_payload=problem_payload,
            answer_payload=answer_payload,
            result_payload=result_payload,
            wrong_type=wrong_type,
            feedback_summary=_extract_feedback_summary(analysis),
        )

        evaluation: dict[str, Any] = {}
        feedback_summary = (
            _clip_detail_text(feedback.get("summary"), 280)
            or _clip_detail_text(analysis.result_summary if analysis else "", 280)
            or _clip_detail_text(analysis.result_detail if analysis else "", 280)
        )
        if feedback_summary:
            evaluation["feedbackSummary"] = feedback_summary
        strengths = _normalize_detail_list(feedback.get("strengths"))
        if strengths:
            evaluation["strengths"] = strengths
        improvements = _normalize_detail_list(feedback.get("improvements"))
        if improvements:
            evaluation["improvements"] = improvements
        found_types = _normalize_detail_list(result_payload.get("foundTypes") or result_payload.get("found_types"))
        if found_types:
            evaluation["matchedPoints"] = found_types
        missed_types = _normalize_detail_list(result_payload.get("missedTypes") or result_payload.get("missed_types"))
        if missed_types:
            evaluation["missedPoints"] = missed_types
        if wrong_type:
            evaluation["wrongType"] = wrong_type
        wrong_type_counts = wrong_payload.get("types") if isinstance(wrong_payload.get("types"), dict) else {}
        if wrong_type_counts:
            evaluation["wrongTypeCounts"] = wrong_type_counts
        option_reviews = _normalize_detail_list(result_payload.get("optionReviews") or result_payload.get("option_reviews"))
        if option_reviews:
            evaluation["optionReviews"] = option_reviews
        commit_reviews = _normalize_detail_list(result_payload.get("commitReviews") or result_payload.get("commit_reviews"))
        if commit_reviews:
            evaluation["commitReviews"] = commit_reviews
        if comparison:
            evaluation["comparison"] = comparison
        reference_report = _clip_detail_text(
            result_payload.get("referenceReport")
            or result_payload.get("reference_report")
            or (problem.reference_solution if problem is not None else None),
            700,
        )
        if reference_report:
            evaluation["referenceExplanation"] = reference_report
        analysis_summary = _clip_detail_text(analysis.result_summary if analysis else None, 220)
        if analysis_summary:
            evaluation["analysisSummary"] = analysis_summary
        analysis_detail = _clip_detail_text(analysis.result_detail if analysis else None, 420)
        if analysis_detail:
            evaluation["analysisDetail"] = analysis_detail

        record: dict[str, Any] = {
            "attempt": idx,
            "submissionId": int(submission.id),
            "mode": mode,
            "modeLabel": _mode_label(mode),
            "title": _clip_detail_text(problem.title if problem is not None else "", 160) or "Untitled",
            "result": _safe_enum_value(submission.status),
            "summary": _clip_detail_text(problem.description if problem is not None else "", 240),
            "questionContext": question_context,
            "evaluation": evaluation,
        }
        if learner_response:
            record["learnerResponse"] = learner_response
        if expected_answer:
            record["expectedAnswer"] = expected_answer
        if submission.score is not None:
            record["score"] = submission.score
        duration_seconds = _extract_duration_seconds(submission_payload)
        if duration_seconds is not None:
            record["durationSeconds"] = duration_seconds
        difficulty = _safe_enum_value(problem.difficulty) if problem is not None else None
        if difficulty:
            record["difficulty"] = difficulty
        language = (submission.language or (problem.language if problem is not None else "unknown")).lower()
        if language:
            record["language"] = language
        if stat is not None:
            record["attemptsOnProblem"] = int(getattr(stat, "attempts", 0) or 0)
            if stat.last_submitted_at is not None:
                record["lastSubmittedAt"] = stat.last_submitted_at.isoformat()
        last_wrong_at = wrong_payload.get("last_wrong_at")
        if isinstance(last_wrong_at, str) and last_wrong_at.strip():
            record["lastWrongAt"] = last_wrong_at.strip()
        if submission.created_at is not None:
            record["submittedAt"] = submission.created_at.isoformat()
        detail_records.append(record)
    return detail_records


def create_milestone_report(db: Session, user_id: int, problem_count: int) -> dict[str, Any]:
    submissions = _load_recent_submissions(db, user_id, problem_count)

    overall = _window_metrics(submissions)
    total = overall["total"]

    sub_ids = [s.id for s in submissions]
    analyses = _load_recent_analyses(db, user_id, sub_ids)
    analyses_by_submission = _latest_analyses_by_submission(analyses)

    problem_ids = sorted({s.problem_id for s in submissions})
    stats_by_problem = _load_problem_stats_map(db, user_id, problem_ids)
    wrong_type_counter = _collect_wrong_type_counter_from_stats(stats_by_problem)

    top_wrong_types = [
        {"type": wrong_type, "count": count}
        for wrong_type, count in wrong_type_counter.most_common(3)
    ]

    difficulty_breakdown, language_breakdown = _build_breakdowns(submissions)

    trend = _build_trend(submissions)
    title, summary = _summarize_milestone(total, overall, top_wrong_types, trend)

    strengths, weaknesses, recommendations, weak_difficulties, weak_languages = _build_actions(
        total=total,
        overall=overall,
        top_wrong_types=top_wrong_types,
        trend=trend,
        difficulty_breakdown=difficulty_breakdown,
        language_breakdown=language_breakdown,
    )
    feedback_strengths = _collect_feedback_items(analyses_by_submission, key="strengths")
    feedback_improvements = _collect_feedback_items(analyses_by_submission, key="improvements")
    if not strengths and feedback_strengths:
        strengths = feedback_strengths
    for item in feedback_improvements:
        if item not in recommendations:
            recommendations.append(item)

    detail_records = _build_learning_detail_records(
        submissions,
        analyses_by_submission=analyses_by_submission,
        stats_by_problem=stats_by_problem,
    )
    learning_evidence = _build_learning_evidence_from_records(detail_records)
    history_context = _build_learning_history_context_from_records(detail_records)
    metric_snapshot: dict[str, Any] = {
        "attempts": int(total),
        "accuracy": overall.get("accuracy"),
        "avgScore": overall.get("avg_score"),
        "trend": _trend_text_from_stats(trend),
        "passed": overall.get("passed"),
        "failed": overall.get("failed"),
        "error": overall.get("error"),
        "processing": overall.get("processing"),
        "pending": overall.get("pending"),
        "analysisCount": len(analyses),
        "problemCount": len(problem_ids),
        "topWrongTypes": top_wrong_types,
        "weakDifficulties": weak_difficulties,
        "weakLanguages": weak_languages,
        "feedbackStrengths": feedback_strengths[:_REPORT_SIGNAL_LIMIT],
        "feedbackImprovements": feedback_improvements[:_REPORT_SIGNAL_LIMIT],
        **learning_evidence,
    }
    solution_plan = _learning_report_ai.generate_learning_solution_report(
        history_context=history_context,
        metric_snapshot=metric_snapshot,
        detail_records=detail_records,
    )
    report_brief = build_report_brief(
        solution_plan=solution_plan,
        metric_snapshot=metric_snapshot,
        fallback_title=title,
        fallback_summary=summary,
    )

    stats = {
        **overall,
        "source": "milestone_report",
        "analysis_count": len(analyses),
        "problem_count": len(problem_ids),
        "wrong_type_breakdown": dict(wrong_type_counter),
        "top_wrong_types": top_wrong_types,
        "difficulty_breakdown": difficulty_breakdown,
        "language_breakdown": language_breakdown,
        "trend": trend,
        "weak_difficulties": weak_difficulties,
        "weak_languages": weak_languages,
        "solutionPlan": solution_plan,
        "metricSnapshot": metric_snapshot,
        "reportBrief": report_brief,
        "detailRecords": detail_records,
        "learningEvidence": learning_evidence,
    }

    goal_for_db = str(solution_plan.get("goal") or title).strip() or title
    summary_for_db = str(solution_plan.get("solutionSummary") or summary).strip() or summary

    report = Report(
        user_id=user_id,
        report_type=ReportType.milestone,
        period_start=None,
        period_end=None,
        milestone_problem_count=problem_count,
        title=goal_for_db[:200],
        summary=summary_for_db,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=solution_plan.get("priorityActions") if isinstance(solution_plan.get("priorityActions"), list) else [],
        stats=stats,
        created_at=utcnow(),
    )
    db.add(report)
    db.flush()
    _prune_old_milestone_reports(db, user_id=user_id, keep_report_id=report.id)
    db.commit()
    db.refresh(report)
    return {
        "reportId": report.id,
        "createdAt": report.created_at.isoformat() if report.created_at is not None else utcnow().isoformat(),
        **solution_plan,
        "metricSnapshot": metric_snapshot,
        "reportBrief": report_brief,
        "pdfDownloadUrl": build_report_pdf_download_url(report.id),
    }
