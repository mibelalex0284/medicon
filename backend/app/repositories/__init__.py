"""Repositories package."""
from app.repositories.appointment_repository import AppointmentRepository, appointment_repo
from app.repositories.base import BaseRepository
from app.repositories.consultation_repository import (
    ConsultationRepository,
    consultation_repo,
)
from app.repositories.department_repository import DepartmentRepository, department_repo
from app.repositories.doctor_repository import DoctorRepository, doctor_repo
from app.repositories.doctor_schedule_repository import (
    DoctorScheduleRepository,
    doctor_schedule_repo,
)
from app.repositories.hospital_repository import HospitalRepository, hospital_repo
from app.repositories.patient_repository import PatientRepository, patient_repo
from app.repositories.profile_repository import ProfileRepository, profile_repo
from app.repositories.queue_repository import QueueRepository, queue_repo
from app.repositories.specialty_repository import SpecialtyRepository, specialty_repo

__all__ = [
    "BaseRepository",
    "hospital_repo",
    "HospitalRepository",
    "department_repo",
    "DepartmentRepository",
    "specialty_repo",
    "SpecialtyRepository",
    "profile_repo",
    "ProfileRepository",
    "doctor_repo",
    "DoctorRepository",
    "doctor_schedule_repo",
    "DoctorScheduleRepository",
    "patient_repo",
    "PatientRepository",
    "appointment_repo",
    "AppointmentRepository",
    "queue_repo",
    "QueueRepository",
    "consultation_repo",
    "ConsultationRepository",
]
