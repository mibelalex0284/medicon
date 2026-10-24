import datetime
import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.dependencies import (
    AuthenticatedUser,
    require_admin,
    verify_hospital_access,
)
from app.core.exceptions import AppException, BadRequestError, ConflictError, InternalServerError, NotFoundError
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.consultation import Consultation
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.doctor_specialty import DoctorSpecialty
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.profile import Profile, UserRole
from app.models.queue_entry import QueueEntry
from app.models.specialty import Specialty
from app.models.system_setting import SystemSetting
from app.schemas.admin_settings import (
    AdminAccountCreatedResponse,
    AdminCreatePatientRequest,
    AdminDoctorLifecycleResponse,
    AdminOnboardDoctorRequest,
    AdminSettingItem,
    AdminSettingsResponse,
    AdminUpdateDoctorStatusRequest,
    UpdatePatientSelfRegistrationRequest,
)
from app.schemas.doctor_schedule import (
    DoctorScheduleBatchUpdate,
    DoctorScheduleResponse,
)
from app.services.supabase_admin_service import supabase_admin_service
from app.services.system_setting_service import system_setting_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


@router.get(
    "/settings",
    response_model=AdminSettingsResponse,
    summary="Get System Settings (Admin Only)",
    description="Retrieves administrative settings, including the patient self-registration toggle.",
)
def get_admin_settings(
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminSettingsResponse:
    enabled = system_setting_service.is_patient_self_registration_enabled(db)
    all_settings = db.query(SystemSetting).all()
    setting_items = [
        AdminSettingItem(
            key=s.key,
            value=s.value,
            description=s.description,
            updated_at=s.updated_at,
            updated_by=s.updated_by,
        )
        for s in all_settings
    ]
    return AdminSettingsResponse(
        patient_self_registration_enabled=enabled,
        settings=setting_items,
    )


@router.patch(
    "/settings/patient-self-registration",
    response_model=AdminSettingsResponse,
    summary="Update Patient Self-Registration Setting (Admin Only)",
    description="Enables or disables public patient self-registration. Enforces administrative credentials.",
)
def update_patient_self_registration(
    payload: UpdatePatientSelfRegistrationRequest,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminSettingsResponse:
    updater_id = admin_user.profile_id or admin_user.id
    system_setting_service.set_patient_self_registration(
        db=db,
        enabled=payload.enabled,
        updated_by=updater_id,
    )
    all_settings = db.query(SystemSetting).all()
    setting_items = [
        AdminSettingItem(
            key=s.key,
            value=s.value,
            description=s.description,
            updated_at=s.updated_at,
            updated_by=s.updated_by,
        )
        for s in all_settings
    ]
    return AdminSettingsResponse(
        patient_self_registration_enabled=payload.enabled,
        settings=setting_items,
    )


@router.post(
    "/patients/register",
    response_model=AdminAccountCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register Patient by Administrator (Admin Only)",
    description=(
        "Allows authorized clinic administrators to register a patient account directly. "
        "Operates independently of public self-registration toggles."
    ),
)
def admin_register_patient(
    payload: AdminCreatePatientRequest,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminAccountCreatedResponse:
    email_clean = payload.email.strip().lower()

    # 1. Enforce unique email check across profiles
    existing_profile = db.query(Profile).filter(Profile.email == email_clean).first()
    if existing_profile:
        raise ConflictError(
            message=f"An account with email '{email_clean}' already exists in the system.",
            code="EMAIL_ALREADY_EXISTS",
        )

    # 2. Check hospital affiliation access if specified
    effective_hospital_id = payload.hospital_id or admin_user.hospital_id
    if effective_hospital_id:
        verify_hospital_access(effective_hospital_id, admin_user)

    # 3. Securely provision Supabase identity or derive UUID
    auth_user_id = payload.auth_user_id
    auth_provisioned = False
    message = "Patient account created successfully."

    if not auth_user_id:
        auth_user_id, auth_provisioned, message = supabase_admin_service.provision_user_identity(
            email=email_clean,
            full_name=payload.full_name,
            role="patient",
        )

    # 4. Transactionally create Profile and Patient records
    try:
        new_profile = Profile(
            auth_user_id=auth_user_id,
            role=UserRole.PATIENT,
            full_name=payload.full_name,
            email=email_clean,
            phone=payload.phone,
            hospital_id=effective_hospital_id,
            is_active=True,
        )
        db.add(new_profile)
        db.flush()

        new_patient = Patient(
            profile_id=new_profile.id,
            date_of_birth=payload.date_of_birth,
            preferred_language=payload.preferred_language,
            emergency_contact=payload.emergency_contact,
            accessibility_notes=payload.accessibility_notes,
        )
        db.add(new_patient)
        db.commit()
        db.refresh(new_profile)
        db.refresh(new_patient)

        logger.info(
            f"Admin {admin_user.id} registered patient: profile_id={new_profile.id}, patient_id={new_patient.id}"
        )

        return AdminAccountCreatedResponse(
            status="created",
            profile_id=new_profile.id,
            auth_user_id=auth_user_id,
            role="patient",
            full_name=new_profile.full_name,
            email=new_profile.email,
            entity_id=new_patient.id,
            auth_provisioned=auth_provisioned,
            message=message,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create patient record: {str(e)}")
        raise


@router.post(
    "/doctors/onboard",
    response_model=AdminAccountCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard Physician by Administrator (Admin Only)",
    description=(
        "Enables authorized administrators to onboard new physicians, assigning license numbers, "
        "department affiliations, and clinical specialties."
    ),
)
def admin_onboard_doctor(
    payload: AdminOnboardDoctorRequest,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminAccountCreatedResponse:
    email_clean = payload.email.strip().lower()

    # 1. Enforce hospital tenant access
    verify_hospital_access(payload.hospital_id, admin_user)

    # 2. Check for duplicate email across all profiles
    existing_profile = db.query(Profile).filter(Profile.email == email_clean).first()
    if existing_profile:
        raise ConflictError(
            message=f"An account with email '{email_clean}' already exists in the system.",
            code="EMAIL_ALREADY_EXISTS",
        )

    # 3. Check for duplicate medical license number
    existing_license = db.query(Doctor).filter(Doctor.license_number == payload.license_number.strip()).first()
    if existing_license:
        raise ConflictError(
            message=f"Physician license number '{payload.license_number}' is already registered.",
            code="LICENSE_ALREADY_REGISTERED",
        )

    # 4. Validate department exists if provided
    if payload.department_id:
        dept = db.query(Department).filter(Department.id == payload.department_id).first()
        if not dept:
            raise NotFoundError(
                message=f"Department with ID '{payload.department_id}' not found.",
                code="DEPARTMENT_NOT_FOUND",
            )

    # 5. Check if user already exists in Supabase Auth with another role
    existing_auth_user = supabase_admin_service.get_user_by_email(email_clean)
    if existing_auth_user:
        metadata_role = (existing_auth_user.get("user_metadata") or {}).get("role")
        if metadata_role in ("patient", "admin"):
            raise ConflictError(
                message=f"An account with email '{email_clean}' already exists in Supabase Auth with role '{metadata_role}'. Existing patients or administrators cannot be silently promoted to a physician.",
                code="CANNOT_PROMOTE_EXISTING_ROLE",
            )

    # 6. Provision identity or invite doctor in Supabase Auth
    auth_user_id = payload.auth_user_id
    auth_provisioned = False
    action_link = None
    is_newly_created = False
    message = "Physician onboarded successfully."

    if not auth_user_id:
        auth_user_id, auth_provisioned, action_link, message, is_newly_created = (
            supabase_admin_service.invite_or_provision_doctor(
                email=email_clean,
                full_name=payload.full_name,
                role="doctor",
            )
        )

    # 7. Transactionally create Profile, Doctor, and DoctorSpecialty records
    try:
        new_profile = Profile(
            auth_user_id=auth_user_id,
            role=UserRole.DOCTOR,
            full_name=payload.full_name,
            email=email_clean,
            phone=payload.phone,
            hospital_id=payload.hospital_id,
            is_active=True,
        )
        db.add(new_profile)
        db.flush()

        new_doctor = Doctor(
            profile_id=new_profile.id,
            hospital_id=payload.hospital_id,
            department_id=payload.department_id,
            license_number=payload.license_number.strip(),
            years_of_experience=payload.years_of_experience,
            consultation_mode=payload.consultation_mode,
            languages=payload.languages,
            is_active=True,
        )
        db.add(new_doctor)
        db.flush()

        # Associate specialties
        for idx, spec_id in enumerate(payload.specialty_ids):
            spec = db.query(Specialty).filter(Specialty.id == spec_id).first()
            if spec:
                is_primary = (
                    spec_id == payload.primary_specialty_id
                    if payload.primary_specialty_id
                    else (idx == 0)
                )
                doc_spec = DoctorSpecialty(
                    doctor_id=new_doctor.id,
                    specialty_id=spec.id,
                    is_primary=is_primary,
                )
                db.add(doc_spec)

        # Initialize standard outpatient consultation schedule (Monday-Friday 09:00 - 17:00, 30 min slots)
        for day in range(0, 5):  # 0=Monday through 4=Friday
            sched = DoctorSchedule(
                doctor_id=new_doctor.id,
                hospital_id=new_doctor.hospital_id,
                day_of_week=day,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(17, 0),
                slot_duration_minutes=30,
                is_active=True,
            )
            db.add(sched)

        db.commit()
        db.refresh(new_profile)
        db.refresh(new_doctor)

        logger.info(
            f"Admin {admin_user.id} onboarded physician: profile_id={new_profile.id}, doctor_id={new_doctor.id}, auth_id={auth_user_id}"
        )

        return AdminAccountCreatedResponse(
            status="created",
            profile_id=new_profile.id,
            auth_user_id=auth_user_id,
            role="doctor",
            full_name=new_profile.full_name,
            email=new_profile.email,
            entity_id=new_doctor.id,
            auth_provisioned=auth_provisioned,
            message=message,
            invitation_sent=bool(action_link),
            action_link=action_link,
        )
    except Exception as e:
        db.rollback()
        if is_newly_created and auth_user_id:
            try:
                supabase_admin_service.delete_user(auth_user_id)
                logger.info(f"Cleaned up orphaned Supabase Auth user {auth_user_id} after DB transaction failure.")
            except Exception as cleanup_err:
                logger.error(f"Failed to cleanup orphaned Auth user: {cleanup_err}")
        logger.error(f"Failed to onboard physician: {str(e)}")
        if isinstance(e, AppException):
            raise
        raise InternalServerError(
            message=f"Database transaction failure during physician onboarding: {str(e)}",
            code="DATABASE_TRANSACTION_FAILED",
        )


@router.patch(
    "/doctors/{doctor_id}/status",
    response_model=AdminDoctorLifecycleResponse,
    summary="Update Doctor Account Status (Admin Only)",
    description="Deactivates or reactivates a doctor account. Enforces tenant boundaries and audit logging.",
)
def update_doctor_status(
    doctor_id: str,
    payload: AdminUpdateDoctorStatusRequest,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminDoctorLifecycleResponse:
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise NotFoundError(
            message=f"Doctor with ID '{doctor_id}' not found.",
            code="DOCTOR_NOT_FOUND",
        )

    # Verify hospital tenant boundary
    verify_hospital_access(doctor.hospital_id, admin_user)

    profile = db.query(Profile).filter(Profile.id == doctor.profile_id).first()

    old_status = doctor.is_active
    doctor.is_active = payload.is_active
    if profile:
        profile.is_active = payload.is_active

    db.commit()
    db.refresh(doctor)
    if profile:
        db.refresh(profile)

    action = "REACTIVATE" if payload.is_active else "DEACTIVATE"
    status_str = "active" if payload.is_active else "deactivated"
    logger.info(
        f"AUDIT: Admin {admin_user.id} ({admin_user.email}) performed {action} on doctor {doctor.id} "
        f"(profile={doctor.profile_id}). PrevStatus={old_status}, NewStatus={payload.is_active}. "
        f"Reason: {payload.reason or 'Not specified'}"
    )

    return AdminDoctorLifecycleResponse(
        doctor_id=doctor.id,
        profile_id=doctor.profile_id,
        full_name=profile.full_name if profile else "Unknown Physician",
        email=profile.email if profile else "",
        is_active=doctor.is_active,
        status=status_str,
        message=f"Physician account successfully {status_str}.",
    )


@router.delete(
    "/doctors/{doctor_id}",
    response_model=AdminDoctorLifecycleResponse,
    summary="Delete Doctor Record (Admin Only, Zero Dependent Records Only)",
    description=(
        "Safely deletes an unused physician record. Strictly prevents deletion if dependent "
        "appointments, consultations, or queue records exist, requiring deactivation instead."
    ),
)
def delete_doctor(
    doctor_id: str,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminDoctorLifecycleResponse:
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise NotFoundError(
            message=f"Doctor with ID '{doctor_id}' not found.",
            code="DOCTOR_NOT_FOUND",
        )

    # Verify hospital tenant boundary
    verify_hospital_access(doctor.hospital_id, admin_user)

    # Inspect dependent clinical history
    appts_count = db.query(Appointment).filter(Appointment.doctor_id == doctor_id).count()
    consults_count = db.query(Consultation).filter(Consultation.doctor_id == doctor_id).count()
    queues_count = db.query(QueueEntry).filter(QueueEntry.doctor_id == doctor_id).count()

    if appts_count > 0 or consults_count > 0 or queues_count > 0:
        raise ConflictError(
            message=(
                f"Physician cannot be permanently deleted because dependent clinical records exist "
                f"({appts_count} appointments, {consults_count} consultations, {queues_count} queue entries). "
                "In compliance with healthcare data retention policies, deactivation must be used instead to "
                "preserve clinical and audit records."
            ),
            code="CANNOT_DELETE_DOCTOR_WITH_CLINICAL_HISTORY",
        )

    profile = db.query(Profile).filter(Profile.id == doctor.profile_id).first()
    profile_id = doctor.profile_id
    full_name = profile.full_name if profile else "Unknown Physician"
    email = profile.email if profile else ""
    auth_user_id = profile.auth_user_id if profile else None

    try:
        # Clean up specialty associations and schedules
        db.query(DoctorSpecialty).filter(DoctorSpecialty.doctor_id == doctor_id).delete()
        db.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doctor_id).delete()

        db.delete(doctor)
        if profile:
            db.delete(profile)
        db.commit()

        # Clean up Supabase Auth user if applicable
        if auth_user_id:
            supabase_admin_service.delete_user(auth_user_id)

        logger.info(
            f"AUDIT: Admin {admin_user.id} permanently deleted doctor {doctor_id} "
            f"(profile={profile_id}, email={email}) with zero dependent clinical records."
        )

        return AdminDoctorLifecycleResponse(
            doctor_id=doctor_id,
            profile_id=profile_id,
            full_name=full_name,
            email=email,
            is_active=False,
            status="deleted",
            message="Physician record and credentials permanently deleted successfully.",
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete doctor {doctor_id}: {str(e)}")
        raise


@router.get(
    "/doctors/{doctor_id}/schedules",
    response_model=List[DoctorScheduleResponse],
    summary="Get Doctor Consultation Schedules (Admin Only)",
    description="Retrieves all configured weekly consultation schedules for a specific physician.",
)
def get_admin_doctor_schedules(
    doctor_id: str,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> List[DoctorScheduleResponse]:
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise NotFoundError(
            message=f"Doctor with ID '{doctor_id}' not found.",
            code="DOCTOR_NOT_FOUND",
        )
    verify_hospital_access(doctor.hospital_id, admin_user)
    return (
        db.query(DoctorSchedule)
        .filter(DoctorSchedule.doctor_id == doctor_id)
        .order_by(DoctorSchedule.day_of_week, DoctorSchedule.start_time)
        .all()
    )


@router.put(
    "/doctors/{doctor_id}/schedules",
    response_model=List[DoctorScheduleResponse],
    summary="Configure Doctor Consultation Schedules (Admin Only)",
    description="Sets or updates weekly consultation schedule slots for a physician.",
)
def update_admin_doctor_schedules(
    doctor_id: str,
    payload: DoctorScheduleBatchUpdate,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> List[DoctorScheduleResponse]:
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise NotFoundError(
            message=f"Doctor with ID '{doctor_id}' not found.",
            code="DOCTOR_NOT_FOUND",
        )
    verify_hospital_access(doctor.hospital_id, admin_user)

    try:
        # Delete existing schedules for this doctor
        db.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doctor_id).delete()

        created_schedules = []
        for sched_in in payload.schedules:
            new_sched = DoctorSchedule(
                doctor_id=doctor.id,
                hospital_id=doctor.hospital_id,
                day_of_week=sched_in.day_of_week,
                start_time=sched_in.start_time,
                end_time=sched_in.end_time,
                slot_duration_minutes=sched_in.slot_duration_minutes,
                is_active=sched_in.is_active,
            )
            db.add(new_sched)
            created_schedules.append(new_sched)

        db.commit()

        updated = (
            db.query(DoctorSchedule)
            .filter(DoctorSchedule.doctor_id == doctor_id)
            .order_by(DoctorSchedule.day_of_week, DoctorSchedule.start_time)
            .all()
        )
        logger.info(
            f"Admin {admin_user.id} updated consultation schedules for doctor {doctor_id} "
            f"({len(updated)} schedule windows configured)."
        )
        return updated
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update consultation schedules for doctor {doctor_id}: {str(e)}")
        raise

