from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse, RedirectResponse

from server.bootstrap import FRONTEND_DIR
from server.features.runtime_ui.template_renderer import render_template_response

router = APIRouter()


def _render_react_app(*, detail: str, template_variant: str = "react") -> Response:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return render_template_response(
        index_path,
        frontend_dir=FRONTEND_DIR,
        template_variant=template_variant,
        vary_user_agent=False,
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/favicon.svg", include_in_schema=False)
def favicon_svg() -> Response:
    icon_path = FRONTEND_DIR / "favicon.svg"
    if not icon_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favicon not found")
    return FileResponse(icon_path)


@router.get("/icons.svg", include_in_schema=False)
def icons_svg() -> Response:
    icons_path = FRONTEND_DIR / "icons.svg"
    if not icons_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Icons not found")
    return FileResponse(icons_path)


@router.get("/", include_in_schema=False)
def root() -> Response:
    return _render_react_app(detail="React app not found")


@router.get("/index.html", include_in_schema=False)
@router.get("/index", include_in_schema=False)
@router.get("/login", include_in_schema=False)
def index_page() -> Response:
    return _render_react_app(detail="Index page not found")


@router.get("/app.html", include_in_schema=False)
def app_page() -> Response:
    return RedirectResponse(url="/dashboard.html", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/dashboard.html", include_in_schema=False)
@router.get("/dashboard", include_in_schema=False)
def dashboard_page() -> Response:
    return _render_react_app(detail="Dashboard page not found")


@router.get("/profile.html", include_in_schema=False)
@router.get("/profile", include_in_schema=False)
def profile_page() -> Response:
    return _render_react_app(detail="Profile page not found")


@router.get("/problems.html", include_in_schema=False)
@router.get("/problems", include_in_schema=False)
def problems_page() -> Response:
    return _render_react_app(detail="Problems page not found")


@router.get("/analysis.html", include_in_schema=False)
@router.get("/analysis", include_in_schema=False)
def analysis_page() -> Response:
    return _render_react_app(detail="Analysis page not found")


@router.get("/codeblock.html", include_in_schema=False)
@router.get("/codeblock", include_in_schema=False)
@router.get("/code-block", include_in_schema=False)
def codeblock_page() -> Response:
    return _render_react_app(detail="Codeblock page not found")


@router.get("/arrange.html", include_in_schema=False)
@router.get("/arrange", include_in_schema=False)
def arrange_page() -> Response:
    return _render_react_app(detail="Arrange page not found")


@router.get("/auditor.html", include_in_schema=False)
@router.get("/auditor", include_in_schema=False)
def auditor_page() -> Response:
    return _render_react_app(detail="Auditor page not found")


@router.get("/refactoring-choice.html", include_in_schema=False)
@router.get("/refactoring-choice", include_in_schema=False)
def refactoring_choice_page() -> Response:
    return _render_react_app(detail="Refactoring choice page not found")


@router.get("/code-blame.html", include_in_schema=False)
@router.get("/code-blame", include_in_schema=False)
def code_blame_page() -> Response:
    return _render_react_app(detail="Code blame page not found")


@router.get("/single-file-analysis.html", include_in_schema=False)
@router.get("/single-file-analysis", include_in_schema=False)
def single_file_analysis_page() -> Response:
    return _render_react_app(detail="Single file analysis page not found")


@router.get("/multi-file-analysis.html", include_in_schema=False)
@router.get("/multi-file-analysis", include_in_schema=False)
def multi_file_analysis_page() -> Response:
    return _render_react_app(detail="Multi file analysis page not found")


@router.get("/fullstack-analysis.html", include_in_schema=False)
@router.get("/fullstack-analysis", include_in_schema=False)
def fullstack_analysis_page() -> Response:
    return _render_react_app(detail="Fullstack analysis page not found")
