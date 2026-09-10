from typing import Optional
from sqlalchemy.orm import Session
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.patient import Patient
from app.models.profile import UserRole
from app.repositories.patient_repository import patient_repo
from app.repositories.profile_repository import profile_repo
from app.schemas.patient import PatientCreate, PatientUpdate


class PatientService:
    @staticmethod
    def get_patient(db: Session, patient_id: str) -> Patient:
        patient = patient_repo.get_with_details(db, patient_id)
        if not patient:
            raise NotFoundError(
                message=f"Patient with id '{patient_id}' not found",
                code="PATIENT_NOT_FOUND",
            )
        return patient

    @staticmethod
    def get_by_profile_id(db: Session, profile_id: str) -> Optional[Patient]:
        return patient_repo.get_by_profile_id(db, profile_id)

    @staticmethod
    def get_by_auth_user_id(db: Session, auth_user_id: str) -> Patient:
        patient = patient_repo.get_by_auth_user_id(db, auth_user_id)
        if not patient:
            raise NotFoundError(
                message="No patient record found for the current authenticated user",
                code="PATIENT_PROFILE_NOT_FOUND",
            )
        return patient

    @staticmethod
    def create_patient(db: Session, obj_in: PatientCreate) -> Patient:
        # Validate profile exists and has role PATIENT
        profile = profile_repo.get(db, obj_in.profile_id)
        if not profile:
            raise NotFoundError(
                message=f"Profile with id '{obj_in.profile_id}' not found",
                code="PROFILE_NOT_FOUND",
            )
        if profile.role != UserRole.PATIENT:
            raise ConflictError(
                message=f"Profile has role '{profile.role.value}', but PATIENT is required",
                code="INVALID_PROFILE_ROLE",
            )

        # Ensure no existing patient for this profile
        existing_patient = patient_repo.get_by_profile_id(db, obj_in.profile_id)
        if existing_patient:
            raise ConflictError(
                message="A patient record already exists for this profile",
                code="PATIENT_PROFILE_EXISTS",
            )

        return patient_repo.create(db, obj_in=obj_in)

    @staticmethod
    def assert_patient_access(patient: Patient, auth_user_id: str) -> None:
        """Enforces that patients can only access their own record."""
        if patient.profile.auth_user_id != auth_user_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot access another patient's records",
                code="ACCESS_FORBIDDEN",
            )


patient_service = PatientService()
