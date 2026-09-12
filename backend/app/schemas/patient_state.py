from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
from app.models.triage_session import TriageSessionStatus


class CandidateCondition(BaseModel):
    condition: str
    probability: float
    severity: int = 1


class PatientState(BaseModel):
    """Authoritative in-memory / reconstructed clinical and trajectory state

    for a conversational triage session.
    """

    session_id: str
    patient_id: str
    conversation_turn: int = 0
    status: TriageSessionStatus = TriageSessionStatus.IN_PROGRESS

    # Clinical Evidence
    chief_complaint: str = ""
    known_present_evidence: Dict[str, Any] = Field(default_factory=dict)
    known_absent_evidence: List[str] = Field(default_factory=list)
    unknown_evidence: List[str] = Field(default_factory=list)

    # Presentation Nuance
    symptom_duration: Optional[str] = None
    symptom_severity: Optional[int] = None
    measurements: Dict[str, float] = Field(default_factory=dict)

    # Dynamic Differential & Uncertainty
    candidate_conditions: List[CandidateCondition] = Field(default_factory=list)
    uncertainty_score: float = 1.0

    # Deterministic Safety Flags
    safety_flags: List[str] = Field(default_factory=list)
    emergency_detected: bool = False

    # Trajectory
    questions_asked: List[str] = Field(default_factory=list)

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

    def mark_present(self, evidence_id: str, value: Any = True) -> None:
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

    def mark_absent(self, evidence_id: str) -> None:
        base_id = evidence_id.split("_@_")[0]
        if base_id not in self.known_absent_evidence:
            self.known_absent_evidence.append(base_id)
        self.known_present_evidence.pop(base_id, None)
        self.known_present_evidence.pop(evidence_id, None)
        if base_id in self.unknown_evidence:
            self.unknown_evidence.remove(base_id)
        if evidence_id in self.unknown_evidence:
            self.unknown_evidence.remove(evidence_id)

    def mark_unknown(self, evidence_id: str) -> None:
        base_id = evidence_id.split("_@_")[0]
        if base_id not in self.unknown_evidence:
            self.unknown_evidence.append(base_id)
        self.known_present_evidence.pop(base_id, None)
        self.known_present_evidence.pop(evidence_id, None)
        if base_id in self.known_absent_evidence:
            self.known_absent_evidence.remove(base_id)
        if evidence_id in self.known_absent_evidence:
            self.known_absent_evidence.remove(evidence_id)

    def record_question_asked(self, evidence_id: str) -> None:
        base_id = evidence_id.split("_@_")[0]
        if base_id not in self.questions_asked:
            self.questions_asked.append(base_id)
        if evidence_id not in self.questions_asked:
            self.questions_asked.append(evidence_id)
