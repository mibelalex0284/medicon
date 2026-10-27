import datetime
import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.dependencies import (
    AuthenticatedUser,
    require_admin,
    verify_hospital_access,
)
from app.core.exceptions import AppException, BadRequestError, ConflictError, InternalServerError, NotFoundError
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentStatus
from app.models.consultation import Consultation, ConsultationStatus
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.doctor_specialty import DoctorSpecialty
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.profile import Profile, UserRole
from app.models.queue_entry import QueueEntry, QueueStatus
from app.models.specialty import Specialty
from app.models.system_setting import SystemSetting
from app.schemas.admin_settings import (
    AdminAccountCreatedResponse,
    AdminAnalyticsOverviewResponse,
    AdminCreatePatientRequest,
    AdminDoctorLifecycleResponse,
    AdminOnboardDoctorRequest,
    AdminResendInvitationResponse,
    AdminSettingItem,
    AdminSettingsResponse,
    AdminUpdateDoctorStatusRequest,
    DepartmentMetricResponse,
    HourlyMetricResponse,
    UpdatePatientSelfRegistrationRequest,
)
from app.schemas.doctor_schedule import (
    DoctorScheduleBatchUpdate,
    DoctorScheduleResponse,
)
from app.services.doctor_service import doctor_service
from app.services.supabase_admin_service import supabase_admin_service
from app.services.system_setting_service import system_setting_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Portal"])


