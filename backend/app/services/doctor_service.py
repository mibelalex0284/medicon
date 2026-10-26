import datetime
import logging
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

logger = logging.getLogger(__name__)


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
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Doctor]:
        return doctor_repo.filter_doctors(
            db,
            hospital_id=hospital_id,
            specialty_id=specialty_id,
            department_id=department_id,
            is_active=is_active,
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

    @staticmethod
    def create_default_schedules(
        db: Session,
        doctor_id: str,
        *,
        start_time: datetime.time = datetime.time(9, 0),
        end_time: datetime.time = datetime.time(17, 0),
        slot_duration_minutes: int = 30,
        weekdays: Optional[List[int]] = None,
        overwrite: bool = False,
    ) -> List[DoctorSchedule]:
        """Creates sensible default weekday outpatient consultation schedules for a doctor.
        
        Requirements:
        - Validates doctor exists, is active, and assigned to a hospital facility.
        - Idempotent: If doctor already has configured schedules and overwrite is False, preserves them.
        - If overwrite is True, cleanly removes existing schedules before creating new ones.
        - Respects slot duration and configured hours.
        - Defaults to Monday-Friday (0 through 4), 09:00 - 17:00, 30-min slots.
        """
        doctor = doctor_repo.get(db, doctor_id)
        if not doctor:
            raise NotFoundError(
                message=f"Doctor with id '{doctor_id}' not found",
                code="DOCTOR_NOT_FOUND",
            )
        if not doctor.is_active:
            raise ConflictError(
                message="Cannot configure consultation schedule for an inactive physician",
                code="DOCTOR_INACTIVE",
            )
        if not doctor.hospital_id:
            raise ConflictError(
                message="Doctor is not assigned to a hospital facility",
                code="DOCTOR_HOSPITAL_MISSING",
            )

        existing_schedules = doctor_schedule_repo.get_by_doctor(db, doctor_id=doctor_id)
        if existing_schedules and not overwrite:
            logger.info(
                f"Doctor {doctor_id} already has {len(existing_schedules)} schedule record(s). Preserving existing."
            )
            return existing_schedules

        if existing_schedules and overwrite:
            for s in existing_schedules:
                db.delete(s)
            db.flush()

        target_days = weekdays if weekdays is not None else [0, 1, 2, 3, 4]
        created: List[DoctorSchedule] = []
        for day in target_days:
            # Prevent duplicate for same day
            if not overwrite and any(s.day_of_week == day for s in existing_schedules):
                continue
            sched = DoctorSchedule(
                doctor_id=doctor.id,
                hospital_id=doctor.hospital_id,
                day_of_week=day,
                start_time=start_time,
                end_time=end_time,
                slot_duration_minutes=slot_duration_minutes,
                is_active=True,
            )
            db.add(sched)
            created.append(sched)

        db.flush()
        return created

    @staticmethod
    def ensure_default_schedules_if_missing(
        db: Session, doctor_id: str
    ) -> List[DoctorSchedule]:
        """Ensures that an active doctor has at least default schedules configured."""
        return DoctorService.create_default_schedules(db, doctor_id, overwrite=False)

    @staticmethod
    def repair_unscheduled_doctors(
        db: Session,
        *,
        hospital_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """Finds active doctors lacking schedules and safely initializes default weekday schedules.
        
        Completely non-destructive, idempotent, and preserves all appointments, doctors, and patient records.
        """
        query = db.query(Doctor).filter(Doctor.is_active == True)
        if hospital_id:
            query = query.filter(Doctor.hospital_id == hospital_id)
        doctors = query.all()

        unscheduled_docs = []
        for doc in doctors:
            existing = doctor_schedule_repo.get_by_doctor(db, doctor_id=doc.id, is_active=True)
            if not existing:
                prof_name = doc.profile.full_name if doc.profile else "Unknown"
                unscheduled_docs.append({
                    "doctor_id": doc.id,
                    "doctor_name": prof_name,
                    "hospital_id": doc.hospital_id,
                })

        if dry_run or not unscheduled_docs:
            return {
                "dry_run": dry_run,
                "unscheduled_count": len(unscheduled_docs),
                "doctors": unscheduled_docs,
                "repaired_count": 0,
            }

        repaired = []
        for item in unscheduled_docs:
            try:
                schedules = DoctorService.create_default_schedules(
                    db, item["doctor_id"], overwrite=False
                )
                repaired.append({
                    "doctor_id": item["doctor_id"],
                    "doctor_name": item["doctor_name"],
                    "schedules_created": len(schedules),
                })
            except Exception as e:
                logger.error(f"Failed to initialize default schedule for doctor {item['doctor_id']}: {e}")
                raise

        db.commit()
        return {
            "dry_run": False,
            "unscheduled_count": len(unscheduled_docs),
            "repaired_count": len(repaired),
            "doctors": repaired,
        }


doctor_service = DoctorService()

