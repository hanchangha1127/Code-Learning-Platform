from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    Problem,
    ReviewQueueItem,
    ReviewQueueStatus,
    Submission,
    SubmissionStatus,
    User,
    UserLearningGoal,
)
from backend.skill_levels import DEFAULT_SKILL_LEVEL, normalize_skill_level
from app.services.report_pdf_service import get_latest_report_detail

DEFAULT_DAILY_TARGET_SESSIONS = 10
DEFAULT_REVIEW_LIMIT = 5
WEEKLY_REPORT_STALE_DAYS = 7

MODE_LABELS: dict[str, str] = {
    "analysis": "\uCF54\uB4DC \uBD84\uC11D",
    "code-block": "\uCF54\uB4DC \uBE14\uB85D",
    "code-arrange": "\uCF54\uB4DC \uBC30\uCE58",
    "code-calc": "\uCF54\uB4DC \uACC4\uC0B0",
    "auditor": "\uAC10\uC0AC\uAD00 \uBAA8\uB4DC",
    "refactoring-choice": "\uCD5C\uC801\uC758 \uC120\uD0DD",
    "code-blame": "\uBC94\uC778 \uCC3E\uAE30",
    "single-file-analysis": "\uB2E8\uC77C \uD30C\uC77C \uBD84\uC11D",
    "multi-file-analysis": "\uB2E4\uC911 \uD30C\uC77C \uBD84\uC11D",
    "fullstack-analysis": "\uD480\uC2A4\uD0DD \uCF54\uB4DC \uBD84\uC11D",
}

MODE_LINKS: dict[str, str] = {
    "analysis": "/analysis.html",
    "code-block": "/codeblock.html",
    "code-arrange": "/arrange.html",
    "code-calc": "/codecalc.html",
    "auditor": "/auditor.html",
    "refactoring-choice": "/refactoring-choice.html",
    "code-blame": "/code-blame.html",
    "single-file-analysis": "/single-file-analysis.html",
    "multi-file-analysis": "/multi-file-analysis.html",
    "fullstack-analysis": "/fullstack-analysis.html",
}

WEAKNESS_LABELS: dict[str, str] = {
    "syntax_error": "\uBB38\uBC95 \uC624\uB958",
    "logic_error": "\uB85C\uC9C1 \uC624\uB958",
    "runtime_error": "\uC2E4\uD589 \uC624\uB958",
    "timeout_error": "\uC131\uB2A5 \uBCD1\uBAA9",
    "analysis_error": "\uBD84\uC11D \uD488\uC9C8",
    "unknown_error": "\uAE30\uBCF8\uAE30 \uBCF4\uAC15",
}


def get_or_create_learning_goal(db: Session, user_id: int) -> UserLearningGoal:
    goal = db.get(UserLearningGoal, user_id)
    if goal is not None:
        return goal

    goal = UserLearningGoal(
        user_id=user_id,
        weekly_target_sessions=DEFAULT_DAILY_TARGET_SESSIONS,
        daily_target_sessions=DEFAULT_DAILY_TARGET_SESSIONS,
        focus_modes=["analysis", "code-block", "code-calc"],
        focus_topics=[],
    )
    db.add(goal)
    try:
        db.commit()
        db.refresh(goal)
        return goal
    except IntegrityError:
        db.rollback()
        existing = db.get(UserLearningGoal, user_id)
        if existing is not None:
            return existing
        raise


def update_learning_goal(
    db: Session,
    user_id: int,
    *,
    daily_target_sessions: int,
    focus_modes: list[str] | None = None,
    focus_topics: list[str] | None = None,
) -> UserLearningGoal:
    goal = get_or_create_learning_goal(db, user_id)
    resolved_target = max(1, min(int(daily_target_sessions), 70))
    goal.daily_target_sessions = resolved_target
    goal.weekly_target_sessions = resolved_target
    if focus_modes is not None:
        goal.focus_modes = [mode for mode in focus_modes if mode in MODE_LABELS]
    if focus_topics is not None:
        goal.focus_topics = [str(topic).strip() for topic in focus_topics if str(topic).strip()]
    goal.updated_at = utcnow()
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def serialize_learning_goal(goal: UserLearningGoal) -> dict[str, Any]:
    daily_target = int(
        goal.daily_target_sessions
        or goal.weekly_target_sessions
        or DEFAULT_DAILY_TARGET_SESSIONS
    )
    focus_modes = [mode for mode in _normalize_string_list(goal.focus_modes) if mode in MODE_LABELS]
    return {
        "dailyTargetSessions": daily_target,
        "focusModes": focus_modes,
        "focusTopics": _normalize_string_list(goal.focus_topics),
        "updatedAt": goal.updated_at.isoformat() if goal.updated_at else None,
    }


