from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import (
    AuthenticatedUser,
    get_current_user,
    require_patient,
)
from app.db.session import get_db
from app.schemas.patient import PatientResponse
from app.schemas.queue_entry import PatientQueueStatusResponse
from app.services.patient_service import patient_service
from app.services.queue_service import queue_service

router = APIRouter(tags=["Patients"])


@router.get(
    "/me",
    response_model=PatientResponse,
    summary="Get Current Patient Profile",
    description="Securely retrieves the patient profile for the currently authenticated user.",
)
def get_current_patient(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> PatientResponse:
    return patient_service.get_by_auth_user_id(db, current_user.id)


@router.get(
    "/me/queue",
    response_model=PatientQueueStatusResponse,
    summary="Get Patient Queue Position & Wait Estimate",
    description="Returns the patient's active queue position, token number, patients ahead, and estimated wait range.",
)
def get_current_patient_queue(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> PatientQueueStatusResponse:
    patient = patient_service.get_by_auth_user_id(db, current_user.id)
    return queue_service.get_patient_queue_status(db, patient.id)


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Get Patient Details",
    description="Retrieves a patient record. Patients may only access their own record.",
)
def get_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PatientResponse:
    patient = patient_service.get_patient(db, patient_id)

    # Patients can ONLY access their own record
    if current_user.is_patient:
        patient_service.assert_patient_access(patient, current_user.id)

    return patient
