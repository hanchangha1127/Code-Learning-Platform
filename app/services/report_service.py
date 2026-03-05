from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AIAnalysis, Report, ReportType, Submission, SubmissionStatus, UserProblemStat


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


def create_milestone_report(db: Session, user_id: int, problem_count: int) -> Report:
    submissions = _load_recent_submissions(db, user_id, problem_count)

    overall = _window_metrics(submissions)
    total = overall["total"]

    sub_ids = [s.id for s in submissions]
    analyses = _load_recent_analyses(db, user_id, sub_ids)

    problem_ids = sorted({s.problem_id for s in submissions})
    wrong_type_counter = _collect_wrong_type_counter(db, user_id, problem_ids)

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

    stats = {
        **overall,
        "analysis_count": len(analyses),
        "problem_count": len(problem_ids),
        "wrong_type_breakdown": dict(wrong_type_counter),
        "top_wrong_types": top_wrong_types,
        "difficulty_breakdown": difficulty_breakdown,
        "language_breakdown": language_breakdown,
        "trend": trend,
        "weak_difficulties": weak_difficulties,
        "weak_languages": weak_languages,
    }

    report = Report(
        user_id=user_id,
        report_type=ReportType.milestone,
        period_start=None,
        period_end=None,
        milestone_problem_count=problem_count,
        title=title,
        summary=summary,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
        stats=stats,
        created_at=datetime.utcnow(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
