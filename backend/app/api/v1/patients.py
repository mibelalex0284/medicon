from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import (
    AuthenticatedUser,
    get_current_user,
    require_patient,
    verify_hospital_access,
)
from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.models.profile import Profile
from app.models.queue_entry import QueueEntry
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
    description="Retrieves a patient record. Access is strictly constrained by role and clinical relationship.",
)
def get_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PatientResponse:
    patient = patient_service.get_patient(db, patient_id)

    # 1. Patients can ONLY access their own record
    if current_user.is_patient:
        patient_service.assert_patient_access(patient, current_user.id)
        return patient

    # 2. Doctors may access if they have a clinical relationship or belong to the patient's hospital
    elif current_user.is_doctor:
        doc = (
            db.query(Doctor)
            .join(Profile)
            .filter(Profile.auth_user_id == current_user.id)
            .first()
        )
        if not doc:
            raise ForbiddenError(
                message="No registered doctor record found for authenticated user",
                code="DOCTOR_RECORD_NOT_FOUND",
            )

        # Check for direct clinical relationship (appointment or queue entry)
        has_clinical_relationship = (
            db.query(Appointment)
            .filter(Appointment.doctor_id == doc.id, Appointment.patient_id == patient.id)
            .first()
            is not None
            or db.query(QueueEntry)
            .filter(QueueEntry.doctor_id == doc.id, QueueEntry.patient_id == patient.id)
            .first()
            is not None
        )

        if not has_clinical_relationship:
            # Fall back to hospital tenant boundary
            if patient.profile.hospital_id and doc.hospital_id != patient.profile.hospital_id:
                raise ForbiddenError(
                    message="Access forbidden: doctor does not belong to the patient's hospital and has no active clinical relationship",
                    code="CROSS_HOSPITAL_FORBIDDEN",
                )
        return patient

    # 3. Administrators may access within their hospital tenant boundary
    elif current_user.is_admin:
        if patient.profile.hospital_id:
            verify_hospital_access(patient.profile.hospital_id, current_user)
        return patient

    # 4. Any other role (e.g. unregistered or unverified) is strictly forbidden
    else:
        raise ForbiddenError(
            message="Access forbidden: insufficient role permissions to view patient record",
            code="INSUFFICIENT_ROLE_PERMISSIONS",
        )

