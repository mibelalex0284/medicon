import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.dependencies import (
    AuthenticatedUser,
    get_current_user,
    require_admin,
    require_doctor,
    verify_hospital_access,
)
from app.db.session import get_db
from app.schemas.appointment import DoctorAvailabilityResponse
from app.schemas.doctor import DoctorCreate, DoctorResponse
from app.schemas.doctor_recommendation import (
    DoctorRecommendationRequest,
    DoctorRecommendationResponse,
)
from app.services.appointment_service import appointment_service
from app.services.doctor_recommendation_service import doctor_recommendation_service
from app.services.doctor_service import doctor_service

router = APIRouter(tags=["Doctors"])


@router.get(
    "",
    response_model=List[DoctorResponse],
    summary="List Doctors",
    description="Retrieves a list of doctors with optional filtering by hospital, department, or specialty.",
)
def list_doctors(
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    specialty_id: Optional[str] = Query(None, description="Filter by specialty ID"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[DoctorResponse]:
    return doctor_service.list_doctors(
        db,
        hospital_id=hospital_id,
        specialty_id=specialty_id,
        department_id=department_id,
        is_active=True,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/admin/list",
    response_model=List[DoctorResponse],
    summary="List Registered Doctors (Admin Only)",
    description="Securely retrieves all registered doctor records for administration. Enforces admin role.",
)
def list_doctors_admin(
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    status: Optional[str] = Query(None, description="Filter by status: 'active', 'inactive', or 'all'"),
    specialty_id: Optional[str] = Query(None, description="Filter by specialty ID"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> List[DoctorResponse]:
    effective_hospital = hospital_id or admin_user.hospital_id
    is_active: Optional[bool] = None
    if status == "active":
        is_active = True
    elif status == "inactive":
        is_active = False

    return doctor_service.list_doctors(
        db,
        hospital_id=effective_hospital,
        specialty_id=specialty_id,
        department_id=department_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/recommend",
    response_model=DoctorRecommendationResponse,
    summary="Explainable Doctor Recommendation & Ranking",
    description=(
        "Recommends and ranks eligible doctors for a given clinical specialty or triage session. "
        "Applies two-stage hard eligibility filtering followed by deterministic explainable scoring."
    ),
)
@router.post(
    "/match",
    response_model=DoctorRecommendationResponse,
    include_in_schema=False,
    summary="Doctor Matching Alias",
)
def recommend_doctors(
    request: DoctorRecommendationRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DoctorRecommendationResponse:
    return doctor_recommendation_service.recommend_doctors(
        db=db,
        request=request,
        current_user=current_user,
    )


@router.get(
    "/me",
    response_model=DoctorResponse,
    summary="Get Current Doctor Profile",
    description="Securely retrieves the doctor profile for the currently authenticated doctor user.",
)
def get_current_doctor(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_doctor),
) -> DoctorResponse:
    from sqlalchemy import or_
    from app.core.exceptions import ForbiddenError
    from app.models.doctor import Doctor
    from app.models.profile import Profile

    doc = (
        db.query(Doctor)
        .join(Profile, Doctor.profile_id == Profile.id)
        .filter(or_(Profile.auth_user_id == current_user.id, Profile.id == current_user.id))
        .first()
    )
    if not doc:
        raise ForbiddenError(
            message="No registered doctor record found for your user account",
            code="DOCTOR_RECORD_NOT_FOUND",
        )
    if not doc.is_active:
        raise ForbiddenError(
            message="Doctor account has been deactivated by clinic administration.",
            code="DOCTOR_DEACTIVATED",
        )
    return doctor_service.get_doctor(db, doc.id)


@router.get(
    "/{doctor_id}",
    response_model=DoctorResponse,
    summary="Get Doctor Details",
    description="Retrieves comprehensive details for a specific doctor, including specialties and hospital affiliation.",
)
def get_doctor(
    doctor_id: str,
    db: Session = Depends(get_db),
) -> DoctorResponse:
    return doctor_service.get_doctor(db, doctor_id)


@router.get(
    "/{doctor_id}/availability",
    response_model=DoctorAvailabilityResponse,
    summary="Get Doctor Available Slots",
    description="Calculates concrete appointment slots for a requested date based on doctor's schedule and existing bookings.",
)
def get_doctor_availability(
    doctor_id: str,
    appointment_date: datetime.date = Query(..., description="Date to check availability for (YYYY-MM-DD)"),
    slot_duration_minutes: Optional[int] = Query(None, description="Optional custom slot duration in minutes"),
    db: Session = Depends(get_db),
) -> DoctorAvailabilityResponse:
    return appointment_service.get_doctor_availability(
        db,
        doctor_id=doctor_id,
        requested_date=appointment_date,
        slot_duration_minutes=slot_duration_minutes,
    )


@router.post(
    "",
    response_model=DoctorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Doctor (Admin Only)",
    description="Registers a new doctor profile within the system. Enforces tenant boundaries.",
)
def create_doctor(
    doctor_in: DoctorCreate,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> DoctorResponse:
    verify_hospital_access(doctor_in.hospital_id, admin_user)
    return doctor_service.create_doctor(db, doctor_in)
