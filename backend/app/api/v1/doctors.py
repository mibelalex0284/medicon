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
from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.schemas.appointment import DoctorAvailabilityResponse
from app.schemas.doctor import (
    DoctorCreate,
    DoctorResponse,
    DoctorIntakeStatusResponse,
    DoctorIntakeStatusUpdate,
)
from app.schemas.doctor_recommendation import (
    DoctorRecommendationRequest,
    DoctorRecommendationResponse,
)
from app.services.appointment_service import appointment_service
from app.services.doctor_recommendation_service import doctor_recommendation_service
from app.services.doctor_service import doctor_service
from app.services.supabase_admin_service import supabase_admin_service
from app.services.system_setting_service import system_setting_service

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
    docs = doctor_service.list_doctors(
        db,
        hospital_id=hospital_id,
        specialty_id=specialty_id,
        department_id=department_id,
        is_active=True,
        skip=skip,
        limit=limit,
    )
    results: List[DoctorResponse] = []
    for d in docs:
        resp = DoctorResponse.model_validate(d)
        resp.is_accepting_patients = system_setting_service.get_doctor_intake_status(db, d.id)
        results.append(resp)
    return results


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

    docs = doctor_service.list_doctors(
        db,
        hospital_id=effective_hospital,
        specialty_id=specialty_id,
        department_id=department_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )

    users_map = (
        supabase_admin_service.get_all_users_map()
        if supabase_admin_service.is_configured
        else {}
    )

    result: List[DoctorResponse] = []
    for d in docs:
        resp = DoctorResponse.model_validate(d)
        resp.is_accepting_patients = system_setting_service.get_doctor_intake_status(db, d.id)
        if not d.is_active:
            resp.invitation_status = "inactive"
        elif d.profile and d.profile.email:
            email_clean = d.profile.email.strip().lower()
            if email_clean in users_map:
                u = users_map[email_clean]
                if u.get("last_sign_in_at") or u.get("confirmed_at") or u.get("email_confirmed_at"):
                    resp.invitation_status = "active"
                else:
                    resp.invitation_status = "pending"
            else:
                resp.invitation_status = "active"
        result.append(resp)
    return result


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
    resp = DoctorResponse.model_validate(doctor_service.get_doctor(db, doc.id))
    resp.is_accepting_patients = system_setting_service.get_doctor_intake_status(db, doc.id)
    return resp


@router.patch(
    "/me/intake-status",
    response_model=DoctorIntakeStatusResponse,
    summary="Update Current Doctor Clinic Station Intake Status",
    description="Updates the authenticated doctor's clinic station patient intake availability.",
)
def update_current_doctor_intake_status(
    payload: DoctorIntakeStatusUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_doctor),
) -> DoctorIntakeStatusResponse:
    from sqlalchemy import or_
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
    return update_doctor_intake_status(
        doctor_id=doc.id,
        payload=payload,
        db=db,
        current_user=current_user,
    )


@router.patch(
    "/{doctor_id}/intake-status",
    response_model=DoctorIntakeStatusResponse,
    summary="Update Doctor Clinic Station Intake Status",
    description="Updates clinic station patient intake availability (accepting patients vs station paused).",
)
def update_doctor_intake_status(
    doctor_id: str,
    payload: DoctorIntakeStatusUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> DoctorIntakeStatusResponse:
    from app.models.doctor import Doctor
    from app.models.profile import Profile

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise NotFoundError(
            message=f"Doctor with ID '{doctor_id}' not found.",
            code="DOCTOR_NOT_FOUND",
        )

    # Authorization verification:
    # 1. Admin can update intake status for doctors in their hospital
    if current_user.is_admin:
        verify_hospital_access(doctor.hospital_id, current_user)
    # 2. Doctor can only update their own intake status
    elif current_user.is_doctor:
        profile = db.query(Profile).filter(Profile.id == doctor.profile_id).first()
        is_owner = (
            profile
            and (profile.auth_user_id == current_user.id or profile.id == current_user.id)
        )
        if not is_owner:
            raise ForbiddenError(
                message="Access forbidden: You are not authorized to update another physician's intake status.",
                code="FORBIDDEN_DOCTOR_STATUS_UPDATE",
            )
    else:
        raise ForbiddenError(
            message="Insufficient permissions to update doctor intake status.",
            code="INSUFFICIENT_PERMISSIONS",
        )

    # Inactive/deactivated doctors cannot toggle station intake
    if not doctor.is_active:
        raise ForbiddenError(
            message="Cannot update intake availability: this physician account has been deactivated by administration.",
            code="DOCTOR_DEACTIVATED",
        )

    # Authoritatively persist in system_settings
    is_accepting = system_setting_service.set_doctor_intake_status(
        db,
        doctor_id=doctor.id,
        is_accepting=payload.is_accepting_patients,
        updated_by=current_user.id,
    )

    status_label = "Accepting Patients" if is_accepting else "Station Paused"
    msg = f"Clinic station intake status updated to '{status_label}'."
    return DoctorIntakeStatusResponse(
        doctor_id=doctor.id,
        is_accepting_patients=is_accepting,
        status=status_label,
        message=msg,
    )


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
    doc = doctor_service.get_doctor(db, doctor_id)
    resp = DoctorResponse.model_validate(doc)
    resp.is_accepting_patients = system_setting_service.get_doctor_intake_status(db, doc.id)
    return resp


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
