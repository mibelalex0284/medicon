from datetime import date, datetime, time
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.appointment import AppointmentStatus


class AvailableSlot(BaseModel):
    start_time: time
    end_time: time
    is_available: bool = True


class DoctorAvailabilityResponse(BaseModel):
    doctor_id: str
    hospital_id: str
    appointment_date: date
    slot_duration_minutes: int
    has_schedule: bool = Field(default=True, description="Whether doctor has working hours configured on this weekday")
    schedule_configured: bool = Field(default=True, description="Whether doctor has any working schedule configured in the system")
    is_fully_booked: bool = Field(default=False, description="Whether all slots for this day are booked")
    slots: List[AvailableSlot]


class AppointmentBase(BaseModel):
    patient_id: str
    doctor_id: str
    hospital_id: str
    appointment_date: date
    scheduled_start: time
    scheduled_end: time
    appointment_type: str = Field(default="in_person", max_length=50)
    reason: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_time_range(self) -> "AppointmentBase":
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be strictly later than scheduled_start")
        return self


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(BaseModel):
    status: Optional[AppointmentStatus] = None
    reason: Optional[str] = None


class AppointmentResponse(AppointmentBase):
    id: str
    status: AppointmentStatus
    created_at: datetime
    updated_at: datetime
    doctor_name: Optional[str] = None
    doctor_specialty: Optional[str] = None
    department_name: Optional[str] = None
    queue_token: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