def build_learning_home(
    *,
    db: Session,
    user: User,
    history: list[dict[str, Any]],
    profile: dict[str, Any],
    display_name: str | None = None,
) -> dict[str, Any]:
    goal = get_or_create_learning_goal(db, int(user.id))
    ordered_history = _sort_history(history)
    review_items = list_due_review_queue(db, int(user.id), limit=DEFAULT_REVIEW_LIMIT)

    daily_target = int(
        goal.daily_target_sessions
        or goal.weekly_target_sessions
        or DEFAULT_DAILY_TARGET_SESSIONS
    )
    daily_goal = _build_daily_goal(ordered_history, daily_target)
    streak_days = _calculate_streak_days(ordered_history, daily_target)
    trend = _build_trend(ordered_history)
    weak_topics = _extract_weak_topics(review_items, ordered_history, goal)
    recommended_modes = _recommend_modes(review_items, ordered_history, goal)
    today_tasks = _build_today_tasks(
        review_items=review_items,
        daily_goal=daily_goal,
        recommended_modes=recommended_modes,
        weak_topics=weak_topics,
    )
    weekly_report_card = _build_weekly_report_card(db, int(user.id))
    notifications = _build_notifications(
        review_items=review_items,
        daily_goal=daily_goal,
        streak_days=streak_days,
        recommended_modes=recommended_modes,
        weekly_report_card=weekly_report_card,
    )

    return {
        "displayName": display_name or profile.get("displayName") or profile.get("display_name") or user.username,
        "todayDate": utcnow().date().isoformat(),
        "streakDays": streak_days,
        "skillLevel": normalize_skill_level(profile.get("skillLevel"), DEFAULT_SKILL_LEVEL),
        "dailyGoal": daily_goal,
        "reviewQueue": {
            "dueCount": len(review_items),
            "items": review_items,
        },
        "todayTasks": today_tasks,
        "weakTopics": weak_topics,
        "recommendedModes": recommended_modes,
        "trend": trend,
        "stats": {
            "totalAttempts": int(profile.get("totalAttempts") or len(ordered_history)),
            "accuracy": float(profile.get("accuracy") or 0.0),
        },
        "focusModes": [mode for mode in _normalize_string_list(goal.focus_modes) if mode in MODE_LABELS],
        "focusTopics": _normalize_string_list(goal.focus_topics),
        "weeklyReportCard": weekly_report_card,
        "notifications": notifications,
    }


def list_due_review_queue(db: Session, user_id: int, *, limit: int = DEFAULT_REVIEW_LIMIT) -> list[dict[str, Any]]:
    now = utcnow()
    rows = (
        db.query(ReviewQueueItem)
        .filter(
            ReviewQueueItem.user_id == user_id,
            ReviewQueueItem.status == ReviewQueueStatus.pending,
            ReviewQueueItem.due_at <= now,
        )
        .order_by(ReviewQueueItem.priority.desc(), ReviewQueueItem.due_at.asc(), ReviewQueueItem.id.asc())
        .limit(limit)
        .all()
    )
    return [
        serialize_review_item(row)
        for row in rows
        if str(row.mode or "").strip().lower() in MODE_LINKS
    ]


def serialize_review_item(item: ReviewQueueItem) -> dict[str, Any]:
    mode = str(item.mode or "analysis").strip().lower()
    resume_link = _resume_link(mode, int(item.id))
    return {
        "id": int(item.id),
        "mode": mode,
        "modeLabel": MODE_LABELS.get(mode, mode),
        "title": item.title,
        "weaknessTag": item.weakness_tag,
        "weaknessLabel": weakness_label(item.weakness_tag),
        "dueAt": item.due_at.isoformat() if item.due_at else None,
        "priority": int(item.priority or 0),
        "actionLink": MODE_LINKS.get(mode, "/dashboard.html"),
        "resumeLink": resume_link,
        "sourceProblemId": item.source_problem_id,
    }


