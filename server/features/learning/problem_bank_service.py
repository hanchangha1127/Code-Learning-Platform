from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session

from server.bootstrap import storage_manager
from server.db.models import Problem, ProblemContentStatus, Submission, SubmissionStatus, UserProblemStat
from server.features.learning.catalog import MODE_LABELS, MODE_LINKS, infer_mode_from_problem

SENSITIVE_PROBLEM_KEYS = {
    "answer",
    "answerIndex",
    "answer_index",
    "answer_index_value",
    "answer_order",
    "answerOrder",
    "bestOption",
    "best_option",
    "commitReviews",
    "commit_reviews",
    "correctAnswer",
    "correct_answer",
    "correctAnswerIndex",
    "correct_answer_index",
    "correctOrder",
    "correct_order",
    "culpritCommits",
    "culprit_commits",
    "explanation",
    "modelAnswer",
    "model_answer",
    "optionReviews",
    "option_reviews",
    "referenceReport",
    "reference_report",
    "referenceSolution",
    "reference_solution",
}

MODE_INSTANCE_TYPES = {
    "analysis": "problem_instance",
    "code-block": "code_block_instance",
    "code-arrange": "code_arrange_instance",
    "auditor": "auditor_instance",
    "refactoring-choice": "refactoring_choice_instance",
    "code-blame": "code_blame_instance",
    "single-file-analysis": "single_file_analysis_instance",
    "multi-file-analysis": "multi_file_analysis_instance",
    "fullstack-analysis": "fullstack_analysis_instance",
}


