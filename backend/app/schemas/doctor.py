from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.department import DepartmentResponse
from app.schemas.doctor_specialty import DoctorSpecialtyResponse
from app.schemas.hospital import HospitalResponse
from app.schemas.profile import ProfileResponse


class DoctorBase(BaseModel):
    profile_id: str
    hospital_id: str
    department_id: Optional[str] = None
    license_number: str = Field(..., min_length=2, max_length=100)
    years_of_experience: int = Field(default=0, ge=0)
    consultation_mode: str = Field(default="both", max_length=50)
    average_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    rating_count: int = Field(default=0, ge=0)
    languages: str = Field(default="en", max_length=255)
    is_active: bool = True


class DoctorCreate(DoctorBase):
    pass


class DoctorUpdate(BaseModel):
    hospital_id: Optional[str] = None
    department_id: Optional[str] = None
    license_number: Optional[str] = Field(None, min_length=2, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)
    consultation_mode: Optional[str] = None
    average_rating: Optional[float] = Field(None, ge=0.0, le=5.0)
    rating_count: Optional[int] = Field(None, ge=0)
    languages: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class DoctorResponse(DoctorBase):
    id: str
    created_at: datetime
    updated_at: datetime
    profile: ProfileResponse
    hospital: Optional[HospitalResponse] = None
    department: Optional[DepartmentResponse] = None
    specialties: List[DoctorSpecialtyResponse] = []
    invitation_status: Optional[str] = "active"
    is_accepting_patients: bool = True

    model_config = ConfigDict(from_attributes=True)


class DoctorIntakeStatusUpdate(BaseModel):
    is_accepting_patients: bool = Field(
        ...,
        description="Whether the doctor is actively accepting new patient triage intakes at their clinic station",
    )


class DoctorIntakeStatusResponse(BaseModel):
    doctor_id: str
    is_accepting_patients: bool
    status: str
    message: str
