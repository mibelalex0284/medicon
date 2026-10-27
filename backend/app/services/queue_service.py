import datetime
from typing import List, Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.models.appointment import AppointmentStatus
from app.models.queue_entry import QueueEntry, QueueStatus
from app.repositories.appointment_repository import appointment_repo
from app.repositories.patient_repository import patient_repo
from app.repositories.queue_repository import queue_repo
from app.schemas.queue_entry import PatientQueueStatusResponse, WaitEstimate


class QueueService:
    @staticmethod
    def get_queue_entry(db: Session, queue_entry_id: str) -> QueueEntry:
        entry = queue_repo.get(db, queue_entry_id)
        if not entry:
            raise NotFoundError(
                message=f"Queue entry with id '{queue_entry_id}' not found",
                code="QUEUE_ENTRY_NOT_FOUND",
            )
        return entry

    @staticmethod
    def check_in(
        db: Session,
        appointment_id: str,
        *,
        actor_auth_user_id: str,
        is_doctor: bool = False,
        is_admin: bool = False,
    ) -> QueueEntry:
        appt = appointment_repo.get(db, appointment_id)
        if not appt:
            raise NotFoundError(
                message=f"Appointment with id '{appointment_id}' not found",
                code="APPOINTMENT_NOT_FOUND",
            )

        # 1. Authoritative check:
        # Patient may check in their own appointment.
        # Assigned doctor may check in their patient.
        # Admin may check in for clinic operations.
        if is_doctor:
            from app.models.doctor import Doctor
            from app.models.profile import Profile
            doc = (
                db.query(Doctor)
                .join(Profile)
                .filter(Profile.auth_user_id == actor_auth_user_id)
                .first()
            )
            if not doc or doc.id != appt.doctor_id:
                raise ForbiddenError(
                    message="Access forbidden: you cannot check in patients assigned to another doctor",
                    code="NOT_ASSIGNED_DOCTOR",
                )
        elif is_admin:
            pass  # Authorized administrative check-in
        else:
            patient = patient_repo.get(db, appt.patient_id)
            if not patient or patient.profile.auth_user_id != actor_auth_user_id:
                raise ForbiddenError(
                    message="Access forbidden: you can only check in for your own appointments",
                    code="FORBIDDEN_CHECK_IN",
                )

        # 2. Eligibility checks
        if appt.status == AppointmentStatus.CANCELLED:
            raise InvalidStateTransitionError(
                message="Cannot check in for a cancelled appointment",
                code="CANNOT_CHECK_IN_CANCELLED",
            )
        if appt.status == AppointmentStatus.COMPLETED:
            raise InvalidStateTransitionError(
                message="Cannot check in for an already completed appointment",
                code="CANNOT_CHECK_IN_COMPLETED",
            )
        if appt.status == AppointmentStatus.NO_SHOW:
            raise InvalidStateTransitionError(
                message="Cannot check in for an appointment marked as no-show",
                code="CANNOT_CHECK_IN_NO_SHOW",
            )

        # 3. Idempotency: cannot check in multiple times
        existing_entry = queue_repo.get_by_appointment_id(db, appointment_id)
        if existing_entry:
            raise ConflictError(
                message="Patient is already checked in for this appointment",
                code="ALREADY_CHECKED_IN",
            )

        # 4. Generate token and create queue entry
        today = datetime.datetime.now(datetime.timezone.utc).date()
        token = queue_repo.generate_token_number(
            db, hospital_id=appt.hospital_id, doctor_id=appt.doctor_id, queue_date=today
        )

        entry = QueueEntry(
            appointment_id=appt.id,
            patient_id=appt.patient_id,
            doctor_id=appt.doctor_id,
            hospital_id=appt.hospital_id,
            queue_date=today,
            token_number=token,
            status=QueueStatus.WAITING,
            checked_in_at=datetime.datetime.now(datetime.timezone.utc),
        )
        try:
            db.add(entry)
            appt.status = AppointmentStatus.CONFIRMED
            db.add(appt)
            db.commit()
            db.refresh(entry)
            return entry
        except IntegrityError:
            db.rollback()
            raise ConflictError(
                message="Patient is already checked in for this appointment",
                code="ALREADY_CHECKED_IN",
            )

    @staticmethod
    def call_patient(db: Session, queue_entry_id: str, doctor_id: str) -> QueueEntry:
        entry = QueueService.get_queue_entry(db, queue_entry_id)

        # Verify doctor ownership
        if entry.doctor_id != doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot operate another doctor's queue",
                code="NOT_ASSIGNED_DOCTOR",
            )

        # State machine: Only WAITING or CHECKED_IN may be called
        if entry.status not in [QueueStatus.WAITING, QueueStatus.CHECKED_IN]:
            raise InvalidStateTransitionError(
                message=f"Cannot call patient in '{entry.status.value}' state. Must be WAITING.",
                code="INVALID_QUEUE_TRANSITION",
            )

        entry.status = QueueStatus.CALLED
        entry.called_at = datetime.datetime.now(datetime.timezone.utc)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    @staticmethod
    def get_doctor_current_queue(
        db: Session, doctor_id: str, queue_date: Optional[datetime.date] = None
    ) -> List[QueueEntry]:
        date_to_query = queue_date or datetime.datetime.now(datetime.timezone.utc).date()
        return queue_repo.get_active_queue_for_doctor(db, doctor_id, date_to_query)

    @staticmethod
    def get_patient_queue_status(
        db: Session, patient_id: str
    ) -> PatientQueueStatusResponse:
        entry = queue_repo.get_active_patient_entry(db, patient_id)
        if not entry:
            raise NotFoundError(
                message="No active queue entry found for patient",
                code="NO_ACTIVE_QUEUE_ENTRY",
            )

        patients_ahead = queue_repo.count_patients_ahead(
            db, doctor_id=entry.doctor_id, queue_date=entry.queue_date, entry=entry
        )

        # Deterministic baseline wait calculation
        avg_slot = 15  # Baseline default minutes per consultation
        expected = max(5, patients_ahead * avg_slot)
        lower = max(2, int(expected * 0.7))
        upper = max(10, int(expected * 1.4))

        wait_est = WaitEstimate(
            lower_minutes=lower,
            expected_minutes=expected,
            upper_minutes=upper,
            source="baseline",
        )

        return PatientQueueStatusResponse(
            queue_entry_id=entry.id,
            appointment_id=entry.appointment_id,
            doctor_id=entry.doctor_id,
            hospital_id=entry.hospital_id,
            token_number=entry.token_number,
            status=entry.status,
            checked_in_at=entry.checked_in_at,
            called_at=entry.called_at,
            consultation_started_at=entry.consultation_started_at,
            patients_ahead=patients_ahead,
            wait_estimate=wait_est,
            patient_name=entry.patient_name,
            doctor_name=entry.doctor_name,
            room_number=entry.room_number,
            department_name=entry.department_name,
            chief_complaint=entry.chief_complaint,
        )

    @staticmethod
    def mark_no_show(db: Session, queue_entry_id: str, doctor_id: str) -> QueueEntry:
        entry = QueueService.get_queue_entry(db, queue_entry_id)
        if entry.doctor_id != doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot operate another doctor's queue",
                code="NOT_ASSIGNED_DOCTOR",
            )
        if entry.status in [QueueStatus.COMPLETED, QueueStatus.CANCELLED]:
            raise InvalidStateTransitionError(
                message=f"Cannot mark entry in '{entry.status.value}' state as NO_SHOW",
                code="INVALID_QUEUE_TRANSITION",
            )
        entry.status = QueueStatus.NO_SHOW
        appt = appointment_repo.get(db, entry.appointment_id)
        if appt:
            appt.status = AppointmentStatus.NO_SHOW
            db.add(appt)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry


queue_service = QueueService()
