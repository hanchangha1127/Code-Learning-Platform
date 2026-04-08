from __future__ import annotations

from fastapi import APIRouter

from server.features.learning.api_advanced_analysis import router as advanced_analysis_router
from server.features.learning.api_auditor import router as auditor_router
from server.features.learning.api_code_blame import router as code_blame_router
from server.features.learning.api_problems import router as problems_router
from server.features.learning.api_public_learning import router as public_learning_router
from server.features.learning.api_refactoring_choice import router as refactoring_choice_router
from server.features.learning.api_submissions import router as submissions_router

router = APIRouter()
router.include_router(public_learning_router)
router.include_router(advanced_analysis_router)
router.include_router(problems_router, prefix="/problems")
router.include_router(submissions_router)
router.include_router(auditor_router, prefix="/auditor")
router.include_router(refactoring_choice_router, prefix="/refactoring-choice")
router.include_router(code_blame_router, prefix="/code-blame")

