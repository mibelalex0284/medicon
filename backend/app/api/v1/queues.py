from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser, require_doctor
from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.profile import Profile
from app.schemas.consultation import ConsultationResponse
from app.schemas.queue_entry import QueueEntryResponse
from app.services.consultation_service import consultation_service
from app.services.queue_service import queue_service

router = APIRouter(tags=["Queues"])


def _get_authenticated_doctor(db: Session, current_user: AuthenticatedUser) -> Doctor:
    """Helper resolving the current authenticated doctor entity."""
    doc = (
        db.query(Doctor)
        .join(Profile)
        .filter(Profile.auth_user_id == current_user.id)
        .first()
    )
    if not doc:
        raise ForbiddenError(
            message="No registered doctor record found for your user account",
            code="DOCTOR_RECORD_NOT_FOUND",
        )
    return doc


@router.get(
    "/{doctor_id}/current",
    response_model=List[QueueEntryResponse],
    summary="Get Doctor's Active Queue",
    description="Retrieves the live waiting/called queue for a doctor, deterministically ordered.",
)
def get_doctor_queue(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_doctor),
) -> List[QueueEntryResponse]:
    if not current_user.is_admin:
        doc = _get_authenticated_doctor(db, current_user)
        if doc.id != doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot view another doctor's operational queue",
                code="FORBIDDEN_QUEUE_ACCESS",
            )
    return queue_service.get_doctor_current_queue(db, doctor_id)


@router.post(
    "/{queue_entry_id}/call",
    response_model=QueueEntryResponse,
    summary="Call Next Patient",
    description="Transitions a waiting queue entry to CALLED state.",
)
def call_patient(
    queue_entry_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_doctor),
) -> QueueEntryResponse:
    doc = _get_authenticated_doctor(db, current_user)
    return queue_service.call_patient(db, queue_entry_id, doctor_id=doc.id)


@router.post(
    "/{queue_entry_id}/start",
    response_model=ConsultationResponse,
    summary="Start Patient Consultation",
    description="Transitions queue entry to IN_CONSULTATION and activates the Consultation record.",
)
def start_consultation(
    queue_entry_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_doctor),
) -> ConsultationResponse:
    doc = _get_authenticated_doctor(db, current_user)
    return consultation_service.start_consultation(
        db, queue_entry_id, doctor_id=doc.id
    )


@router.post(
    "/{queue_entry_id}/complete",
    response_model=ConsultationResponse,
    summary="Complete Patient Consultation",
    description="Atomically completes the Consultation, QueueEntry, and Appointment, tracking duration.",
)
def complete_consultation(
    queue_entry_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_doctor),
) -> ConsultationResponse:
    doc = _get_authenticated_doctor(db, current_user)
    return consultation_service.complete_consultation(
        db, queue_entry_id, doctor_id=doc.id
    )
