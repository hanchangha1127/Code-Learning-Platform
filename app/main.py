from fastapi import FastAPI, Request

from app.api.routes.auth import router as auth_router
from app.api.routes.advanced_analysis import router as advanced_analysis_router
from app.api.routes.auditor import router as auditor_router
from app.api.routes.code_blame import router as code_blame_router
from app.api.routes.health import router as health_router
from app.api.routes.me import router as me_router
from app.api.routes.platform_mode_jobs import router as platform_mode_jobs_router
from app.api.routes.problems import router as problems_router
from app.api.routes.public_learning import router as public_learning_router
from app.api.routes.refactoring_choice import router as refactoring_choice_router
from app.api.routes.reports import router as reports_router
from app.api.routes.submissions import router as submissions_router
from app.core.request_context import ensure_request_id, set_request_id

app = FastAPI(title="code-platform")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    set_request_id(request.headers.get("x-request-id"))
    request_id = ensure_request_id()
    try:
        response = await call_next(request)
    finally:
        set_request_id(None)
    response.headers["X-Request-Id"] = request_id
    return response


app.include_router(health_router)
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(me_router, prefix="/me", tags=["me"])
app.include_router(public_learning_router, tags=["public-learning"])
app.include_router(advanced_analysis_router, tags=["advanced-analysis"])

app.include_router(problems_router, prefix="/problems", tags=["problems"])
app.include_router(submissions_router, tags=["submissions"])
app.include_router(reports_router, tags=["reports"])
app.include_router(auditor_router, prefix="/auditor", tags=["auditor"])
app.include_router(refactoring_choice_router, prefix="/refactoring-choice", tags=["refactoring-choice"])
app.include_router(code_blame_router, prefix="/code-blame", tags=["code-blame"])
app.include_router(platform_mode_jobs_router, prefix="/mode-jobs", tags=["mode-jobs"])
