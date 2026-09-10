from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.queue_entry import QueueStatus


class WaitEstimate(BaseModel):
    lower_minutes: int
    expected_minutes: int
    upper_minutes: int
    source: str = "baseline"


class QueueEntryBase(BaseModel):
    appointment_id: str
    patient_id: str
    doctor_id: str
    hospital_id: str
    queue_date: date
    token_number: str
    status: QueueStatus = QueueStatus.WAITING


class QueueEntryCreate(QueueEntryBase):
    pass


class QueueEntryResponse(QueueEntryBase):
    id: str
    checked_in_at: datetime
    called_at: Optional[datetime] = None
    consultation_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientQueueStatusResponse(BaseModel):
    queue_entry_id: str
    appointment_id: str
    doctor_id: str
    hospital_id: str
    token_number: str
    status: QueueStatus
    checked_in_at: datetime
    called_at: Optional[datetime] = None
    consultation_started_at: Optional[datetime] = None
    patients_ahead: int
    wait_estimate: WaitEstimate
