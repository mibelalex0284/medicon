import datetime
from typing import List, Optional
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
    ) -> QueueEntry:
        appt = appointment_repo.get(db, appointment_id)
        if not appt:
            raise NotFoundError(
                message=f"Appointment with id '{appointment_id}' not found",
                code="APPOINTMENT_NOT_FOUND",
            )

        # 1. Authoritative check: only the appointment's patient may check in
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

        # 3. Idempotency: cannot check in multiple times
        existing_entry = queue_repo.get_by_appointment_id(db, appointment_id)
        if existing_entry and existing_entry.status not in [
            QueueStatus.CANCELLED,
            QueueStatus.NO_SHOW,
        ]:
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
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

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
        )


queue_service = QueueService()
