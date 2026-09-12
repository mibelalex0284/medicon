from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class ExtractedEvidenceItem(BaseModel):
    """An individual piece of clinical evidence extracted from patient communication."""

    evidence_code: str
    status: EvidenceStatus = EvidenceStatus.PRESENT
    value: Optional[Any] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractedEvidenceResult(BaseModel):
    """Structured clinical extraction payload produced from unstructured patient text."""

    chief_complaint: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=1, le=10)
    measurements: Dict[str, float] = Field(default_factory=dict)
    items: List[ExtractedEvidenceItem] = Field(default_factory=list)


class LLMProvider(Protocol):
    """Protocol defining the required contract for conversational LLM components."""

    def extract_patient_evidence(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> ExtractedEvidenceResult:
        """Extracts structured symptoms, negations, severity, and duration from patient text."""
        ...

    def phrase_question(
        self, controlled_question: str, evidence_id: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Phrases a controlled medical evidence inquiry into empathetic, natural conversational language."""
        ...

    def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """Summarizes dialogue history for clinician handoff."""
        ...
