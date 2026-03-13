from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from server_runtime.context import FRONTEND_DIR
from server_runtime.template_renderer import render_template_response
from server_runtime.user_agent import is_mobile_user_agent

router = APIRouter()

APP_DIR = FRONTEND_DIR / "app"
DESKTOP_DIR = FRONTEND_DIR / "desktop"
MOBILE_DIR = FRONTEND_DIR / "mobile"

PAGE_FILES: dict[str, str] = {
    "index": "index.html",
    "dashboard": "dashboard.html",
    "profile": "profile.html",
    "analysis": "analysis.html",
    "codeblock": "codeblock.html",
    "arrange": "arrange.html",
    "codecalc": "codecalc.html",
    "codeerror": "codeerror.html",
    "auditor": "auditor.html",
    "context-inference": "context-inference.html",
    "refactoring-choice": "refactoring-choice.html",
    "code-blame": "code-blame.html",
}


def _variant_for_request(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "")
    return "mobile" if is_mobile_user_agent(user_agent) else "desktop"


def _template_path(page_key: str, *, variant: str) -> Path:
    directory = MOBILE_DIR if variant == "mobile" else DESKTOP_DIR
    return directory / PAGE_FILES[page_key]


def _render_template(template_path: Path, *, variant: str) -> Response:
    return render_template_response(
        template_path,
        frontend_dir=FRONTEND_DIR,
        template_variant=variant,
        vary_user_agent=True,
    )


def _render_page_or_404(request: Request, page_key: str, *, detail: str) -> Response:
    variant = _variant_for_request(request)
    template_path = _template_path(page_key, variant=variant)
    if not template_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return _render_template(template_path, variant=variant)


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/", include_in_schema=False)
def root(request: Request) -> Response:
    variant = _variant_for_request(request)
    template_path = _template_path("index", variant=variant)
    if template_path.exists():
        return _render_template(template_path, variant=variant)

    return JSONResponse(
        {
            "message": "프런트엔드 파일을 찾을 수 없어 API 모드로 실행 중입니다.",
            "docs": "/docs",
            "health": "/health",
        }
    )


@router.get("/index.html", include_in_schema=False)
def index_page(request: Request) -> Response:
    return _render_page_or_404(request, "index", detail="Index page not found")


@router.get("/app.html", include_in_schema=False)
def app_page() -> Response:
    return RedirectResponse(url="/dashboard.html", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/dashboard.html", include_in_schema=False)
def dashboard_page(request: Request) -> Response:
    return _render_page_or_404(request, "dashboard", detail="Dashboard page not found")


@router.get("/profile.html", include_in_schema=False)
def profile_page(request: Request) -> Response:
    return _render_page_or_404(request, "profile", detail="Profile page not found")


@router.get("/analysis.html", include_in_schema=False)
def analysis_page(request: Request) -> Response:
    return _render_page_or_404(request, "analysis", detail="Analysis page not found")


@router.get("/codeblock.html", include_in_schema=False)
def codeblock_page(request: Request) -> Response:
    return _render_page_or_404(request, "codeblock", detail="Codeblock page not found")


@router.get("/arrange.html", include_in_schema=False)
def arrange_page(request: Request) -> Response:
    return _render_page_or_404(request, "arrange", detail="Arrange page not found")


@router.get("/codecalc.html", include_in_schema=False)
def codecalc_page(request: Request) -> Response:
    return _render_page_or_404(request, "codecalc", detail="Codecalc page not found")


@router.get("/codeerror.html", include_in_schema=False)
def codeerror_page(request: Request) -> Response:
    return _render_page_or_404(request, "codeerror", detail="Codeerror page not found")


@router.get("/auditor.html", include_in_schema=False)
def auditor_page(request: Request) -> Response:
    return _render_page_or_404(request, "auditor", detail="Auditor page not found")


@router.get("/context-inference.html", include_in_schema=False)
def context_inference_page(request: Request) -> Response:
    return _render_page_or_404(request, "context-inference", detail="Context inference page not found")


@router.get("/refactoring-choice.html", include_in_schema=False)
def refactoring_choice_page(request: Request) -> Response:
    return _render_page_or_404(request, "refactoring-choice", detail="Refactoring choice page not found")


@router.get("/code-blame.html", include_in_schema=False)
def code_blame_page(request: Request) -> Response:
    return _render_page_or_404(request, "code-blame", detail="Code blame page not found")
