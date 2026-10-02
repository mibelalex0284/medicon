from app.services.llm.gemini import GeminiProvider, LLMExtractionError, is_diagnostic_claim
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    MeasurementItem,
    LLMProvider,
)


def get_llm_provider() -> LLMProvider:
    """Returns the production GeminiProvider for CareRoute-X conversational triage."""
    return GeminiProvider()


__all__ = [
    "LLMProvider",
    "EvidenceStatus",
    "ExtractedEvidenceItem",
    "ExtractedEvidenceResult",
    "MeasurementItem",
    "GeminiProvider",
    "LLMExtractionError",
    "get_llm_provider",
    "is_diagnostic_claim",
]
