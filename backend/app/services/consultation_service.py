import datetime
from typing import Optional
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

        # State transition check: entry must be CALLED or WAITING
        if entry.status not in [QueueStatus.CALLED, QueueStatus.WAITING]:
            raise InvalidStateTransitionError(
                message=f"Cannot start consultation for patient in '{entry.status.value}' state. Must be CALLED or WAITING.",
                code="INVALID_QUEUE_TRANSITION",
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
    def complete_consultation(
        db: Session, queue_entry_id: str, doctor_id: str
    ) -> Consultation:
        """Transitions Consultation and QueueEntry to COMPLETED, calculates duration, and completes Appointment."""
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


consultation_service = ConsultationService()
