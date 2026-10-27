import datetime
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.models.appointment import AppointmentStatus
from app.models.consultation import Consultation, ConsultationStatus
from app.models.queue_entry import QueueEntry, QueueStatus
from app.repositories.appointment_repository import appointment_repo
from app.repositories.consultation_repository import consultation_repo
from app.repositories.queue_repository import queue_repo


class ConsultationService:
    @staticmethod
    def get_consultation(db: Session, consultation_id: str) -> Consultation:
        consultation = consultation_repo.get(db, consultation_id)
        if not consultation:
            raise NotFoundError(
                message=f"Consultation with id '{consultation_id}' not found",
                code="CONSULTATION_NOT_FOUND",
            )
        return consultation

    @staticmethod
    def start_consultation(
        db: Session, queue_entry_id: str, doctor_id: str
    ) -> Consultation:
        """Transitions QueueEntry to IN_CONSULTATION and creates/activates the Consultation record."""
        entry = queue_repo.get(db, queue_entry_id)
        if not entry:
            raise NotFoundError(
                message=f"Queue entry with id '{queue_entry_id}' not found",
                code="QUEUE_ENTRY_NOT_FOUND",
            )

        # Authoritative ownership check
        if entry.doctor_id != doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot start consultations for another doctor's patient",
                code="NOT_ASSIGNED_DOCTOR",
            )

        # Idempotent resume check: if already IN_CONSULTATION and active for this doctor, return existing
        if entry.status == QueueStatus.IN_CONSULTATION:
            active_existing = consultation_repo.get_by_queue_entry_id(db, queue_entry_id)
            if (
                active_existing
                and active_existing.doctor_id == doctor_id
                and active_existing.status == ConsultationStatus.IN_PROGRESS
            ):
                return active_existing

        # State transition check: entry must be CALLED or WAITING
        if entry.status not in [QueueStatus.CALLED, QueueStatus.WAITING]:
            raise InvalidStateTransitionError(
                message=f"Cannot start consultation for patient in '{entry.status.value}' state. Must be CALLED or WAITING.",
                code="INVALID_QUEUE_TRANSITION",
            )

        # Enforce that doctor cannot have multiple consultations IN_PROGRESS simultaneously
        active_consultation = consultation_repo.get_active_by_doctor(db, doctor_id)
        if active_consultation and active_consultation.queue_entry_id != queue_entry_id:
            raise ConflictError(
                message="Doctor already has an active consultation in progress. Complete it before starting a new one.",
                code="DOCTOR_BUSY_WITH_ACTIVE_CONSULTATION",
            )

        now = datetime.datetime.now(datetime.timezone.utc)

        # Check if consultation already exists
        consultation = consultation_repo.get_by_queue_entry_id(db, queue_entry_id)
        if not consultation:
            consultation = Consultation(
                queue_entry_id=entry.id,
                appointment_id=entry.appointment_id,
                patient_id=entry.patient_id,
                doctor_id=entry.doctor_id,
                hospital_id=entry.hospital_id,
                started_at=now,
                status=ConsultationStatus.IN_PROGRESS,
            )
            db.add(consultation)
        else:
            consultation.started_at = now
            consultation.status = ConsultationStatus.IN_PROGRESS

        # Coordinated queue transition
        entry.status = QueueStatus.IN_CONSULTATION
        entry.consultation_started_at = now

        db.add(entry)
        db.commit()
        db.refresh(consultation)
        db.refresh(entry)
        return consultation

    @staticmethod
    def save_consultation_notes(
        db: Session,
        consultation_id: str,
        doctor_id: str,
        notes_in: Any,
    ) -> Consultation:
        """Persists clinical notes, diagnosis, and orders for an active consultation."""
        consultation = consultation_repo.get(db, consultation_id)
        if not consultation:
            raise NotFoundError(
                message=f"Consultation with id '{consultation_id}' not found",
                code="CONSULTATION_NOT_FOUND",
            )

        if consultation.doctor_id != doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot update another doctor's consultation",
                code="NOT_ASSIGNED_DOCTOR",
            )

        if consultation.status == ConsultationStatus.COMPLETED:
            raise InvalidStateTransitionError(
                message="Cannot update notes for an already completed consultation",
                code="ALREADY_COMPLETED",
            )

        if hasattr(notes_in, "clinical_notes") and notes_in.clinical_notes is not None:
            consultation.clinical_notes = notes_in.clinical_notes
        if hasattr(notes_in, "diagnosis") and notes_in.diagnosis is not None:
            consultation.diagnosis = notes_in.diagnosis
        if hasattr(notes_in, "prescriptions") and notes_in.prescriptions is not None:
            consultation.prescriptions = notes_in.prescriptions
        if hasattr(notes_in, "follow_up_instructions") and notes_in.follow_up_instructions is not None:
            consultation.follow_up_instructions = notes_in.follow_up_instructions

        db.add(consultation)
        db.commit()
        db.refresh(consultation)
        return consultation

    @staticmethod
    def complete_consultation(
        db: Session,
        queue_entry_id: str,
        doctor_id: str,
        notes_in: Optional[Any] = None,
    ) -> Consultation:
        """Transitions Consultation and QueueEntry to COMPLETED, calculates duration, persists notes, and completes Appointment."""
        entry = queue_repo.get(db, queue_entry_id)
        if not entry:
            raise NotFoundError(
                message=f"Queue entry with id '{queue_entry_id}' not found",
                code="QUEUE_ENTRY_NOT_FOUND",
            )

        if entry.doctor_id != doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot complete consultations for another doctor's patient",
                code="NOT_ASSIGNED_DOCTOR",
            )

        if entry.status != QueueStatus.IN_CONSULTATION:
            raise InvalidStateTransitionError(
                message=f"Cannot complete consultation from '{entry.status.value}' state. Must be IN_CONSULTATION.",
                code="INVALID_QUEUE_TRANSITION",
            )

        consultation = consultation_repo.get_by_queue_entry_id(db, queue_entry_id)
        if not consultation:
            raise NotFoundError(
                message="No consultation record found for this queue entry",
                code="CONSULTATION_NOT_FOUND",
            )

        if consultation.status == ConsultationStatus.COMPLETED:
            raise InvalidStateTransitionError(
                message="Consultation is already completed",
                code="ALREADY_COMPLETED",
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        started_at = consultation.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=datetime.timezone.utc)
        duration_seconds = max(0, int((now - started_at).total_seconds()))

        # Update notes if supplied at completion time
        if notes_in:
            if hasattr(notes_in, "clinical_notes") and notes_in.clinical_notes is not None:
                consultation.clinical_notes = notes_in.clinical_notes
            if hasattr(notes_in, "diagnosis") and notes_in.diagnosis is not None:
                consultation.diagnosis = notes_in.diagnosis
            if hasattr(notes_in, "prescriptions") and notes_in.prescriptions is not None:
                consultation.prescriptions = notes_in.prescriptions
            if hasattr(notes_in, "follow_up_instructions") and notes_in.follow_up_instructions is not None:
                consultation.follow_up_instructions = notes_in.follow_up_instructions

        # Update Consultation
        consultation.status = ConsultationStatus.COMPLETED
        consultation.completed_at = now
        consultation.duration_seconds = duration_seconds

        # Update QueueEntry
        entry.status = QueueStatus.COMPLETED
        entry.completed_at = now

        # Update Appointment
        appt = appointment_repo.get(db, entry.appointment_id)
        if appt:
            appt.status = AppointmentStatus.COMPLETED
            db.add(appt)

        db.add(consultation)
        db.add(entry)
        db.commit()
        db.refresh(consultation)
        db.refresh(entry)
        return consultation

    @staticmethod
    def get_active_by_doctor(
        db: Session, doctor_id: str
    ) -> Optional[Consultation]:
        return consultation_repo.get_active_by_doctor(db, doctor_id)

    @staticmethod
    def get_by_queue_entry(
        db: Session, queue_entry_id: str, doctor_id: str
    ) -> Consultation:
        consultation = consultation_repo.get_by_queue_entry_id(db, queue_entry_id)
        if not consultation:
            raise NotFoundError(
                message=f"No consultation found for queue entry '{queue_entry_id}'",
                code="CONSULTATION_NOT_FOUND",
            )
        if consultation.doctor_id != doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot view another doctor's consultation",
                code="NOT_ASSIGNED_DOCTOR",
            )
        return consultation


consultation_service = ConsultationService()
