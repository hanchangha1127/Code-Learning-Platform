import logging

from server.core.config import settings
from .mock import MockAIProvider
from .openai_provider import OpenAIProvider
from .platform_mode_bridge import get_platform_mode_ai_bridge

logger = logging.getLogger(__name__)


def get_provider():
    provider = (settings.AI_PROVIDER or "mock").strip().lower()

    if provider == "openai":
        key = settings.RESOLVED_AI_API_KEY
        if not key:
            logger.warning("AI_PROVIDER=openai but API key is missing; falling back to mock provider.")
            return MockAIProvider()
        return OpenAIProvider(
            api_key=key,
            model=settings.OPENAI_MODEL,
            timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
        )

    return MockAIProvider()


__all__ = ["get_provider", "get_platform_mode_ai_bridge"]

