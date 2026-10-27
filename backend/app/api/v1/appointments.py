import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.dependencies import (
    AuthenticatedUser,
    get_current_user,
    require_patient,
    verify_hospital_access,
)
from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.models.appointment import AppointmentStatus
from app.repositories.doctor_repository import doctor_repo
from app.repositories.patient_repository import patient_repo
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
)
from app.schemas.queue_entry import QueueEntryResponse
from app.services.appointment_service import appointment_service
from app.services.queue_service import queue_service

router = APIRouter(tags=["Appointments"])


@router.post(
    "",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book an Outpatient Appointment",
    description="Schedules an appointment with a doctor. Enforces availability and conflict prevention.",
)
def book_appointment(
    appt_in: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AppointmentResponse:
    # Authorization: Patients can only book for themselves
    if current_user.is_patient:
        patient = patient_repo.get_by_auth_user_id(db, current_user.id)
        if not patient or patient.id != appt_in.patient_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot book appointments on behalf of another patient",
                code="FORBIDDEN_PATIENT_BOOKING",
            )
    elif current_user.is_admin:
        verify_hospital_access(appt_in.hospital_id, current_user)
    else:
        raise ForbiddenError(
            message="Only patients or authorized staff can book appointments",
            code="INSUFFICIENT_PERMISSIONS",
        )

    return appointment_service.book_appointment(db, appt_in)


@router.get(
    "",
    response_model=List[AppointmentResponse],
    summary="List Appointments",
    description="Lists appointments according to role authorization boundaries.",
)
def list_appointments(
    patient_id: Optional[str] = Query(None),
    doctor_id: Optional[str] = Query(None),
    hospital_id: Optional[str] = Query(None),
    appointment_date: Optional[datetime.date] = Query(None),
    status: Optional[AppointmentStatus] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> List[AppointmentResponse]:
    target_patient_id = patient_id
    target_doctor_id = doctor_id
    target_hospital_id = hospital_id

    # Enforce role boundaries
    if current_user.is_patient:
        patient = patient_repo.get_by_auth_user_id(db, current_user.id)
        target_patient_id = patient.id if patient else "none"
    elif current_user.is_doctor:
        doc = doctor_repo.get_by_profile_id(db, current_user.raw_claims.get("profile_id", ""))
        if not doc:
            # Fallback by doctor profile join
            from app.models.profile import Profile
            from app.models.doctor import Doctor
            doc = db.query(Doctor).join(Profile).filter(Profile.auth_user_id == current_user.id).first()
        target_doctor_id = doc.id if doc else "none"
    elif current_user.is_admin and current_user.hospital_id:
        target_hospital_id = current_user.hospital_id

    return appointment_service.list_appointments(
        db,
        patient_id=target_patient_id,
        doctor_id=target_doctor_id,
        hospital_id=target_hospital_id,
        appointment_date=appointment_date,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{appointment_id}",
    response_model=AppointmentResponse,
    summary="Get Appointment Details",
)
def get_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AppointmentResponse:
    appt = appointment_service.get_appointment(db, appointment_id)

    # Patient can only view their own appointment
    if current_user.is_patient:
        patient = patient_repo.get_by_auth_user_id(db, current_user.id)
        if not patient or patient.id != appt.patient_id:
            raise ForbiddenError(
                message="Access forbidden: you can only access your own appointments",
                code="FORBIDDEN_APPOINTMENT_ACCESS",
            )
    elif current_user.is_doctor:
        from app.models.profile import Profile
        from app.models.doctor import Doctor
        doc = db.query(Doctor).join(Profile).filter(Profile.auth_user_id == current_user.id).first()
        if not doc or doc.id != appt.doctor_id:
            raise ForbiddenError(
                message="Access forbidden: you can only view appointments assigned to you",
                code="FORBIDDEN_DOCTOR_ACCESS",
            )
    elif current_user.is_admin:
        verify_hospital_access(appt.hospital_id, current_user)

    return appt


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentResponse,
    summary="Cancel an Appointment",
)
def cancel_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AppointmentResponse:
    return appointment_service.cancel_appointment(
        db,
        appointment_id,
        actor_auth_user_id=current_user.id,
        is_doctor=current_user.is_doctor,
        is_admin=current_user.is_admin,
    )


@router.post(
    "/{appointment_id}/check-in",
    response_model=QueueEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Check-In for Scheduled Appointment",
    description="Authoritatively checks in an eligible appointment and creates the corresponding QueueEntry with a server-generated token.",
)
def check_in_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> QueueEntryResponse:
    return queue_service.check_in(
        db,
        appointment_id,
        actor_auth_user_id=current_user.id,
        is_doctor=current_user.is_doctor,
        is_admin=current_user.is_admin,
    )

