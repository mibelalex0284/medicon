from datetime import datetime
from typing import List, Optional
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
