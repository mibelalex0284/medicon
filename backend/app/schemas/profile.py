from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.profile import UserRole


class ProfileBase(BaseModel):
    role: UserRole
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    email: EmailStr
    hospital_id: Optional[str] = None
    is_active: bool = True


class ProfileCreate(ProfileBase):
    auth_user_id: str = Field(..., min_length=1, max_length=128)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    hospital_id: Optional[str] = None
    is_active: Optional[bool] = None


class ProfileResponse(ProfileBase):
    id: str
    auth_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
