from app.core.config import settings
from app.services.llm.gemini import GeminiProvider, LLMExtractionError
from app.services.llm.mock import MockLLMProvider
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)


def get_llm_provider() -> LLMProvider:
    """Returns configured GeminiProvider if API key is present, otherwise returns MockLLMProvider."""
    if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your-gemini-api-key-here":
        return GeminiProvider()
    return MockLLMProvider()


__all__ = [
    "LLMProvider",
    "EvidenceStatus",
    "ExtractedEvidenceItem",
    "ExtractedEvidenceResult",
    "GeminiProvider",
    "MockLLMProvider",
    "LLMExtractionError",
    "get_llm_provider",
]
