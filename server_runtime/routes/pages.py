from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from server_runtime.context import (
    ANALYSIS_FILE,
    AUDITOR_FILE,
    ARRANGE_FILE,
    CONTEXT_INFERENCE_FILE,
    CODEBLOCK_FILE,
    CODECALC_FILE,
    CODEERROR_FILE,
    DASHBOARD_FILE,
    INDEX_FILE,
    PROFILE_FILE,
    REFACTORING_CHOICE_FILE,
    CODE_BLAME_FILE,
)

router = APIRouter()


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/", include_in_schema=False)
def root() -> Response:
    if INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE), media_type="text/html; charset=utf-8")

    return JSONResponse(
        {
            "message": "프런트엔드 파일을 찾을 수 없어 API 모드로 실행 중입니다.",
            "docs": "/docs",
            "health": "/health",
        }
    )


@router.get("/index.html", include_in_schema=False)
def index_page() -> Response:
    if INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Index page not found")


@router.get("/app.html", include_in_schema=False)
def app_page() -> Response:
    return RedirectResponse(url="/dashboard.html", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/dashboard.html", include_in_schema=False)
def dashboard_page() -> Response:
    if DASHBOARD_FILE.exists():
        return FileResponse(str(DASHBOARD_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard page not found")


@router.get("/profile.html", include_in_schema=False)
def profile_page() -> Response:
    if PROFILE_FILE.exists():
        return FileResponse(str(PROFILE_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile page not found")


@router.get("/analysis.html", include_in_schema=False)
def analysis_page() -> Response:
    if ANALYSIS_FILE.exists():
        return FileResponse(str(ANALYSIS_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis page not found")


@router.get("/codeblock.html", include_in_schema=False)
def codeblock_page() -> Response:
    if CODEBLOCK_FILE.exists():
        return FileResponse(str(CODEBLOCK_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Codeblock page not found")


@router.get("/arrange.html", include_in_schema=False)
def arrange_page() -> Response:
    if ARRANGE_FILE.exists():
        return FileResponse(str(ARRANGE_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arrange page not found")


@router.get("/codecalc.html", include_in_schema=False)
def codecalc_page() -> Response:
    if CODECALC_FILE.exists():
        return FileResponse(str(CODECALC_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Codecalc page not found")


@router.get("/codeerror.html", include_in_schema=False)
def codeerror_page() -> Response:
    if CODEERROR_FILE.exists():
        return FileResponse(str(CODEERROR_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Codeerror page not found")


@router.get("/auditor.html", include_in_schema=False)
def auditor_page() -> Response:
    if AUDITOR_FILE.exists():
        return FileResponse(str(AUDITOR_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditor page not found")


@router.get("/context-inference.html", include_in_schema=False)
def context_inference_page() -> Response:
    if CONTEXT_INFERENCE_FILE.exists():
        return FileResponse(str(CONTEXT_INFERENCE_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context inference page not found")


@router.get("/refactoring-choice.html", include_in_schema=False)
def refactoring_choice_page() -> Response:
    if REFACTORING_CHOICE_FILE.exists():
        return FileResponse(str(REFACTORING_CHOICE_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refactoring choice page not found")


@router.get("/code-blame.html", include_in_schema=False)
def code_blame_page() -> Response:
    if CODE_BLAME_FILE.exists():
        return FileResponse(str(CODE_BLAME_FILE), media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code blame page not found")
