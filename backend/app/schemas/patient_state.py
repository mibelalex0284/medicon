from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, model_validator
from app.models.triage_session import TriageSessionStatus
from app.services.llm.provider import EvidenceStatus


class SymptomObservation(BaseModel):
    """Structured clinical observation of a symptom or risk factor reported during triage."""

    code: str
    name: str = ""
    status: EvidenceStatus
    value: Any = True
    confidence: float = 1.0
    category: str = "GENERAL"
    source_message_id: Optional[str] = None


class PatientState(BaseModel):
    """Authoritative in-memory / reconstructed clinical and intake interview state

    for a conversational triage session. Focuses strictly on patient-reported information
    and clinical observation without predicting or diagnosing diseases.
    """

    session_id: str
    patient_id: str
    conversation_turn: int = 0
    status: TriageSessionStatus = TriageSessionStatus.IN_PROGRESS

    # Clinical Intake & Presentation
    chief_complaint: str = ""
    symptom_duration: Optional[str] = None
    symptom_severity: Optional[int] = None  # 1-10 scale
    functional_impact: Optional[str] = None
    measurements: Dict[str, float] = Field(default_factory=dict)

    # Structured Observations
    observations: Dict[str, SymptomObservation] = Field(default_factory=dict)

    # Structured collections for fast lookup and backward compatibility
    known_present_evidence: Dict[str, Any] = Field(default_factory=dict)
    known_absent_evidence: List[str] = Field(default_factory=list)
    unknown_evidence: List[str] = Field(default_factory=list)

    # Deterministic Safety Screening
    safety_screenings: Dict[str, bool] = Field(default_factory=dict)
    safety_flags: List[str] = Field(default_factory=list)
    emergency_detected: bool = False

    # Interview Completeness Tracking
    interview_completed: bool = False
    completeness_score: float = 0.0
    requires_human_review: bool = False
    declined_to_continue: bool = False
    stopping_reason: Optional[str] = None

    # Trajectory & Provenance
    questions_asked: List[str] = Field(default_factory=list)
    unanswered_questions: List[str] = Field(default_factory=list)
    corrections: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)

    def __init__(self, **data: Any):
        if "patient_reported_severity" in data and "symptom_severity" not in data:
            data["symptom_severity"] = data.pop("patient_reported_severity")
        super().__init__(**data)

    def record_correction(self, note: str) -> None:
        if note and note not in self.corrections:
            self.corrections.append(note)

    def record_contradiction(self, note: str) -> None:
        if note and note not in self.contradictions:
            self.contradictions.append(note)

    def record_unanswered_question(self, question_text: str) -> None:
        if question_text and question_text not in self.unanswered_questions:
            self.unanswered_questions.append(question_text)

    @property
    def patient_reported_severity(self) -> Optional[int]:
        return self.symptom_severity

    @patient_reported_severity.setter
    def patient_reported_severity(self, val: Optional[int]) -> None:
        self.symptom_severity = val

    def is_known(self, evidence_id: str) -> bool:
        base_id = evidence_id.split("_@_")[0]
        return (
            base_id in self.known_present_evidence
            or evidence_id in self.known_present_evidence
            or any(k.startswith(f"{base_id}_@_") for k in self.known_present_evidence)
            or base_id in self.known_absent_evidence
            or evidence_id in self.known_absent_evidence
            or any(k.startswith(f"{base_id}_@_") for k in self.known_absent_evidence)
            or base_id in self.unknown_evidence
            or evidence_id in self.unknown_evidence
            or any(k.startswith(f"{base_id}_@_") for k in self.unknown_evidence)
        )

    def mark_present(
        self,
        evidence_id: str,
        value: Any = True,
        name: str = "",
        category: str = "GENERAL",
        confidence: float = 1.0,
        source_message_id: Optional[str] = None,
    ) -> None:
        base_id = evidence_id.split("_@_")[0]
        self.known_present_evidence[evidence_id] = value
        if base_id in self.known_absent_evidence:
            self.known_absent_evidence.remove(base_id)
        if evidence_id in self.known_absent_evidence:
            self.known_absent_evidence.remove(evidence_id)
        if base_id in self.unknown_evidence:
            self.unknown_evidence.remove(base_id)
        if evidence_id in self.unknown_evidence:
            self.unknown_evidence.remove(evidence_id)

        self.observations[evidence_id] = SymptomObservation(
            code=evidence_id,
            name=name,
            status=EvidenceStatus.PRESENT,
            value=value,
            confidence=confidence,
            category=category,
            source_message_id=source_message_id,
        )

    def mark_absent(
        self,
        evidence_id: str,
        name: str = "",
        category: str = "GENERAL",
        confidence: float = 1.0,
        source_message_id: Optional[str] = None,
    ) -> None:
        base_id = evidence_id.split("_@_")[0]
        if base_id not in self.known_absent_evidence:
            self.known_absent_evidence.append(base_id)
        if evidence_id not in self.known_absent_evidence:
            self.known_absent_evidence.append(evidence_id)

        # Clean up any present evidence matching base_id or compound subcodes
        keys_to_pop = [
            k for k in self.known_present_evidence
            if k == base_id or k == evidence_id or k.startswith(f"{base_id}_@_")
        ]
        for k in keys_to_pop:
            self.known_present_evidence.pop(k, None)
            if k in self.observations:
                self.observations[k].status = EvidenceStatus.ABSENT

        if base_id in self.unknown_evidence:
            self.unknown_evidence.remove(base_id)
        if evidence_id in self.unknown_evidence:
            self.unknown_evidence.remove(evidence_id)

        self.observations[evidence_id] = SymptomObservation(
            code=evidence_id,
            name=name,
            status=EvidenceStatus.ABSENT,
            value=False,
            confidence=confidence,
            category=category,
            source_message_id=source_message_id,
        )

    def mark_unknown(
        self,
        evidence_id: str,
        name: str = "",
        category: str = "GENERAL",
        confidence: float = 1.0,
        source_message_id: Optional[str] = None,
    ) -> None:
        base_id = evidence_id.split("_@_")[0]
        if base_id not in self.unknown_evidence:
            self.unknown_evidence.append(base_id)
        if evidence_id not in self.unknown_evidence:
            self.unknown_evidence.append(evidence_id)

        # Clean up any present evidence matching base_id or compound subcodes
        keys_to_pop = [
            k for k in self.known_present_evidence
            if k == base_id or k == evidence_id or k.startswith(f"{base_id}_@_")
        ]
        for k in keys_to_pop:
            self.known_present_evidence.pop(k, None)
            if k in self.observations:
                self.observations[k].status = EvidenceStatus.UNKNOWN

        if base_id in self.known_absent_evidence:
            self.known_absent_evidence.remove(base_id)
        if evidence_id in self.known_absent_evidence:
            self.known_absent_evidence.remove(evidence_id)

        self.observations[evidence_id] = SymptomObservation(
            code=evidence_id,
            name=name,
            status=EvidenceStatus.UNKNOWN,
            value=None,
            confidence=confidence,
            category=category,
            source_message_id=source_message_id,
        )

    def record_question_asked(self, evidence_id: str) -> None:
        base_id = evidence_id.split("_@_")[0]
        if base_id not in self.questions_asked:
            self.questions_asked.append(base_id)
        if evidence_id not in self.questions_asked:
            self.questions_asked.append(evidence_id)
