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


class ConsultationResponse(ConsultationBase):
    id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: ConsultationStatus
    duration_seconds: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
