from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.doctor import DoctorResponse


class DoctorRecommendationRequest(BaseModel):
    """Payload for requesting explainable doctor recommendations."""

    hospital_id: Optional[str] = Field(
        None, description="Target hospital ID. If omitted, derived from patient context."
    )
    specialty_id: Optional[str] = Field(
        None, description="Direct clinical specialty ID to match."
    )
    triage_session_id: Optional[str] = Field(
        None, description="Associated completed triage session ID to derive recommended specialty."
    )
    consultation_mode: Optional[str] = Field(
        None, description="Requested mode: 'in_person', 'teleconsultation', or 'both'."
    )
    appointment_date: Optional[date] = Field(
        None, description="Target appointment date for availability checking (YYYY-MM-DD)."
    )
    preferred_doctor_id: Optional[str] = Field(
        None, description="Explicit patient preferred doctor ID (optional)."
    )
    preferred_language: Optional[str] = Field(
        None, description="Explicit patient language code (e.g., 'en', 'es', 'hi')."
    )
    require_availability: bool = Field(
        default=False,
        description="If True, only doctors with open appointment slots on target date are eligible.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of recommendations to return.",
    )


class RecommendationFactorBreakdown(BaseModel):
    """Structured internal representation of calculated ranking factors."""

    specialty_match: bool
    specialty_is_primary: bool
    specialty_score: float

    has_available_slots: bool
    available_slot_count: int
    availability_score: float

    estimated_wait_minutes: int
    wait_score: float

    years_of_experience: int
    experience_score: float

    average_rating: float
    rating_count: int
    rating_reliability_score: float

    preference_match: bool
    preference_score: float

    language_match: bool
    language_score: float

    raw_weights: Dict[str, float] = {}

    model_config = ConfigDict(from_attributes=True)


class DoctorRecommendationItem(BaseModel):
    """Individual ranked doctor recommendation with explainability payload."""

    doctor_id: str
    rank: int
    score: float = Field(..., description="Normalized composite recommendation score [0.0, 1.0].")
    estimated_wait_minutes: int
    consultation_mode: str
    matched_factors: List[str] = Field(
        ..., description="List of positive contributing factor keys."
    )
    explanation: str = Field(
        ..., description="Deterministic, human-readable operational justification."
    )
    doctor: DoctorResponse
    factor_breakdown: RecommendationFactorBreakdown

    model_config = ConfigDict(from_attributes=True)


class DoctorRecommendationResponse(BaseModel):
    """Overall response payload for doctor recommendations."""

    recommendations: List[DoctorRecommendationItem]
    status: str = Field(
        ..., description="Operational status code: 'SUCCESS', 'NO_ELIGIBLE_DOCTORS', or 'EMERGENCY_ESCALATION'."
    )
    message: str
    applied_specialty_id: Optional[str] = None
    applied_specialty_name: Optional[str] = None
    applied_hospital_id: str
    total_eligible_doctors: int
    is_emergency_escalation: bool = False
    escalation_notice: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