def resume_review_queue_item(db: Session, user_id: int, item_id: int) -> dict[str, Any]:
    item = (
        db.query(ReviewQueueItem)
        .filter(
            ReviewQueueItem.id == item_id,
            ReviewQueueItem.user_id == user_id,
            ReviewQueueItem.status == ReviewQueueStatus.pending,
        )
        .first()
    )
    if item is None or item.problem_id is None:
        raise LookupError("review_queue_item_not_found")

    problem = db.get(Problem, item.problem_id)
    if problem is None or not isinstance(problem.problem_payload, dict):
        raise LookupError("review_problem_not_found")

    mode = str(item.mode or "").strip().lower() or _mode_from_problem(problem)
    return {
        "reviewItemId": int(item.id),
        "mode": mode,
        "resumeLink": _resume_link(mode, int(item.id)),
        "problem": problem.problem_payload,
    }


def sync_review_queue_for_submission(
    *,
    db: Session,
    user_id: int,
    problem: Problem,
    submission: Submission,
    mode: str,
    result_payload: dict[str, Any],
    wrong_type: str | None,
    total_wrong: int,
) -> None:
    pending_item = (
        db.query(ReviewQueueItem)
        .filter(
            ReviewQueueItem.user_id == user_id,
            ReviewQueueItem.problem_id == problem.id,
            ReviewQueueItem.mode == mode,
            ReviewQueueItem.status == ReviewQueueStatus.pending,
        )
        .order_by(ReviewQueueItem.id.desc())
        .first()
    )

    if submission.status == SubmissionStatus.passed:
        if pending_item is not None:
            pending_item.status = ReviewQueueStatus.completed
            pending_item.completed_at = utcnow()
            pending_item.updated_at = utcnow()
            db.add(pending_item)
        return

    due_at = utcnow() + timedelta(hours=_next_review_delay_hours(total_wrong))
    title = str(problem.title or MODE_LABELS.get(mode) or "Review item")[:200]
    payload = {
        "summary": _feedback_summary(result_payload),
        "score": submission.score,
        "problemId": problem.external_id or str(problem.id),
    }

    if pending_item is None:
        pending_item = ReviewQueueItem(
            user_id=user_id,
            problem_id=problem.id,
            submission_id=submission.id,
            source_problem_id=problem.external_id or str(problem.id),
            mode=mode,
            title=title,
            weakness_tag=wrong_type,
            due_at=due_at,
            priority=_review_priority(total_wrong, wrong_type),
            status=ReviewQueueStatus.pending,
            payload=payload,
        )
    else:
        pending_item.submission_id = submission.id
        pending_item.source_problem_id = problem.external_id or str(problem.id)
        pending_item.title = title
        pending_item.weakness_tag = wrong_type
        pending_item.due_at = due_at
        pending_item.priority = _review_priority(total_wrong, wrong_type)
        pending_item.payload = payload
        pending_item.updated_at = utcnow()

    db.add(pending_item)


def weakness_label(tag: str | None) -> str | None:
    if not tag:
        return None
    return WEAKNESS_LABELS.get(tag, tag.replace("_", " "))


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _feedback_summary(result_payload: dict[str, Any]) -> str:
    feedback = result_payload.get("feedback")
    if isinstance(feedback, dict):
        return str(feedback.get("summary") or "").strip()
    return ""


