from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import SessionLocal
from app.services import platform_public_bridge
from app.services.platform_mode_observability import observe_platform_mode_operation


def _resolve_username(db: Session, user_id: int) -> str:
    user = db.get(User, int(user_id))
    username = str(getattr(user, "username", "") or "").strip()
    if not username:
        raise ValueError("user_not_found_for_platform_mode_submit")
    return username


def run_platform_mode_submit_background(mode: str, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    db: Session = SessionLocal()
    try:
        normalized_mode = str(mode or "").strip().lower()
        request_id = str(payload.get("request_id") or "").strip() or None
        with observe_platform_mode_operation(
            mode=normalized_mode,
            operation="submit_background",
            user_id=user_id,
            request_id=request_id,
        ):
            if normalized_mode == "auditor":
                return platform_public_bridge.submit_mode_answer(
                    mode=normalized_mode,
                    username=_resolve_username(db, user_id),
                    user_id=user_id,
                    body={
                        "problemId": str(payload.get("problem_id") or ""),
                        "report": str(payload.get("report") or ""),
                    },
                    db=db,
                )

            if normalized_mode == "refactoring-choice":
                return platform_public_bridge.submit_mode_answer(
                    mode=normalized_mode,
                    username=_resolve_username(db, user_id),
                    user_id=user_id,
                    body={
                        "problemId": str(payload.get("problem_id") or ""),
                        "selectedOption": str(payload.get("selected_option") or ""),
                        "report": str(payload.get("report") or ""),
                    },
                    db=db,
                )

            if normalized_mode == "code-blame":
                raw_selected_commits = payload.get("selected_commits")
                selected_commits = []
                if isinstance(raw_selected_commits, list):
                    selected_commits = [str(token or "") for token in raw_selected_commits]
                return platform_public_bridge.submit_mode_answer(
                    mode=normalized_mode,
                    username=_resolve_username(db, user_id),
                    user_id=user_id,
                    body={
                        "problemId": str(payload.get("problem_id") or ""),
                        "selectedCommits": selected_commits,
                        "report": str(payload.get("report") or ""),
                    },
                    db=db,
                )

            if normalized_mode in {"single-file-analysis", "multi-file-analysis", "fullstack-analysis"}:
                return platform_public_bridge.submit_mode_answer(
                    mode=normalized_mode,
                    username=_resolve_username(db, user_id),
                    user_id=user_id,
                    body={
                        "problemId": str(payload.get("problem_id") or ""),
                        "report": str(payload.get("report") or ""),
                    },
                    db=db,
                )

            raise ValueError("unsupported_platform_mode")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
