"""Services package."""
from app.services.appointment_service import AppointmentService, appointment_service
from app.services.consultation_service import (
    ConsultationService,
    consultation_service,
)
from app.services.department_service import DepartmentService, department_service
from app.services.doctor_service import DoctorService, doctor_service
from app.services.hospital_service import HospitalService, hospital_service
from app.services.patient_service import PatientService, patient_service
from app.services.profile_service import ProfileService, profile_service
from app.services.queue_service import QueueService, queue_service
from app.services.specialty_service import SpecialtyService, specialty_service
from app.services.triage_service import TriageService, triage_service

__all__ = [
    "hospital_service",
    "HospitalService",
    "department_service",
    "DepartmentService",
    "specialty_service",
    "SpecialtyService",
    "profile_service",
    "ProfileService",
    "doctor_service",
    "DoctorService",
    "patient_service",
    "PatientService",
    "appointment_service",
    "AppointmentService",
    "queue_service",
    "QueueService",
    "consultation_service",
    "ConsultationService",
    "triage_service",
    "TriageService",
]
