import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegistrationStatusResponse(BaseModel):
    """Public read-only response indicating if patient self-registration is enabled."""
    patient_self_registration_enabled: bool = Field(
        ...,
        description="True if public patient self-registration is currently allowed",
    )


class AdminSettingItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None
    updated_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdminSettingsResponse(BaseModel):
    patient_self_registration_enabled: bool
    settings: List[AdminSettingItem] = []


class UpdatePatientSelfRegistrationRequest(BaseModel):
    enabled: bool = Field(
        ...,
        description="Set to true to allow public patient self-registration, false to disable",
    )


class AdminCreatePatientRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255, description="Full legal name of the patient")
    email: EmailStr = Field(..., description="Patient email address")
    date_of_birth: datetime.date = Field(..., description="Date of birth (YYYY-MM-DD)")
    phone: Optional[str] = Field(None, max_length=50, description="Contact telephone number")
    preferred_language: str = Field("en", max_length=10, description="Preferred language code")
    emergency_contact: Optional[str] = Field(None, max_length=100, description="Emergency contact details")
    accessibility_notes: Optional[str] = Field(None, description="Accessibility or accommodation notes")
    hospital_id: Optional[str] = Field(None, description="Associated hospital ID")
    auth_user_id: Optional[str] = Field(None, description="Optional pre-existing Supabase auth user UUID")


class AdminOnboardDoctorRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255, description="Full legal name of the physician")
    email: EmailStr = Field(..., description="Physician professional email address")
    password: str = Field(..., min_length=8, description="Initial physician password for Supabase Auth account creation")
    license_number: str = Field(..., min_length=2, max_length=100, description="Medical practitioner license number")
    hospital_id: str = Field(..., description="Affiliated hospital UUID")
    department_id: Optional[str] = Field(None, description="Optional department UUID")
    specialty_ids: List[str] = Field(default_factory=list, description="Associated specialty UUIDs")
    primary_specialty_id: Optional[str] = Field(None, description="Primary clinical specialty UUID")
    years_of_experience: int = Field(default=0, ge=0, description="Clinical experience in years")
    consultation_mode: str = Field(default="both", max_length=50, description="in_person, video, or both")
    languages: str = Field(default="en", max_length=255, description="Languages spoken")
    phone: Optional[str] = Field(None, max_length=50, description="Physician phone number")
    auth_user_id: Optional[str] = Field(None, description="Optional pre-existing Supabase auth user UUID")



class AdminAccountCreatedResponse(BaseModel):
    status: str = "created"
    profile_id: str
    auth_user_id: str
    role: str
    full_name: str
    email: str
    entity_id: str  # patient_id or doctor_id
    auth_provisioned: bool = Field(..., description="True if identity was provisioned in Supabase Auth")
    message: str
    invitation_sent: bool = Field(default=False, description="True if an invite or recovery password-setup link was generated")
    action_link: Optional[str] = Field(default=None, description="Password-setup or invitation action link")


class AdminUpdateDoctorStatusRequest(BaseModel):
    is_active: bool = Field(..., description="Set to false to deactivate, true to reactivate")
    reason: Optional[str] = Field(None, max_length=500, description="Administrative rationale for the status update")


class AdminDoctorLifecycleResponse(BaseModel):
    doctor_id: str
    profile_id: str
    full_name: str
    email: str
    is_active: bool
    status: str  # "active", "deactivated", "deleted"
    message: str


class AdminResendInvitationResponse(BaseModel):
    doctor_id: str
    profile_id: str
    full_name: str
    email: str
    action_link: Optional[str] = Field(default=None, description="Regenerated password-setup or invitation link")
    message: str
    auth_provisioned: bool = Field(default=True, description="True if link was provisioned via Supabase Auth")


class DepartmentMetricResponse(BaseModel):
    id: str
    name: str
    code: Optional[str] = None
    active_doctors: int
    total_waiting: int
    mean_wait_minutes: float
    p90_wait_minutes: float
    urgent_cases_count: int
    current_bottleneck: Optional[str] = None


class HourlyMetricResponse(BaseModel):
    hour: str
    arrivals: int
    completed: int


class AdminAnalyticsOverviewResponse(BaseModel):
    total_patients_today: int
    active_queue_count: int
    in_consultation_count: int
    completed_today: int
    mean_wait_minutes: float
    p90_wait_minutes: float
    urgent_delay_rate: float
    doctor_utilization_rate: float
    punctuality_rate: float
    departments: List[DepartmentMetricResponse] = []
    hourly_flow: List[HourlyMetricResponse] = []


