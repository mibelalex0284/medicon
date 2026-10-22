from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class MeasurementItem(BaseModel):
    """An individual numerical or quantitative measurement (e.g. temperature, blood pressure)."""

    name: str
    value: float
    unit: Optional[str] = None


class ExtractedEvidenceItem(BaseModel):
    """An individual piece of clinical evidence extracted from patient communication."""

    evidence_code: str
    status: EvidenceStatus = EvidenceStatus.PRESENT
    value: Optional[Any] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AdaptiveQuestionStatus(str, Enum):
    ASK = "ask"
    SUFFICIENT = "sufficient"
    UNCERTAIN = "uncertain"
    ESCALATE = "escalate"


class AdaptiveQuestionProposal(BaseModel):
    """Structured question generation proposal produced by the LLM."""

    status: AdaptiveQuestionStatus = AdaptiveQuestionStatus.ASK
    question: Optional[str] = None
    intent: Optional[str] = None
    target_information: List[str] = Field(default_factory=list)
    reason: str = Field(default="")
    safety_flags: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    covered_information: List[str] = Field(default_factory=list)
    requires_human_review: bool = False


class ExtractedEvidenceResult(BaseModel):
    """Structured clinical extraction payload produced from unstructured patient text."""

    chief_complaint: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=1, le=10)
    measurements: List[MeasurementItem] = Field(default_factory=list)
    items: List[ExtractedEvidenceItem] = Field(default_factory=list)
    corrections: List[str] = Field(default_factory=list)
    declined_to_continue: bool = False


class LLMProvider(Protocol):
    """Protocol defining the required contract for conversational LLM components."""

    def extract_patient_evidence(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> ExtractedEvidenceResult:
        """Extracts structured symptoms, negations, severity, and duration from patient text."""
        ...

    def propose_next_question(
        self, context: Dict[str, Any]
    ) -> AdaptiveQuestionProposal:
        """Proposes an adaptive next question or intake completion status based on patient state and information gaps."""
        ...

    def phrase_question(
        self, controlled_question: str, evidence_id: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Phrases a controlled medical evidence inquiry into empathetic, natural conversational language."""
        ...

    def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        """Summarizes dialogue history for clinician handoff."""
        ...

    def close(self) -> None:
        """Closes the provider and releases any underlying connection pools or resources."""
        ...
