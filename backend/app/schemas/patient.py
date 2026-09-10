from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.profile import ProfileResponse


class PatientBase(BaseModel):
    profile_id: str
    date_of_birth: date
    preferred_language: str = Field(default="en", max_length=10)
    emergency_contact: Optional[str] = Field(None, max_length=100)
    accessibility_notes: Optional[str] = None


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    date_of_birth: Optional[date] = None
    preferred_language: Optional[str] = Field(None, max_length=10)
    emergency_contact: Optional[str] = None
    accessibility_notes: Optional[str] = None


class PatientResponse(PatientBase):
    id: str
    created_at: datetime
    updated_at: datetime
    profile: ProfileResponse

    model_config = ConfigDict(from_attributes=True)
