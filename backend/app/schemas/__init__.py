"""Pydantic schemas package."""
from app.schemas.appointment import (
    AppointmentBase,
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    AvailableSlot,
    DoctorAvailabilityResponse,
)
from app.schemas.consultation import (
    ConsultationBase,
    ConsultationCreate,
    ConsultationResponse,
)
from app.schemas.department import (
    DepartmentBase,
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
)
from app.schemas.doctor import (
    DoctorBase,
    DoctorCreate,
    DoctorResponse,
    DoctorUpdate,
)
from app.schemas.doctor_schedule import (
    DoctorScheduleBase,
    DoctorScheduleCreate,
    DoctorScheduleResponse,
    DoctorScheduleUpdate,
)
from app.schemas.doctor_specialty import (
    DoctorSpecialtyBase,
    DoctorSpecialtyCreate,
    DoctorSpecialtyResponse,
)
from app.schemas.hospital import (
    HospitalBase,
    HospitalCreate,
    HospitalResponse,
    HospitalUpdate,
)
from app.schemas.patient import (
    PatientBase,
    PatientCreate,
    PatientResponse,
    PatientUpdate,
)
from app.schemas.profile import (
    ProfileBase,
    ProfileCreate,
    ProfileResponse,
    ProfileUpdate,
)
from app.schemas.queue_entry import (
    PatientQueueStatusResponse,
    QueueEntryBase,
    QueueEntryCreate,
    QueueEntryResponse,
    WaitEstimate,
)
from app.schemas.specialty import (
    SpecialtyBase,
    SpecialtyCreate,
    SpecialtyResponse,
    SpecialtyUpdate,
)
from app.schemas.triage import (
    TriageAnswerCreate,
    TriageAnswerResponse,
    TriageAssessmentResponse,
    TriageQuestionResponse,
    TriageSessionConfirm,
    TriageSessionCreate,
    TriageSessionResponse,
)
from app.schemas.admin_settings import (
    RegistrationStatusResponse,
    AdminSettingsResponse,
    UpdatePatientSelfRegistrationRequest,
    AdminCreatePatientRequest,
    AdminOnboardDoctorRequest,
    AdminAccountCreatedResponse,
    AdminUpdateDoctorStatusRequest,
    AdminDoctorLifecycleResponse,
)

__all__ = [
    "HospitalBase",
    "HospitalCreate",
    "HospitalUpdate",
    "HospitalResponse",
    "DepartmentBase",
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentResponse",
    "SpecialtyBase",
    "SpecialtyCreate",
    "SpecialtyUpdate",
    "SpecialtyResponse",
    "ProfileBase",
    "ProfileCreate",
    "ProfileUpdate",
    "ProfileResponse",
    "DoctorSpecialtyBase",
    "DoctorSpecialtyCreate",
    "DoctorSpecialtyResponse",
    "DoctorScheduleBase",
    "DoctorScheduleCreate",
    "DoctorScheduleUpdate",
    "DoctorScheduleResponse",
    "DoctorBase",
    "DoctorCreate",
    "DoctorUpdate",
    "DoctorResponse",
    "PatientBase",
    "PatientCreate",
    "PatientUpdate",
    "PatientResponse",
    "AppointmentBase",
    "AppointmentCreate",
    "AppointmentUpdate",
    "AppointmentResponse",
    "AvailableSlot",
    "DoctorAvailabilityResponse",
    "QueueEntryBase",
    "QueueEntryCreate",
    "QueueEntryResponse",
    "PatientQueueStatusResponse",
    "WaitEstimate",
    "ConsultationBase",
    "ConsultationCreate",
    "ConsultationResponse",
    "TriageSessionCreate",
    "TriageSessionConfirm",
    "TriageSessionResponse",
    "TriageQuestionResponse",
    "TriageAnswerCreate",
    "TriageAnswerResponse",
    "TriageAssessmentResponse",
    "RegistrationStatusResponse",
    "AdminSettingsResponse",
    "UpdatePatientSelfRegistrationRequest",
    "AdminCreatePatientRequest",
    "AdminOnboardDoctorRequest",
    "AdminAccountCreatedResponse",
    "AdminUpdateDoctorStatusRequest",
    "AdminDoctorLifecycleResponse",
]

