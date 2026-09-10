from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.exceptions import ConflictError, InvalidStateTransitionError, NotFoundError
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.doctor_specialty import DoctorSpecialty
from app.models.profile import UserRole
from app.repositories.department_repository import department_repo
from app.repositories.doctor_repository import doctor_repo
from app.repositories.doctor_schedule_repository import doctor_schedule_repo
from app.repositories.hospital_repository import hospital_repo
from app.repositories.profile_repository import profile_repo
from app.repositories.specialty_repository import specialty_repo
from app.schemas.doctor import DoctorCreate, DoctorUpdate
from app.schemas.doctor_schedule import DoctorScheduleCreate
from app.schemas.doctor_specialty import DoctorSpecialtyCreate


class DoctorService:
    @staticmethod
    def get_doctor(db: Session, doctor_id: str) -> Doctor:
        doctor = doctor_repo.get_with_details(db, doctor_id)
        if not doctor:
            raise NotFoundError(
                message=f"Doctor with id '{doctor_id}' not found",
                code="DOCTOR_NOT_FOUND",
            )
        return doctor

    @staticmethod
    def get_by_profile_id(db: Session, profile_id: str) -> Optional[Doctor]:
        return doctor_repo.get_by_profile_id(db, profile_id)

    @staticmethod
    def list_doctors(
        db: Session,
        *,
        hospital_id: Optional[str] = None,
        specialty_id: Optional[str] = None,
        department_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Doctor]:
        return doctor_repo.filter_doctors(
            db,
            hospital_id=hospital_id,
            specialty_id=specialty_id,
            department_id=department_id,
            skip=skip,
            limit=limit,
        )

    @staticmethod
    def create_doctor(db: Session, obj_in: DoctorCreate) -> Doctor:
        # Validate profile exists and has role DOCTOR
        profile = profile_repo.get(db, obj_in.profile_id)
        if not profile:
            raise NotFoundError(
                message=f"Profile with id '{obj_in.profile_id}' not found",
                code="PROFILE_NOT_FOUND",
            )
        if profile.role != UserRole.DOCTOR:
            raise ConflictError(
                message=f"Profile has role '{profile.role.value}', but DOCTOR is required",
                code="INVALID_PROFILE_ROLE",
            )

        # Ensure no existing doctor for this profile
        existing_doc = doctor_repo.get_by_profile_id(db, obj_in.profile_id)
        if existing_doc:
            raise ConflictError(
                message="A doctor record already exists for this profile",
                code="DOCTOR_PROFILE_EXISTS",
            )

        # Validate hospital
        hospital = hospital_repo.get(db, obj_in.hospital_id)
        if not hospital:
            raise NotFoundError(
                message=f"Hospital with id '{obj_in.hospital_id}' not found",
                code="HOSPITAL_NOT_FOUND",
            )

        # Validate department belongs to the hospital if supplied
        if obj_in.department_id:
            dept = department_repo.get(db, obj_in.department_id)
            if not dept or dept.hospital_id != obj_in.hospital_id:
                raise ConflictError(
                    message="Department does not exist or does not belong to the doctor's hospital",
                    code="INVALID_DEPARTMENT_HOSPITAL",
                )

        # Check unique license
        if doctor_repo.get_by_license(db, obj_in.license_number):
            raise ConflictError(
                message=f"Doctor with license '{obj_in.license_number}' already exists",
                code="DOCTOR_LICENSE_EXISTS",
            )

        return doctor_repo.create(db, obj_in=obj_in)

    @staticmethod
    def assign_specialty(
        db: Session, doctor_id: str, obj_in: DoctorSpecialtyCreate
    ) -> DoctorSpecialty:
        doctor = DoctorService.get_doctor(db, doctor_id)
        specialty = specialty_repo.get(db, obj_in.specialty_id)
        if not specialty:
            raise NotFoundError(
                message=f"Specialty with id '{obj_in.specialty_id}' not found",
                code="SPECIALTY_NOT_FOUND",
            )

        # Check duplicate doctor-specialty link
        existing = (
            db.query(DoctorSpecialty)
            .filter(
                DoctorSpecialty.doctor_id == doctor_id,
                DoctorSpecialty.specialty_id == obj_in.specialty_id,
            )
            .first()
        )
        if existing:
            raise ConflictError(
                message="Doctor is already associated with this specialty",
                code="DOCTOR_SPECIALTY_EXISTS",
            )

        doc_spec = DoctorSpecialty(
            doctor_id=doctor_id,
            specialty_id=obj_in.specialty_id,
            is_primary=obj_in.is_primary,
        )
        db.add(doc_spec)
        db.commit()
        db.refresh(doc_spec)
        return doc_spec

    @staticmethod
    def add_schedule(
        db: Session, doctor_id: str, obj_in: DoctorScheduleCreate
    ) -> DoctorSchedule:
        doctor = DoctorService.get_doctor(db, doctor_id)
        if obj_in.hospital_id != doctor.hospital_id:
            raise ConflictError(
                message="Schedule hospital must match the doctor's registered hospital",
                code="SCHEDULE_HOSPITAL_MISMATCH",
            )
        if obj_in.end_time <= obj_in.start_time:
            raise InvalidStateTransitionError(
                message="Schedule end_time must be later than start_time",
                code="INVALID_SCHEDULE_TIME_RANGE",
            )

        return doctor_schedule_repo.create(db, obj_in=obj_in)


doctor_service = DoctorService()
