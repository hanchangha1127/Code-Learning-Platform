from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from server_runtime.context import learning_service, user_service
from server_runtime.deps import get_current_username
from server_runtime.schemas import (
    AuditorSubmitRequest,
    CodeBlameSubmitRequest,
    CodeArrangeSubmitRequest,
    CodeBlockSubmitRequest,
    CodeCalcSubmitRequest,
    CodeErrorSubmitRequest,
    ContextInferenceSubmitRequest,
    DiagnosticStartRequest,
    ExplanationSubmission,
    ProblemRequest,
    RefactoringChoiceSubmitRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _require_username(username: str) -> None:
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다.")


@router.get("/api/tracks")
def list_tracks(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return {"tracks": learning_service.list_tracks()}


@router.get("/api/languages")
def list_languages(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return {"languages": learning_service.list_languages()}


@router.get("/api/profile")
def profile(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return learning_service.get_profile(username)


@router.get("/api/me")
def me(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return user_service.get_user_info(username)


@router.post("/api/diagnostics/start")
def start_diagnostic(
    selection: DiagnosticStartRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_problem(
            username,
            selection.language_id,
            selection.difficulty,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/api/problem/submit")
def submit_explanation(
    submission: ExplanationSubmission,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_explanation(
            username,
            submission.language_id,
            submission.problem_id,
            submission.explanation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_explanation failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-block/problem")
def request_code_block_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_code_block_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_block_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-block/submit")
def submit_code_block_answer(
    submission: CodeBlockSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_block_answer(
            username,
            submission.problem_id,
            submission.selected_option,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_block_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-arrange/problem")
def request_code_arrange_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_code_arrange_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_arrange_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-arrange/submit")
def submit_code_arrange_answer(
    submission: CodeArrangeSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_arrange_answer(
            username,
            submission.problem_id,
            submission.order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_arrange_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-calc/problem")
def request_code_calc_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_code_calc_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_calc_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-calc/submit")
def submit_code_calc_answer(
    submission: CodeCalcSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_calc_answer(
            username,
            submission.problem_id,
            submission.output_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_calc_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-error/problem")
def request_code_error_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_code_error_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_error_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-error/submit")
def submit_code_error_answer(
    submission: CodeErrorSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_error_answer(
            username,
            submission.problem_id,
            submission.selected_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_error_answer failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/auditor/problem")
def request_auditor_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_auditor_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_auditor_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/auditor/submit")
def submit_auditor_report(
    submission: AuditorSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_auditor_report(
            username,
            submission.problem_id,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_auditor_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/context-inference/problem")
def request_context_inference_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_context_inference_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_context_inference_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/context-inference/submit")
def submit_context_inference_report(
    submission: ContextInferenceSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_context_inference_report(
            username,
            submission.problem_id,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_context_inference_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/refactoring-choice/problem")
def request_refactoring_choice_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_refactoring_choice_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_refactoring_choice_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/refactoring-choice/submit")
def submit_refactoring_choice_report(
    submission: RefactoringChoiceSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_refactoring_choice_report(
            username,
            submission.problem_id,
            submission.selected_option,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_refactoring_choice_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-blame/problem")
def request_code_blame_problem(
    payload: ProblemRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.request_code_blame_problem(
            username,
            payload.language_id,
            payload.difficulty_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("request_code_blame_problem failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.post("/api/code-blame/submit")
def submit_code_blame_report(
    submission: CodeBlameSubmitRequest,
    username: str = Depends(get_current_username),
) -> dict:
    _require_username(username)
    try:
        return learning_service.submit_code_blame_report(
            username,
            submission.problem_id,
            submission.selected_commits,
            submission.report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("submit_code_blame_report failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="요청 처리 중 오류가 발생했습니다.") from exc


@router.get("/api/learning/history")
def history(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    events = learning_service.user_history(username)
    return {"history": events}


@router.get("/api/learning/memory")
def memory(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    memo = learning_service.user_memory(username)
    return {"memory": memo}


@router.get("/api/report")
def report(username: str = Depends(get_current_username)) -> dict:
    _require_username(username)
    return learning_service.learning_report(username)
