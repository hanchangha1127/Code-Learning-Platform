from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import SubmissionStatus, UserProblemStat


def _normalize_status(status: SubmissionStatus | str) -> SubmissionStatus:
    if isinstance(status, SubmissionStatus):
        return status
    try:
        return SubmissionStatus(str(status))
    except ValueError:
        return SubmissionStatus.error


def _stringify_detail(detail: Any) -> str:
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    return str(detail)


def _classify_wrong_answer_type(
    status: SubmissionStatus,
    analysis_summary: str | None,
    analysis_detail: Any,
) -> str | None:
    if status == SubmissionStatus.passed:
        return None

    text = f"{analysis_summary or ''} {_stringify_detail(analysis_detail)}".lower()

    if any(token in text for token in ("syntaxerror", "syntax error", "indentationerror", "invalid syntax", "parse error")):
        return "syntax_error"

    if any(token in text for token in ("timeout", "timed out", "time limit", "tle")):
        return "timeout_error"

    if any(
        token in text
        for token in (
            "runtimeerror",
            "runtime error",
            "exception",
            "traceback",
            "indexerror",
            "keyerror",
            "typeerror",
            "valueerror",
            "nullpointer",
            "segmentation fault",
        )
    ):
        return "runtime_error"

    if any(token in text for token in ("wrong answer", "assert", "expected", "actual", "test case", "failed test")):
        return "logic_error"

    if status == SubmissionStatus.error:
        return "analysis_error"

    return "unknown_error"


def _normalize_wrong_answer_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"total_wrong": 0, "types": {}}

    raw_types = payload.get("types")
    normalized_types: dict[str, int] = {}
    if isinstance(raw_types, dict):
        for key, value in raw_types.items():
            if not isinstance(key, str):
                continue
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                continue
            if ivalue > 0:
                normalized_types[key] = ivalue

    try:
        total_wrong = int(payload.get("total_wrong", 0))
    except (TypeError, ValueError):
        total_wrong = 0

    return {
        "total_wrong": max(total_wrong, 0),
        "types": normalized_types,
        "last_wrong_type": payload.get("last_wrong_type") if isinstance(payload.get("last_wrong_type"), str) else None,
        "last_wrong_at": payload.get("last_wrong_at") if isinstance(payload.get("last_wrong_at"), str) else None,
    }


def update_user_problem_stat(
    db: Session,
    user_id: int,
    problem_id: int,
    score: int | None,
    status: SubmissionStatus | str,
    *,
    analysis_summary: str | None = None,
    analysis_detail: Any = None,
    increment_attempt: bool = False,
) -> None:
    stat = db.get(UserProblemStat, (user_id, problem_id))
    if not stat:
        stat = UserProblemStat(
            user_id=user_id,
            problem_id=problem_id,
            attempts=0,
        )
        db.add(stat)
        # Ensure subsequent calls in the same transaction see this row.
        db.flush()

    if increment_attempt:
        stat.attempts += 1

    now = datetime.utcnow()
    stat.last_submitted_at = now

    normalized_status = _normalize_status(status)

    if score is not None and (stat.best_score is None or score > stat.best_score):
        stat.best_score = score
        stat.best_status = normalized_status
    elif stat.best_status is None:
        stat.best_status = normalized_status

    wrong_type = _classify_wrong_answer_type(
        normalized_status,
        analysis_summary=analysis_summary,
        analysis_detail=analysis_detail,
    )
    if not wrong_type:
        return

    payload = _normalize_wrong_answer_payload(stat.wrong_answer_types)
    type_map = payload["types"]
    type_map[wrong_type] = int(type_map.get(wrong_type, 0)) + 1
    payload["total_wrong"] = int(payload.get("total_wrong", 0)) + 1
    payload["last_wrong_type"] = wrong_type
    payload["last_wrong_at"] = now.isoformat()
    stat.wrong_answer_types = payload

