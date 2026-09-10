from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DoctorScheduleBase(BaseModel):
    doctor_id: str
    hospital_id: str
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(default=15, gt=0, le=120)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_time_range(self) -> "DoctorScheduleBase":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly later than start_time")
        return self


class DoctorScheduleCreate(DoctorScheduleBase):
    pass


class DoctorScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    slot_duration_minutes: Optional[int] = Field(None, gt=0, le=120)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "DoctorScheduleUpdate":
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValueError("end_time must be strictly later than start_time")
        return self


class DoctorScheduleResponse(DoctorScheduleBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
