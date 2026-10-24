import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class PatientProfileCompletionRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255, description="Full legal name of the patient")
    date_of_birth: datetime.date = Field(..., description="Date of birth (YYYY-MM-DD)")
    phone: Optional[str] = Field(None, max_length=50, description="Contact telephone number")
    email: Optional[EmailStr] = Field(None, description="Contact email address (defaults to verified token email)")
    preferred_language: str = Field("en", max_length=10, description="Preferred language code (e.g. en, es, hi)")
    emergency_contact: Optional[str] = Field(None, max_length=100, description="Emergency contact details")
    accessibility_notes: Optional[str] = Field(None, description="Accessibility or accommodation notes")
    hospital_id: Optional[str] = Field(None, description="Optional default hospital association")


class ProfileCompletionResponse(BaseModel):
    status: str = "completed"
    profile_id: str
    patient_id: str
    role: str
    full_name: str
    email: str
    date_of_birth: datetime.date


class AuthMeResponse(BaseModel):
    auth_user_id: str
    has_profile: bool
    role: str
    profile_id: Optional[str] = None
    email: Optional[str] = None
    hospital_id: Optional[str] = None
    is_active: bool = True
