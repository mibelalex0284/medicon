from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.schemas.specialty import SpecialtyResponse


class DoctorSpecialtyBase(BaseModel):
    doctor_id: str
    specialty_id: str
    is_primary: bool = False


class DoctorSpecialtyCreate(DoctorSpecialtyBase):
    pass


class DoctorSpecialtyResponse(DoctorSpecialtyBase):
    id: str
    created_at: datetime
    specialty: SpecialtyResponse

    model_config = ConfigDict(from_attributes=True)
