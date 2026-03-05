from server_runtime.routes.auth import router as auth_router
from server_runtime.routes.health import router as health_router
from server_runtime.routes.learning import router as learning_router
from server_runtime.routes.pages import router as pages_router

__all__ = [
    "auth_router",
    "health_router",
    "learning_router",
    "pages_router",
]