def _sort_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(history, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def _parse_history_datetime(item: dict[str, Any]) -> datetime | None:
    raw = str(item.get("created_at") or "").strip()
    if not raw:
        return None
    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return _to_naive_utc(parsed)


def _calculate_streak_days(history: list[dict[str, Any]], daily_target_sessions: int) -> int:
    achieved_dates = _achieved_dates(history, daily_target_sessions)
    if not achieved_dates:
        return 0

    today = utcnow().date()
    if today in achieved_dates:
        current = today
    else:
        yesterday = today - timedelta(days=1)
        if yesterday not in achieved_dates:
            return 0
        current = yesterday

    streak = 0
    while current - timedelta(days=streak) in achieved_dates:
        streak += 1
    return streak


def _build_daily_goal(history: list[dict[str, Any]], daily_target_sessions: int) -> dict[str, Any]:
    today = utcnow().date()
    completed = 0
    for item in history:
        parsed = _parse_history_datetime(item)
        if parsed is None:
            continue
        if parsed.date() == today:
            completed += 1
    remaining = max(daily_target_sessions - completed, 0)
    progress = round(min((completed / max(daily_target_sessions, 1)) * 100.0, 100.0), 1)
    return {
        "date": today.isoformat(),
        "targetSessions": int(daily_target_sessions),
        "completedSessions": int(completed),
        "remainingSessions": int(remaining),
        "progressPercent": progress,
        "achieved": remaining == 0,
    }


def _build_trend(history: list[dict[str, Any]]) -> dict[str, Any]:
    now = utcnow()
    within_7: list[dict[str, Any]] = []
    within_30: list[dict[str, Any]] = []
    for item in history:
        parsed = _parse_history_datetime(item)
        if parsed is None:
            continue
        age = now - parsed
        if age <= timedelta(days=30):
            within_30.append(item)
        if age <= timedelta(days=7):
            within_7.append(item)
    return {
        "last7DaysAttempts": len(within_7),
        "last30DaysAttempts": len(within_30),
        "last7DaysAccuracy": _window_accuracy(within_7),
        "last30DaysAccuracy": _window_accuracy(within_30),
    }


def _window_accuracy(items: list[dict[str, Any]]) -> float | None:
    if not items:
        return None
    correct = sum(1 for item in items if item.get("correct") is True)
    return round((correct / len(items)) * 100.0, 1)


def _extract_weak_topics(
    review_items: list[dict[str, Any]],
    history: list[dict[str, Any]],
    goal: UserLearningGoal,
) -> list[str]:
    counter: Counter[str] = Counter()
    for item in review_items:
        label = item.get("weaknessLabel") or item.get("weaknessTag")
        if label:
            counter[str(label)] += 2
        mode_label = MODE_LABELS.get(str(item.get("mode") or ""), "")
        if mode_label:
            counter[mode_label] += 1

    for item in history[:20]:
        if item.get("correct") is True:
            continue
        mode_label = MODE_LABELS.get(str(item.get("mode") or ""), "")
        if mode_label:
            counter[mode_label] += 1

    for topic in _normalize_string_list(goal.focus_topics):
        counter[topic] += 1

    return [name for name, _count in counter.most_common(4)]


def _recommend_modes(
    review_items: list[dict[str, Any]],
    history: list[dict[str, Any]],
    goal: UserLearningGoal,
) -> list[dict[str, str]]:
    counter: Counter[str] = Counter()
    for item in review_items:
        mode = str(item.get("mode") or "").strip().lower()
        if mode:
            counter[mode] += 3

    for item in history[:15]:
        mode = str(item.get("mode") or "").strip().lower()
        if not mode:
            continue
        counter[mode] += 0 if item.get("correct") is True else 1

    for mode in _normalize_string_list(goal.focus_modes):
        counter[mode] += 2

    recommended: list[dict[str, str]] = []
    for mode, _count in counter.most_common(3):
        if mode not in MODE_LINKS:
            continue
        recommended.append({
            "mode": mode,
            "label": MODE_LABELS.get(mode, mode),
            "link": MODE_LINKS.get(mode, "/dashboard.html"),
        })

    if not recommended:
        recommended.append({
            "mode": "analysis",
            "label": MODE_LABELS["analysis"],
            "link": MODE_LINKS["analysis"],
        })
    return recommended


def _build_today_tasks(
    *,
    review_items: list[dict[str, Any]],
    daily_goal: dict[str, Any],
    recommended_modes: list[dict[str, str]],
    weak_topics: list[str],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []

    if review_items:
        tasks.append(
            {
                "type": "review",
                "title": "\uBCF5\uC2B5 \uD050 \uCC98\uB9AC",
                "description": "\uCD5C\uADFC \uD2C0\uB9B0 \uBB38\uC81C\uB97C \uB2E4\uC2DC \uD480\uACE0 \uC57D\uC810\uC744 \uBC14\uB85C\uC7A1\uC73C\uC138\uC694.",
                "actionLabel": "\uBCF5\uC2B5 \uC2DC\uC791",
                "actionLink": review_items[0].get("resumeLink") or review_items[0].get("actionLink") or "/dashboard.html",
            }
        )

    remaining = int(daily_goal.get("remainingSessions") or 0)
    if remaining > 0:
        primary_mode = recommended_modes[0] if recommended_modes else {"link": "/analysis.html", "label": MODE_LABELS["analysis"]}
        tasks.append(
            {
                "type": "practice",
                "title": f"\uC624\uB298 \uBAA9\uD45C\uAE4C\uC9C0 {remaining}\uBB38\uC81C \uB0A8\uC74C",
                "description": f"{primary_mode.get('label')}\uBD80\uD130 \uC774\uC5B4\uC11C \uD559\uC2B5\uD558\uB294 \uAC83\uC774 \uC88B\uC2B5\uB2C8\uB2E4.",
                "actionLabel": "\uBB38\uC81C \uD480\uAE30",
                "actionLink": primary_mode.get("link") or "/analysis.html",
            }
        )

    if weak_topics:
        tasks.append(
            {
                "type": "focus",
                "title": "\uC57D\uC810 \uC8FC\uC81C \uC9D1\uC911 \uBCF4\uAC15",
                "description": ", ".join(weak_topics[:3]),
                "actionLabel": "\uD504\uB85C\uD544 \uBCF4\uAE30",
                "actionLink": "/profile.html",
            }
        )

    return tasks[:3]


def _build_weekly_report_card(db: Session, user_id: int) -> dict[str, Any]:
    action_link = "/profile.html"
    detail = get_latest_report_detail(db, user_id)
    if detail is None:
        return {
            "available": False,
            "reportId": None,
            "createdAt": None,
            "goal": "",
            "solutionSummary": "",
            "actionLink": action_link,
            "stale": True,
        }

    created_at = detail.get("createdAt")
    parsed_created_at = None
    if isinstance(created_at, str) and created_at:
        try:
            parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            parsed_created_at = None
    stale = _is_report_stale(_to_naive_utc(parsed_created_at))
    return {
        "available": True,
        "reportId": int(detail.get("reportId")),
        "createdAt": created_at,
        "goal": str(detail.get("goal") or "").strip(),
        "solutionSummary": str(detail.get("solutionSummary") or "").strip(),
        "actionLink": action_link,
        "stale": stale,
    }


def _is_report_stale(created_at: datetime | None) -> bool:
    if created_at is None:
        return True
    return (_to_naive_utc(utcnow()) - _to_naive_utc(created_at)) >= timedelta(days=WEEKLY_REPORT_STALE_DAYS)


def _to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _build_notifications(
    *,
    review_items: list[dict[str, Any]],
    daily_goal: dict[str, Any],
    streak_days: int,
    recommended_modes: list[dict[str, str]],
    weekly_report_card: dict[str, Any],
) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []

    if review_items:
        first_review = review_items[0]
        notifications.append(
            {
                "type": "review_queue",
                "severity": "warn",
                "title": "\uBCF5\uC2B5\uD560 \uBB38\uC81C\uAC00 \uB0A8\uC544 \uC788\uC2B5\uB2C8\uB2E4.",
                "description": f"\uB300\uAE30 \uC911\uC778 \uBCF5\uC2B5 {len(review_items)}\uAC74\uC744 \uCC98\uB9AC\uD574 \uC57D\uC810\uC744 \uBC14\uB85C \uBCF4\uAC15\uD574 \uBCF4\uC138\uC694.",
                "actionLabel": "\uBCF5\uC2B5 \uC2DC\uC791",
                "actionLink": first_review.get("resumeLink") or first_review.get("actionLink") or "/dashboard.html",
                "count": len(review_items),
            }
        )

    remaining_sessions = int(daily_goal.get("remainingSessions") or 0)
    if remaining_sessions > 0:
        primary_mode = recommended_modes[0] if recommended_modes else {
            "link": MODE_LINKS["analysis"],
            "label": MODE_LABELS["analysis"],
        }
        notifications.append(
            {
                "type": "daily_goal",
                "severity": "info",
                "title": "\uC624\uB298 \uBAA9\uD45C\uB97C \uC544\uC9C1 \uCC44\uC6B0\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.",
                "description": f"\uC624\uB298 \uBAA9\uD45C\uAE4C\uC9C0 {remaining_sessions}\uBB38\uC81C\uAC00 \uB0A8\uC558\uC2B5\uB2C8\uB2E4. {primary_mode.get('label')}\uBD80\uD130 \uC774\uC5B4\uC11C \uD480\uC5B4 \uBCF4\uC138\uC694.",
                "actionLabel": "\uBB38\uC81C \uD480\uAE30",
                "actionLink": primary_mode.get("link") or MODE_LINKS["analysis"],
                "count": remaining_sessions,
            }
        )

    if not bool(weekly_report_card.get("available")) or bool(weekly_report_card.get("stale")):
        notifications.append(
            {
                "type": "weekly_report",
                "severity": "warn",
                "title": "\uC8FC\uAC04 \uB9AC\uD3EC\uD2B8\uB97C \uAC31\uC2E0\uD560 \uC2DC\uC810\uC785\uB2C8\uB2E4.",
                "description": "\uCD5C\uADFC \uD559\uC2B5 \uD750\uB984\uC744 \uAE30\uC900\uC73C\uB85C \uB2E4\uC74C \uC2E4\uD589 \uACC4\uD68D\uC744 \uB2E4\uC2DC \uC0DD\uC131\uD574 \uBCF4\uC138\uC694.",
                "actionLabel": "\uB9AC\uD3EC\uD2B8 \uAC31\uC2E0",
                "actionLink": "/dashboard.html#weekly-report-card",
                "count": 1,
            }
        )

    if streak_days > 0 and not bool(daily_goal.get("achieved")):
        notifications.append(
            {
                "type": "streak_risk",
                "severity": "urgent",
                "title": "\uC5F0\uC18D \uD559\uC2B5\uC774 \uB04A\uAE38 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
                "description": "\uC624\uB298 \uBAA9\uD45C\uB97C \uB2EC\uC131\uD574\uC57C \uD604\uC7AC \uC2A4\uD2B8\uB9AD\uC744 \uC774\uC5B4\uAC08 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
                "actionLabel": "\uC9C0\uAE08 \uC2DC\uC791",
                "actionLink": (recommended_modes[0].get("link") if recommended_modes else MODE_LINKS["analysis"]),
                "count": 1,
            }
        )

    return notifications[:4]


def _achieved_dates(history: list[dict[str, Any]], daily_target_sessions: int) -> set[Any]:
    counts: Counter[Any] = Counter()
    for item in history:
        parsed = _parse_history_datetime(item)
        if parsed is None:
            continue
        counts[parsed.date()] += 1

    target = max(int(daily_target_sessions or DEFAULT_DAILY_TARGET_SESSIONS), 1)
    return {date for date, count in counts.items() if count >= target}


def _resume_link(mode: str, item_id: int) -> str:
    return f"{MODE_LINKS.get(mode, '/dashboard.html')}?resume_review={item_id}"


def _mode_from_problem(problem: Problem) -> str:
    problem_payload = problem.problem_payload if isinstance(problem.problem_payload, dict) else {}
    raw_mode = str(problem_payload.get("mode") or "").strip()
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

    external_id = str(problem.external_id or "").strip().lower()
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

    mapping = {
        "analysis": "analysis",
        "code_block": "code-block",
        "code_arrange": "code-arrange",
        "code_calc": "code-calc",
        "code_error": "code-error",
        "auditor": "auditor",
        "context_inference": "context-inference",
        "refactoring_choice": "refactoring-choice",
        "code_blame": "code-blame",
    }
    value = getattr(problem.kind, "value", str(problem.kind))
    return mapping.get(str(value), "analysis")


def _next_review_delay_hours(total_wrong: int) -> int:
    if total_wrong <= 1:
        return 4
    if total_wrong == 2:
        return 24
    if total_wrong == 3:
        return 72
    return 168


def _review_priority(total_wrong: int, wrong_type: str | None) -> int:
    base = min(max(total_wrong, 1) * 10, 80)
    if wrong_type in {"logic_error", "runtime_error", "timeout_error"}:
        base += 10
    return min(base, 100)
