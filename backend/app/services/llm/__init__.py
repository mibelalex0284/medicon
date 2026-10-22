from typing import Optional
from app.services.llm.gemini import GeminiProvider, LLMExtractionError, is_diagnostic_claim
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    MeasurementItem,
    LLMProvider,
)

_default_gemini_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """Returns the application-lifetime GeminiProvider for CareRoute-X conversational triage."""
    global _default_gemini_provider
    if _default_gemini_provider is None:
        _default_gemini_provider = GeminiProvider()
    return _default_gemini_provider


def close_llm_provider() -> None:
    """Closes the application-lifetime GeminiProvider and releases resources."""
    global _default_gemini_provider
    if _default_gemini_provider is not None:
        if hasattr(_default_gemini_provider, "close"):
            _default_gemini_provider.close()
        _default_gemini_provider = None


def set_llm_provider(provider: Optional[LLMProvider]) -> None:
    """Sets or resets the application-lifetime LLM provider (useful for testing)."""
    global _default_gemini_provider
    _default_gemini_provider = provider


__all__ = [
    "LLMProvider",
    "EvidenceStatus",
    "ExtractedEvidenceItem",
    "ExtractedEvidenceResult",
    "MeasurementItem",
    "GeminiProvider",
    "LLMExtractionError",
    "get_llm_provider",
    "close_llm_provider",
    "set_llm_provider",
    "is_diagnostic_claim",
]