@router.get(
    "/analytics/overview",
    response_model=AdminAnalyticsOverviewResponse,
    summary="Get Clinic Operational Analytics Overview (Admin Only)",
    description="Aggregates live operational queue, wait times, department loads, and throughput from actual database records.",
)
def get_admin_analytics_overview(
    hospital_id: Optional[str] = Query(None, description="Optional hospital ID to filter by"),
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminAnalyticsOverviewResponse:
    effective_hospital = hospital_id or admin_user.hospital_id
    if effective_hospital:
        verify_hospital_access(effective_hospital, admin_user)

    today = datetime.date.today()

    # Base queries scoped to hospital if specified
    q_filter = [QueueEntry.queue_date == today]
    apt_filter = [Appointment.appointment_date == today]
    doc_filter = [Doctor.is_active == True]
    dept_filter = [Department.is_active == True]

    if effective_hospital:
        q_filter.append(QueueEntry.hospital_id == effective_hospital)
        apt_filter.append(Appointment.hospital_id == effective_hospital)
        doc_filter.append(Doctor.hospital_id == effective_hospital)
        dept_filter.append(Department.hospital_id == effective_hospital)

    # 1. Fetch today's queue entries and appointments
    queue_entries: List[QueueEntry] = db.query(QueueEntry).filter(*q_filter).all()
    today_appointments: List[Appointment] = db.query(Appointment).filter(*apt_filter).all()

    # Total unique patients today
    patient_ids = set()
    for qe in queue_entries:
        patient_ids.add(qe.patient_id)
    for apt in today_appointments:
        patient_ids.add(apt.patient_id)
    total_patients_today = len(patient_ids)

    # Counts by queue status
    active_statuses = {QueueStatus.WAITING, QueueStatus.CALLED, QueueStatus.CHECKED_IN}
    active_queue_count = sum(1 for qe in queue_entries if qe.status in active_statuses)
    in_consultation_count = sum(1 for qe in queue_entries if qe.status == QueueStatus.IN_CONSULTATION)
    completed_today = sum(1 for qe in queue_entries if qe.status == QueueStatus.COMPLETED)

    # Wait times: calculated for entries where called_at is present
    wait_minutes_list: List[float] = []
    urgent_wait_count = 0
    urgent_delayed_count = 0

    for qe in queue_entries:
        if qe.called_at and qe.checked_in_at:
            wait_secs = (qe.called_at - qe.checked_in_at).total_seconds()
            if wait_secs >= 0:
                mins = wait_secs / 60.0
                wait_minutes_list.append(mins)
                is_urgent = False
                if qe.appointment and qe.appointment.reason:
                    r_lower = qe.appointment.reason.lower()
                    if "urgent" in r_lower or "emergency" in r_lower:
                        is_urgent = True
                if is_urgent:
                    urgent_wait_count += 1
                    if mins > 15.0:
                        urgent_delayed_count += 1

    if wait_minutes_list:
        mean_wait_minutes = round(sum(wait_minutes_list) / len(wait_minutes_list), 1)
        sorted_waits = sorted(wait_minutes_list)
        p90_idx = int((len(sorted_waits) - 1) * 0.9)
        p90_wait_minutes = round(sorted_waits[p90_idx], 1)
    else:
        mean_wait_minutes = 0.0
        p90_wait_minutes = 0.0

    urgent_delay_rate = (
        round((urgent_delayed_count / urgent_wait_count) * 100.0, 1)
        if urgent_wait_count > 0
        else 0.0
    )

    # Doctor utilization and punctuality
    active_doctors: List[Doctor] = db.query(Doctor).filter(*doc_filter).all()
    num_active_doctors = len(active_doctors)
    if num_active_doctors > 0 and (in_consultation_count > 0 or completed_today > 0):
        doc_utilization = min(
            100.0,
            round(((in_consultation_count * 1.5 + completed_today) / max(1.0, num_active_doctors * 6.0)) * 100.0, 1),
        )
    else:
        doc_utilization = 0.0

    punctual_count = 0
    checked_in_appts = 0
    for qe in queue_entries:
        if qe.appointment and qe.appointment.scheduled_start and qe.checked_in_at:
            checked_in_appts += 1
            checkin_time = qe.checked_in_at.time()
            sched_time = qe.appointment.scheduled_start
            delta_mins = abs(
                (checkin_time.hour * 60 + checkin_time.minute)
                - (sched_time.hour * 60 + sched_time.minute)
            )
            if delta_mins <= 15:
                punctual_count += 1

    punctuality_rate = (
        round((punctual_count / checked_in_appts) * 100.0, 1)
        if checked_in_appts > 0
        else 100.0 if total_patients_today == 0 else 0.0
    )

    # 2. Department metrics
    departments = db.query(Department).filter(*dept_filter).all()
    dept_metrics: List[DepartmentMetricResponse] = []

    for dept in departments:
        dept_docs = [d for d in active_doctors if d.department_id == dept.id]
        dept_doc_ids = {d.id for d in dept_docs}

        dept_entries = [qe for qe in queue_entries if qe.doctor_id in dept_doc_ids]
        dept_waiting = sum(1 for qe in dept_entries if qe.status in active_statuses)

        dept_waits = []
        dept_urgent = 0
        for qe in dept_entries:
            if qe.called_at and qe.checked_in_at:
                w_sec = (qe.called_at - qe.checked_in_at).total_seconds()
                if w_sec >= 0:
                    dept_waits.append(w_sec / 60.0)
            if qe.appointment and qe.appointment.reason:
                r = qe.appointment.reason.lower()
                if "urgent" in r or "emergency" in r:
                    dept_urgent += 1

        if dept_waits:
            dept_mean = round(sum(dept_waits) / len(dept_waits), 1)
            sorted_dw = sorted(dept_waits)
            d_p90 = round(sorted_dw[int((len(sorted_dw) - 1) * 0.9)], 1)
        else:
            dept_mean = 0.0
            d_p90 = 0.0

        bottleneck = None
        if dept_waiting > 8:
            bottleneck = f"High intake volume ({dept_waiting} waiting)"
        elif dept_waiting > 0 and len(dept_docs) == 0:
            bottleneck = "No active physicians assigned"

        dept_metrics.append(
            DepartmentMetricResponse(
                id=dept.id,
                name=dept.name,
                code=dept.code,
                active_doctors=len(dept_docs),
                total_waiting=dept_waiting,
                mean_wait_minutes=dept_mean,
                p90_wait_minutes=d_p90,
                urgent_cases_count=dept_urgent,
                current_bottleneck=bottleneck,
            )
        )

    # 3. Hourly Flow (08:00 to 17:00)
    hourly_flow: List[HourlyMetricResponse] = []
    hourly_arrivals = {h: 0 for h in range(8, 18)}
    hourly_completed = {h: 0 for h in range(8, 18)}

    for qe in queue_entries:
        if qe.checked_in_at:
            h = qe.checked_in_at.hour
            if h in hourly_arrivals:
                hourly_arrivals[h] += 1
        if qe.completed_at:
            h = qe.completed_at.hour
            if h in hourly_completed:
                hourly_completed[h] += 1

    for h in range(8, 18):
        hourly_flow.append(
            HourlyMetricResponse(
                hour=f"{h:02d}:00",
                arrivals=hourly_arrivals[h],
                completed=hourly_completed[h],
            )
        )

    return AdminAnalyticsOverviewResponse(
        total_patients_today=total_patients_today,
        active_queue_count=active_queue_count,
        in_consultation_count=in_consultation_count,
        completed_today=completed_today,
        mean_wait_minutes=mean_wait_minutes,
        p90_wait_minutes=p90_wait_minutes,
        urgent_delay_rate=urgent_delay_rate,
        doctor_utilization_rate=doc_utilization,
        punctuality_rate=punctuality_rate,
        departments=dept_metrics,
        hourly_flow=hourly_flow,
    )


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

    # 5. Check if user already exists in Supabase Auth with another role or existing profile
    if payload.auth_user_id:
        existing_profile_by_auth = (
            db.query(Profile).filter(Profile.auth_user_id == payload.auth_user_id).first()
        )
        if existing_profile_by_auth:
            raise ConflictError(
                message=f"The provided auth_user_id '{payload.auth_user_id}' is already linked to another profile in the database.",
                code="AUTH_USER_ALREADY_LINKED",
            )

    existing_auth_user = supabase_admin_service.get_user_by_email(email_clean)
    if existing_auth_user:
        auth_id = existing_auth_user.get("id")
        if auth_id:
            existing_profile_by_auth = (
                db.query(Profile).filter(Profile.auth_user_id == auth_id).first()
            )
            if existing_profile_by_auth:
                raise ConflictError(
                    message=f"The Supabase Auth identity for '{email_clean}' is already linked to an existing profile.",
                    code="AUTH_USER_ALREADY_LINKED",
                )
        metadata_role = (existing_auth_user.get("user_metadata") or {}).get("role")
        if metadata_role in ("patient", "admin"):
            raise ConflictError(
                message=f"An account with email '{email_clean}' already exists in Supabase Auth with role '{metadata_role}'. Existing patients or administrators cannot be silently promoted to a physician.",
                code="CANNOT_PROMOTE_EXISTING_ROLE",
            )
        raise ConflictError(
            message=f"An account with email '{email_clean}' already exists in Supabase Auth. Existing accounts cannot be overwritten with a new password during onboarding.",
            code="AUTH_USER_ALREADY_EXISTS",
        )

    # 6. Provision identity in Supabase Auth with administrator-provided password
    auth_user_id = payload.auth_user_id
    auth_provisioned = False
    action_link = None
    is_newly_created = False
    message = "Physician onboarded successfully."

    if not auth_user_id:
        auth_user_id, auth_provisioned, message, is_newly_created = (
            supabase_admin_service.create_doctor_user(
                email=email_clean,
                password=payload.password,
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

        # Initialize standard outpatient consultation schedule via DoctorService (safe transaction)
        doctor_service.create_default_schedules(db, new_doctor.id, overwrite=False)

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


@router.post(
    "/doctors/{doctor_id}/resend-invitation",
    response_model=AdminResendInvitationResponse,
    summary="Resend Physician Invitation (Admin Only)",
    description=(
        "Safely regenerates a secure invitation or password-setup link for an existing doctor "
        "without generating duplicate Auth records."
    ),
)
def resend_doctor_invitation(
    doctor_id: str,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> AdminResendInvitationResponse:
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise NotFoundError(
            message=f"Doctor with ID '{doctor_id}' not found.",
            code="DOCTOR_NOT_FOUND",
        )

    # Verify hospital tenant access
    verify_hospital_access(doctor.hospital_id, admin_user)

    profile = db.query(Profile).filter(Profile.id == doctor.profile_id).first()
    if not profile:
        raise NotFoundError(
            message=f"Profile associated with doctor '{doctor_id}' not found.",
            code="PROFILE_NOT_FOUND",
        )

    action_link, message, auth_provisioned = supabase_admin_service.resend_or_generate_invitation(
        email=profile.email,
        full_name=profile.full_name,
    )

    logger.info(
        f"AUDIT: Admin {admin_user.id} ({admin_user.email}) resent invitation for doctor {doctor.id} "
        f"({profile.email}). Provisioned: {auth_provisioned}"
    )

    return AdminResendInvitationResponse(
        doctor_id=doctor.id,
        profile_id=profile.id,
        full_name=profile.full_name,
        email=profile.email,
        action_link=action_link,
        message=message,
        auth_provisioned=auth_provisioned,
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


@router.post(
    "/doctors/{doctor_id}/schedules/initialize-default",
    response_model=List[DoctorScheduleResponse],
    summary="Initialize Default Doctor Schedules (Admin Only)",
    description="Initializes standard outpatient consultation hours (Mon-Fri 09:00 - 17:00, 30 min slots) for a physician. Idempotent.",
)
def initialize_doctor_default_schedule(
    doctor_id: str,
    overwrite: bool = False,
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
        schedules = doctor_service.create_default_schedules(
            db, doctor_id=doctor.id, overwrite=overwrite
        )
        db.commit()
        logger.info(
            f"Admin {admin_user.id} initialized default schedules for doctor {doctor_id} ({len(schedules)} slots)."
        )
        return (
            db.query(DoctorSchedule)
            .filter(DoctorSchedule.doctor_id == doctor_id)
            .order_by(DoctorSchedule.day_of_week, DoctorSchedule.start_time)
            .all()
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to initialize default schedules for doctor {doctor_id}: {str(e)}")
        raise


@router.post(
    "/doctors/repair-schedules",
    summary="Repair Unscheduled Doctors (Admin Only)",
    description="Identifies active doctors lacking schedules and optionally initializes default weekday schedules. Safe and idempotent.",
)
def repair_doctor_schedules(
    hospital_id: Optional[str] = None,
    dry_run: bool = False,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
):
    target_hospital = hospital_id or admin_user.hospital_id
    if target_hospital:
        verify_hospital_access(target_hospital, admin_user)
    return doctor_service.repair_unscheduled_doctors(
        db, hospital_id=target_hospital, dry_run=dry_run
    )


