import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser, get_current_user
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError
from app.db.session import get_db
from app.models.patient import Patient
from app.models.profile import Profile, UserRole
from app.schemas.admin_settings import RegistrationStatusResponse
from app.schemas.auth import (
    AuthMeResponse,
    PatientProfileCompletionRequest,
    ProfileCompletionResponse,
)
from app.services.system_setting_service import system_setting_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get(
    "/registration-status",
    response_model=RegistrationStatusResponse,
    summary="Get Public Registration Status",
    description="Public endpoint to check if patient self-registration is currently enabled by clinic administration.",
)
def get_registration_status(
    db: Session = Depends(get_db),
) -> RegistrationStatusResponse:
    enabled = system_setting_service.is_patient_self_registration_enabled(db)
    return RegistrationStatusResponse(patient_self_registration_enabled=enabled)


@router.get(
    "/me",
    response_model=AuthMeResponse,
    summary="Get Authentication Identity & Profile Status",
    description="Resolves verified Supabase identity, application profile mapping, and active role.",
)
def get_auth_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthMeResponse:
    return AuthMeResponse(
        auth_user_id=current_user.id,
        has_profile=current_user.has_profile,
        role=current_user.role,
        profile_id=current_user.profile_id,
        email=current_user.email,
        hospital_id=current_user.hospital_id,
        is_active=current_user.is_active,
    )


@router.post(
    "/complete-patient-profile",
    response_model=ProfileCompletionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Complete Patient Profile Registration",
    description=(
        "Transactionally creates a patient profile for a newly authenticated Supabase user. "
        "User ID is derived strictly from the verified token. Only the PATIENT role is permitted."
    ),
)
def complete_patient_profile(
    payload: PatientProfileCompletionRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ProfileCompletionResponse:
    # 0. Enforce admin-controlled registration setting - prevent direct API bypass
    if not system_setting_service.is_patient_self_registration_enabled(db):
        raise ForbiddenError(
            message="Public patient registration is currently disabled by clinic administration.",
            code="REGISTRATION_DISABLED",
        )

    # 1. Reject duplicate profile registration for this auth user ID
    existing_profile = (
        db.query(Profile).filter(Profile.auth_user_id == current_user.id).first()
    )

    if existing_profile:
        raise ConflictError(
            message="A profile already exists for this authenticated user account",
            code="PROFILE_ALREADY_EXISTS",
        )

    # 2. Derive email from verified token or provided contact payload
    email = (
        payload.email
        or current_user.email
        or current_user.raw_claims.get("email")
    )
    if not email:
        raise BadRequestError(
            message="Email address is required to complete profile registration",
            code="EMAIL_REQUIRED",
        )

    # Check for duplicate email across profiles
    existing_email_profile = (
        db.query(Profile).filter(Profile.email == str(email).lower()).first()
    )
    if existing_email_profile:
        raise ConflictError(
            message="A profile with this email address already exists",
            code="EMAIL_ALREADY_EXISTS",
        )

    # 3. Transactionally create Profile and Patient records with atomic rollback
    try:
        new_profile = Profile(
            auth_user_id=current_user.id,
            role=UserRole.PATIENT,  # Enforce patient role strictly - no privilege escalation
            full_name=payload.full_name,
            phone=payload.phone,
            email=str(email).lower(),
            hospital_id=payload.hospital_id,
            is_active=True,
        )
        db.add(new_profile)
        db.flush()  # Flushes to generate new_profile.id without committing

        new_patient = Patient(
            profile_id=new_profile.id,
            date_of_birth=payload.date_of_birth,
            preferred_language=payload.preferred_language or "en",
            emergency_contact=payload.emergency_contact,
            accessibility_notes=payload.accessibility_notes,
        )
        db.add(new_patient)
        db.commit()
        db.refresh(new_profile)
        db.refresh(new_patient)

        logger.info(
            f"Successfully completed patient profile registration: "
            f"auth_user_id={current_user.id}, profile_id={new_profile.id}, patient_id={new_patient.id}"
        )

        return ProfileCompletionResponse(
            status="completed",
            profile_id=new_profile.id,
            patient_id=new_patient.id,
            role=new_profile.role.value,
            full_name=new_profile.full_name,
            email=new_profile.email,
            date_of_birth=new_patient.date_of_birth,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to complete patient profile transaction: {str(e)}")
        raise
