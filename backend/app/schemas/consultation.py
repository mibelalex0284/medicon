from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.consultation import ConsultationStatus


class ConsultationBase(BaseModel):
    queue_entry_id: str
    appointment_id: str
    patient_id: str
    doctor_id: str
    hospital_id: str


class ConsultationCreate(ConsultationBase):
    pass


class ConsultationNotesUpdate(BaseModel):
    clinical_notes: Optional[str] = None
    diagnosis: Optional[str] = None
    prescriptions: Optional[str] = None
    follow_up_instructions: Optional[str] = None


class ConsultationResponse(ConsultationBase):
    id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: ConsultationStatus
    duration_seconds: Optional[int] = None
    clinical_notes: Optional[str] = None
    diagnosis: Optional[str] = None
    prescriptions: Optional[str] = None
    follow_up_instructions: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    token_number: Optional[str] = None
    chief_complaint: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