def list_problem_bank(
    db: Session,
    *,
    user_id: int,
    query: str | None = None,
    mode: str | None = None,
    language: str | None = None,
    difficulty: str | None = None,
    my_status: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_mode = str(mode).strip().lower() if mode else None
    normalized_status = str(my_status).strip().lower() if my_status else None

    rows_query = (
        db.query(Problem)
        .filter(_problem_bank_access_condition(user_id=user_id))
        .filter(Problem.content_status != ProblemContentStatus.hidden)
        .filter(Problem.answer_payload.isnot(None))
    )

    if language:
        rows_query = rows_query.filter(Problem.language == language)
    if difficulty:
        rows_query = rows_query.filter(Problem.difficulty == difficulty)
    if query:
        pattern = f"%{query.strip()}%"
        rows_query = rows_query.filter(or_(Problem.title.ilike(pattern), Problem.description.ilike(pattern)))

    if normalized_status in {"solved", "tried", "unsolved"}:
        rows_query = _apply_status_filter(rows_query, user_id=user_id, status=normalized_status)

    ordered_query = rows_query.order_by(Problem.id.desc())
    summary_problems = _collect_visible_problems(ordered_query, mode=normalized_mode)
    total = len(summary_problems)
    page = summary_problems[offset : offset + limit]
    summary_problem_ids = [int(problem.id) for problem in summary_problems]
    stat_by_problem_id = _load_current_user_stats(db, user_id=user_id, problem_ids=summary_problem_ids)
    aggregate_by_problem_id = _load_submission_aggregates(db, problem_ids=summary_problem_ids)

    return {
        "items": [
            _problem_bank_item(
                problem,
                aggregate=aggregate_by_problem_id.get(int(problem.id), {}),
                user_stat=stat_by_problem_id.get(int(problem.id)),
            )
            for problem in page
        ],
        "summary": _problem_bank_summary_from_ids(
            summary_problem_ids,
            aggregate_by_problem_id=aggregate_by_problem_id,
            stat_by_problem_id=stat_by_problem_id,
        ),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def resume_problem_bank_item(db: Session, *, user_id: int, username: str, problem_id: int) -> dict[str, Any]:
    problem = db.get(Problem, problem_id)
    if not _can_resume_problem(db, problem, user_id=user_id):
        raise LookupError("problem_bank_item_not_found")

    assert problem is not None
    mode = _problem_mode(problem)
    if mode not in MODE_LINKS:
        raise LookupError("problem_bank_mode_not_supported")

    _inject_runtime_instance(username=username, problem=problem, mode=mode)
    payload = _safe_problem_payload(problem, mode=mode)
    return {
        "bank_problem_id": int(problem.id),
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "resume_link": f"{MODE_LINKS[mode]}?bank_problem={int(problem.id)}",
        "problem": payload,
    }


def publish_problem_after_submission(problem: Problem) -> None:
    if getattr(problem, "content_status", None) == ProblemContentStatus.hidden:
        return
    if not _has_replay_payload(problem):
        return
    problem.is_published = True


def _is_problem_bank_visible(problem: Problem) -> bool:
    if getattr(problem, "content_status", None) == ProblemContentStatus.hidden:
        return False
    if not _has_replay_payload(problem):
        return False
    return _problem_mode(problem) in MODE_LINKS


def _can_resume_problem(db: Session, problem: Problem | None, *, user_id: int) -> bool:
    if problem is None or not _has_replay_payload(problem):
        return False
    if getattr(problem, "content_status", None) == ProblemContentStatus.hidden:
        return False
    if getattr(problem, "is_published", False):
        return True
    if _has_submission_by_user(db, problem_id=int(problem.id), user_id=user_id):
        return True
    created_by = getattr(problem, "created_by", None)
    try:
        return created_by is not None and int(created_by) == int(user_id)
    except (TypeError, ValueError):
        return False


def _has_replay_payload(problem: Problem) -> bool:
    payload = getattr(problem, "answer_payload", None)
    return isinstance(payload, dict) and bool(payload)


def _collect_visible_problems(query: Any, *, mode: str | None) -> list[Problem]:
    visible: list[Problem] = []
    cursor = 0
    chunk_size = 100
    while True:
        batch = query.offset(cursor).limit(chunk_size).all()
        cursor += len(batch)
        for problem in batch:
            if not _is_problem_bank_visible(problem):
                continue
            if mode is not None and _problem_mode(problem) != mode:
                continue
            visible.append(problem)
        if len(batch) < chunk_size:
            break
    return visible


def _problem_bank_access_condition(*, user_id: int) -> Any:
    return or_(
        Problem.is_published == True,
        Problem.created_by == user_id,
        exists().where(and_(Submission.problem_id == Problem.id, Submission.user_id == user_id)),
    )


def _apply_status_filter(query, *, user_id: int, status: str) -> Any:
    attempts = func.coalesce(UserProblemStat.attempts, 0)
    query = query.outerjoin(
        UserProblemStat,
        and_(UserProblemStat.user_id == user_id, UserProblemStat.problem_id == Problem.id),
    )
    if status == "solved":
        return query.filter(UserProblemStat.best_status == SubmissionStatus.passed)
    if status == "tried":
        return query.filter(
            UserProblemStat.problem_id.isnot(None),
            attempts > 0,
            or_(
                UserProblemStat.best_status.is_(None),
                UserProblemStat.best_status != SubmissionStatus.passed,
            ),
        )
    if status == "unsolved":
        return query.filter(
            or_(UserProblemStat.problem_id.is_(None), attempts <= 0),
        )
    return query


def _has_submission_by_user(db: Session, *, problem_id: int, user_id: int) -> bool:
    return bool(
        db.query(Submission.id)
        .filter(and_(Submission.problem_id == problem_id, Submission.user_id == user_id))
        .first()
    )


def _problem_mode(problem: Problem) -> str:
    problem_payload = problem.problem_payload if isinstance(problem.problem_payload, dict) else {}
    answer_payload = problem.answer_payload if isinstance(problem.answer_payload, dict) else {}
    return str(infer_mode_from_problem(problem=problem, problem_payload=problem_payload, answer_payload=answer_payload)).strip().lower()


def _safe_problem_payload(problem: Problem, *, mode: str) -> dict[str, Any]:
    payload = deepcopy(problem.problem_payload if isinstance(problem.problem_payload, dict) else {})
    payload = _sanitize_problem_payload(payload)
    payload["problemId"] = str(problem.id)
    payload["id"] = str(problem.id)
    payload["mode"] = mode
    payload.setdefault("title", problem.title)
    payload.setdefault("description", problem.description)
    payload.setdefault("language", problem.language)
    payload.setdefault("difficulty", problem.difficulty.value if hasattr(problem.difficulty, "value") else str(problem.difficulty))
    if problem.starter_code and "code" not in payload and "starterCode" not in payload:
        payload["code"] = problem.starter_code
    return payload


def _sanitize_problem_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_problem_payload(item)
            for key, item in value.items()
            if key not in SENSITIVE_PROBLEM_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_problem_payload(item) for item in value]
    return value


def _inject_runtime_instance(*, username: str, problem: Problem, mode: str) -> None:
    instance = deepcopy(problem.answer_payload if isinstance(problem.answer_payload, dict) else {})
    instance.update(
        {
            "type": MODE_INSTANCE_TYPES.get(mode, "problem_instance"),
            "problem_id": str(problem.id),
            "problemId": str(problem.id),
            "mode": mode,
            "title": problem.title,
            "language": problem.language,
            "difficulty": problem.difficulty.value if hasattr(problem.difficulty, "value") else str(problem.difficulty),
        }
    )
    try:
        storage = storage_manager.get_storage(username)
    except FileNotFoundError:
        storage = storage_manager.create_user_storage(username)
    storage.append(instance)


def _problem_bank_item(
    problem: Problem,
    *,
    aggregate: dict[str, int],
    user_stat: UserProblemStat | None,
) -> dict[str, Any]:
    mode = _problem_mode(problem)
    submissions = int(aggregate.get("submissions") or 0)
    passed = int(aggregate.get("passed") or 0)
    success_rate = round((passed / submissions) * 100, 1) if submissions else None
    return {
        "id": int(problem.id),
        "title": problem.title,
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "language": problem.language,
        "difficulty": problem.difficulty.value if hasattr(problem.difficulty, "value") else str(problem.difficulty),
        "submissions": submissions,
        "success_rate": success_rate,
        "my_status": _my_problem_status(user_stat),
        "created_at": problem.created_at,
        "updated_at": problem.updated_at,
        "solve_link": f"{MODE_LINKS.get(mode, '/dashboard.html')}?bank_problem={int(problem.id)}",
    }


def _problem_bank_summary_from_ids(
    problem_ids: list[int],
    *,
    aggregate_by_problem_id: dict[int, dict[str, int]],
    stat_by_problem_id: dict[int, UserProblemStat],
) -> dict[str, Any]:
    total_submissions = 0
    total_passed = 0
    for problem_id in problem_ids:
        aggregate = aggregate_by_problem_id.get(int(problem_id), {})
        total_submissions += int(aggregate.get("submissions") or 0)
        total_passed += int(aggregate.get("passed") or 0)

    statuses = [_my_problem_status(stat) for stat in stat_by_problem_id.values()]
    return {
        "total_problems": len(problem_ids),
        "total_submissions": total_submissions,
        "solved_count": sum(1 for status in statuses if status == "solved"),
        "tried_count": sum(1 for status in statuses if status == "tried"),
        "average_success_rate": round((total_passed / total_submissions) * 100, 1)
        if total_submissions
        else None,
    }


def _load_submission_aggregates(db: Session, problem_ids: list[int]) -> dict[int, dict[str, int]]:
    if not problem_ids:
        return {}
    passed_case = case((Submission.status == SubmissionStatus.passed, 1), else_=0)
    rows = (
        db.query(
            Submission.problem_id,
            func.count(Submission.id),
            func.coalesce(func.sum(passed_case), 0),
        )
        .filter(Submission.problem_id.in_(problem_ids))
        .group_by(Submission.problem_id)
        .all()
    )
    return {
        int(problem_id): {"submissions": int(total or 0), "passed": int(passed or 0)}
        for problem_id, total, passed in rows
    }


def _load_current_user_stats(
    db: Session,
    *,
    user_id: int,
    problem_ids: list[int],
) -> dict[int, UserProblemStat]:
    if not problem_ids:
        return {}
    rows = (
        db.query(UserProblemStat)
        .filter(UserProblemStat.user_id == user_id, UserProblemStat.problem_id.in_(problem_ids))
        .all()
    )
    return {int(row.problem_id): row for row in rows}


def _my_problem_status(stat: UserProblemStat | None) -> str:
    if stat is None or int(stat.attempts or 0) <= 0:
        return "unsolved"
    status = stat.best_status.value if hasattr(stat.best_status, "value") else str(stat.best_status or "")
    if status == SubmissionStatus.passed.value:
        return "solved"
    return "tried"
