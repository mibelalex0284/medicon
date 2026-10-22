from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.triage_assessment import TriageUrgency
from app.models.triage_question import QuestionResponseType
from app.models.triage_session import TriageSessionStatus


class TriageSessionCreate(BaseModel):
    original_input: str = Field(..., min_length=3, max_length=2000)
    language: str = Field(default="en", max_length=10)


class TriageSessionConfirm(BaseModel):
    confirmed_input: str = Field(..., min_length=3, max_length=2000)


class TriageQuestionResponse(BaseModel):
    id: str
    code: str
    question_text: str
    response_type: QuestionResponseType
    category: str
    priority: int

    model_config = ConfigDict(from_attributes=True)


class TriageAnswerCreate(BaseModel):
    question_id: str
    answer_value: str = Field(..., min_length=1, max_length=500)


class TriageAnswerResponse(BaseModel):
    id: str
    question_id: str
    answer_value: str
    answered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TriageAssessmentResponse(BaseModel):
    id: str
    triage_session_id: str
    urgency: TriageUrgency
    confidence: float
    needs_escalation: bool
    red_flag_detected: bool
    red_flag_codes: List[str]
    recommended_specialty_id: Optional[str] = None
    recommended_specialty_name: Optional[str] = None
    rationale: str
    guidance: str
    assessed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TriageSessionResponse(BaseModel):
    id: str
    patient_id: str
    status: TriageSessionStatus
    original_input: str
    confirmed_input: Optional[str] = None
    language: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    assessment: Optional[TriageAssessmentResponse] = None

    model_config = ConfigDict(from_attributes=True)


class TriageMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


class TriageMessageResponse(BaseModel):
    id: str
    session_id: str
    sender: str
    content: str
    turn_index: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SelectedQuestionSummary(BaseModel):
    evidence_id: str
    question_text: str
    data_type: str = "B"
    possible_values: List[str] = []
    category: str = "GENERAL"
    is_antecedent: bool = False
    expected_information_gain: float = 0.0


class TriageConversationalTurnResponse(BaseModel):
    session_id: str
    conversation_turn: int
    is_complete: bool
    stop_reason: Optional[str] = None
    patient_message: str
    assistant_message: str
    extracted_evidences: List[dict] = Field(default_factory=list)
    selected_question: Optional[SelectedQuestionSummary] = None
    completeness_score: float = 0.0
    uncertainty_score: float = 0.0
    safety_flags: List[str] = Field(default_factory=list)
    assessment: Optional[TriageAssessmentResponse] = None

    model_config = ConfigDict(from_attributes=True)


class PreConsultationReportResponse(BaseModel):
    session_id: str
    patient_id: str
    assessed_at: Optional[datetime] = None
    urgency: TriageUrgency
    recommended_specialty_id: Optional[str] = None
    recommended_specialty_name: Optional[str] = None
    chief_complaint: str
    symptom_duration: Optional[str] = None
    patient_reported_severity: Optional[int] = None
    present_symptoms: List[str] = Field(default_factory=list)
    absent_symptoms: List[str] = Field(default_factory=list)
    unknown_symptoms: List[str] = Field(default_factory=list)
    safety_screenings: Dict[str, str] = Field(default_factory=dict)
    conversation_summary: str = ""
    notice: str = (
        "This summary is based on patient-reported intake information. "
        "It is not a diagnosis. Final clinical assessment and diagnostic decisions "
        "remain the responsibility of the treating physician."
    )
    formatted_report: str = ""

    model_config = ConfigDict(from_attributes=True)

