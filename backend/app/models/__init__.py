"""Domain models package."""
from app.models.appointment import Appointment, AppointmentStatus
from app.models.consultation import Consultation, ConsultationStatus
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.doctor_specialty import DoctorSpecialty
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.profile import Profile, UserRole
from app.models.queue_entry import QueueEntry, QueueStatus
from app.models.specialty import Specialty
from app.models.triage_answer import TriageAnswer
from app.models.triage_assessment import TriageAssessment, TriageUrgency
from app.models.triage_question import QuestionResponseType, TriageQuestion
from app.models.triage_session import TriageSession, TriageSessionStatus

__all__ = [
    "UserRole",
    "Profile",
    "Hospital",
    "Department",
    "Specialty",
    "Doctor",
    "DoctorSpecialty",
    "DoctorSchedule",
    "Patient",
    "Appointment",
    "AppointmentStatus",
    "QueueEntry",
    "QueueStatus",
    "Consultation",
    "ConsultationStatus",
    "TriageSession",
    "TriageSessionStatus",
    "TriageQuestion",
    "QuestionResponseType",
    "TriageAnswer",
    "TriageAssessment",
    "TriageUrgency",
]
