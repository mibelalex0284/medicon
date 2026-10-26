import datetime
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.appointment import Appointment, AppointmentStatus
from app.models.consultation import Consultation, ConsultationStatus
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.profile import Profile, UserRole
from app.models.queue_entry import QueueEntry, QueueStatus
from app.core.security import create_access_token


def test_admin_list_doctors_unauthenticated(client: TestClient):
    """GET /api/v1/doctors/admin/list must reject unauthenticated requests with 401."""
    response = client.get("/api/v1/doctors/admin/list")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "AUTHORIZATION_HEADER_MISSING"


def test_admin_list_doctors_forbidden_for_patient(client: TestClient, patient_headers: dict):
    """GET /api/v1/doctors/admin/list must reject patients with 403."""
    response = client.get("/api/v1/doctors/admin/list", headers=patient_headers)
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"


def test_admin_list_doctors_forbidden_for_doctor(client: TestClient, doctor_headers: dict):
    """GET /api/v1/doctors/admin/list must reject doctors without admin role with 403."""
    response = client.get("/api/v1/doctors/admin/list", headers=doctor_headers)
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"


def test_admin_list_doctors_authorized_for_admin(client: TestClient, auth_seeded_db, admin_headers: dict):
    """GET /api/v1/doctors/admin/list succeeds for authorized administrators."""
    response = client.get("/api/v1/doctors/admin/list", headers=admin_headers)
    assert response.status_code == 200
    doctors = response.json()
    assert isinstance(doctors, list)
    for doc in doctors:
        assert "id" in doc
        assert "profile" in doc
        assert "full_name" in doc["profile"]
        assert "email" in doc["profile"]
        assert "license_number" in doc
        assert "is_active" in doc
        assert "specialties" in doc


def test_admin_onboard_doctor_password_provisioning_success(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """Admin onboards doctor with password, verifying UUID linkage, doctor role, and lack of password persistence."""
    unique_suffix = str(uuid.uuid4())[:8]
    payload = {
        "full_name": f"Dr. Elena Rostova {unique_suffix}",
        "email": f"elena.rostova.{unique_suffix}@hospital.org",
        "password": "SecurePassword123!",
        "license_number": f"LIC-ELENA-{unique_suffix}",
        "hospital_id": "hosp-001",
        "years_of_experience": 10,
        "consultation_mode": "both",
        "languages": "en, ru",
        "phone": "+1-555-0199",
    }

    response = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["status"] == "created"
    assert data["role"] == "doctor"
    assert data["email"] == payload["email"]
    assert data["auth_user_id"] is not None
    assert data["invitation_sent"] is False
    assert data["action_link"] is None

    # Verify database records
    profile = auth_seeded_db.query(Profile).filter(Profile.id == data["profile_id"]).first()
    assert profile is not None
    assert profile.role == UserRole.DOCTOR
    assert profile.auth_user_id == data["auth_user_id"]
    assert profile.is_active is True
    # Password must NEVER be persisted in PostgreSQL tables
    assert not hasattr(profile, "password") or getattr(profile, "password", None) is None

    doctor = auth_seeded_db.query(Doctor).filter(Doctor.id == data["entity_id"]).first()
    assert doctor is not None
    assert doctor.license_number == payload["license_number"]
    assert doctor.is_active is True
    assert not hasattr(doctor, "password") or getattr(doctor, "password", None) is None


def test_admin_onboard_doctor_password_validation_rules(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """Rejects onboarding when password is missing or shorter than eight characters."""
    base_payload = {
        "full_name": "Dr. Validation Test",
        "email": "validation.doc@hospital.org",
        "license_number": "LIC-VAL-001",
        "hospital_id": "hosp-001",
    }

    # 1. Missing password
    res_missing = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=base_payload)
    assert res_missing.status_code == 422

    # 2. Short password (< 8 chars)
    payload_short = {**base_payload, "password": "short"}
    res_short = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload_short)
    assert res_short.status_code == 422


def test_admin_onboard_doctor_reject_existing_auth_user(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """When an Auth user already exists in Supabase, rejects onboarding rather than overwriting password."""
    existing_auth_uuid = str(uuid.uuid4())
    unique_email = f"existing.auth.{str(uuid.uuid4())[:8]}@hospital.org"

    # Mock Supabase admin service to return existing auth user
    with patch(
        "app.services.supabase_admin_service.supabase_admin_service.get_user_by_email",
        return_value={"id": existing_auth_uuid, "user_metadata": {"role": "doctor"}},
    ):
        payload = {
            "full_name": "Dr. Existing Auth",
            "email": unique_email,
            "password": "SecurePassword123!",
            "license_number": f"LIC-AUTH-{str(uuid.uuid4())[:8]}",
            "hospital_id": "hosp-001",
            "years_of_experience": 7,
            "consultation_mode": "video",
            "languages": "en",
        }
        response = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload)
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "AUTH_USER_ALREADY_EXISTS"


def test_admin_onboard_doctor_reject_existing_patient_or_admin(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """Prevents silently converting an existing patient or admin into a doctor."""
    with patch(
        "app.services.supabase_admin_service.supabase_admin_service.get_user_by_email",
        return_value={"id": "existing-pat-uuid", "user_metadata": {"role": "patient"}},
    ):
        payload = {
            "full_name": "Infiltrator Doctor",
            "email": "existing.patient@example.com",
            "password": "SecurePassword123!",
            "license_number": "LIC-ATTEMPT-01",
            "hospital_id": "hosp-001",
        }
        response = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload)
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "CANNOT_PROMOTE_EXISTING_ROLE"


def test_admin_onboard_doctor_duplicate_email_or_license(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """Rejects onboarding when email or medical license is already registered."""
    unique_email = f"dup.check.{str(uuid.uuid4())[:8]}@hospital.org"
    license_no = f"LIC-DUP-{str(uuid.uuid4())[:8]}"

    payload1 = {
        "full_name": "Dr. First",
        "email": unique_email,
        "password": "SecurePassword123!",
        "license_number": license_no,
        "hospital_id": "hosp-001",
    }
    res1 = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload1)
    assert res1.status_code == 201

    # Attempt duplicate email
    payload_dup_email = {
        "full_name": "Dr. Duplicate Email",
        "email": unique_email,
        "password": "SecurePassword123!",
        "license_number": f"LIC-DIFF-{str(uuid.uuid4())[:8]}",
        "hospital_id": "hosp-001",
    }
    res2 = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload_dup_email)
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    # Attempt duplicate license
    payload_dup_license = {
        "full_name": "Dr. Duplicate License",
        "email": f"diff.email.{str(uuid.uuid4())[:8]}@hospital.org",
        "password": "SecurePassword123!",
        "license_number": license_no,
        "hospital_id": "hosp-001",
    }
    res3 = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload_dup_license)
    assert res3.status_code == 409
    assert res3.json()["error"]["code"] == "LICENSE_ALREADY_REGISTERED"


def test_admin_onboard_doctor_transaction_rollback_cleanup(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """If database transaction fails, rolls back newly created Supabase Auth user to prevent orphans."""
    newly_created_auth_id = str(uuid.uuid4())
    deleted_ids = []

    with patch(
        "app.services.supabase_admin_service.supabase_admin_service.create_doctor_user",
        return_value=(
            newly_created_auth_id,
            True,
            "User created",
            True,  # is_newly_created
        ),
    ), patch(
        "app.services.supabase_admin_service.supabase_admin_service.delete_user",
        side_effect=lambda user_id: deleted_ids.append(user_id) or True,
    ), patch(
        "sqlalchemy.orm.Session.commit",
        side_effect=RuntimeError("Simulated database constraint or connection failure"),
    ):
        payload = {
            "full_name": "Dr. Rollback Test",
            "email": f"rollback.{str(uuid.uuid4())[:8]}@hospital.org",
            "password": "SecurePassword123!",
            "license_number": f"LIC-RB-{str(uuid.uuid4())[:8]}",
            "hospital_id": "hosp-001",
        }
        response = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload)
        assert response.status_code == 500
        # Verify rollback cleanup was executed for the newly created Auth user
        assert newly_created_auth_id in deleted_ids


def test_doctor_login_after_password_setup(client: TestClient, db_session: Session):
    """Doctor authenticates with valid token and retrieves authorized profile and role."""
    doc_auth_id = f"doctor-active-{str(uuid.uuid4())[:8]}"
    prof = Profile(
        auth_user_id=doc_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Valid Login",
        email=f"valid.doc.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=True,
    )
    db_session.add(prof)
    db_session.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-VAL-{str(uuid.uuid4())[:8]}",
        years_of_experience=8,
        is_active=True,
    )
    db_session.add(doc)
    db_session.commit()

    token = create_access_token(subject=doc_auth_id, role="doctor", hospital_id="hosp-001")
    headers = {"Authorization": f"Bearer {token}"}

    # Verify /api/v1/auth/me
    res_me = client.get("/api/v1/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["role"] == "doctor"
    assert res_me.json()["has_profile"] is True
    assert res_me.json()["is_active"] is True

    # Verify /api/v1/doctors/me
    res_doc_me = client.get("/api/v1/doctors/me", headers=headers)
    assert res_doc_me.status_code == 200
    assert res_doc_me.json()["id"] == doc.id


def test_deactivate_and_reactivate_doctor_lifecycle(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """Deactivation immediately blocks protected doctor access; reactivation restores it."""
    doc_auth_id = f"doc-lifecycle-{str(uuid.uuid4())[:8]}"
    prof = Profile(
        auth_user_id=doc_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Lifecycle Physician",
        email=f"lifecycle.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=True,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-LC-{str(uuid.uuid4())[:8]}",
        years_of_experience=12,
        is_active=True,
    )
    auth_seeded_db.add(doc)
    auth_seeded_db.commit()

    doc_token = create_access_token(subject=doc_auth_id, role="doctor", hospital_id="hosp-001")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    # 1. Before deactivation: access succeeds
    assert client.get("/api/v1/doctors/me", headers=doc_headers).status_code == 200

    # 2. Admin deactivates the doctor
    deact_res = client.patch(
        f"/api/v1/admin/doctors/{doc.id}/status",
        headers=admin_headers,
        json={"is_active": False, "reason": "Sabbatical leave"},
    )
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False
    assert deact_res.json()["status"] == "deactivated"

    # 3. Existing doctor session is immediately denied access
    denied_res = client.get("/api/v1/doctors/me", headers=doc_headers)
    assert denied_res.status_code == 403
    assert denied_res.json()["error"]["code"] in ("ACCOUNT_DEACTIVATED", "ACCOUNT_INACTIVE", "DOCTOR_DEACTIVATED")

    # 4. Admin reactivates the doctor
    react_res = client.patch(
        f"/api/v1/admin/doctors/{doc.id}/status",
        headers=admin_headers,
        json={"is_active": True, "reason": "Returned from leave"},
    )
    assert react_res.status_code == 200
    assert react_res.json()["is_active"] is True
    assert react_res.json()["status"] == "active"

    # 5. Access is restored
    assert client.get("/api/v1/doctors/me", headers=doc_headers).status_code == 200


def test_prevent_new_appointments_for_inactive_doctor(client: TestClient, auth_seeded_db: Session, patient_headers: dict):
    """Booking an appointment with an inactive physician is rejected with 409 Conflict."""
    from app.services.appointment_service import appointment_service
    from app.schemas.appointment import AppointmentCreate
    import datetime

    doc_auth_id = f"doc-inactive-appt-{str(uuid.uuid4())[:8]}"
    prof = Profile(
        auth_user_id=doc_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Inactive Booking",
        email=f"inactive.booking.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=False,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-INACT-{str(uuid.uuid4())[:8]}",
        years_of_experience=5,
        is_active=False,
    )
    auth_seeded_db.add(doc)
    auth_seeded_db.commit()

    # Query availability returns empty slots
    avail = appointment_service.get_doctor_availability(
        auth_seeded_db,
        doctor_id=doc.id,
        requested_date=datetime.date.today() + datetime.timedelta(days=2),
    )
    assert len(avail.slots) == 0

    # Direct booking attempt raises DOCTOR_INACTIVE
    patient_prof = auth_seeded_db.query(Profile).filter(Profile.auth_user_id == "patient-123").first()
    from app.models.patient import Patient
    pat = auth_seeded_db.query(Patient).filter(Patient.profile_id == patient_prof.id).first()
    if not pat:
        pat = Patient(
            profile_id=patient_prof.id,
            date_of_birth=datetime.date(1990, 1, 1),
            preferred_language="en",
        )
        auth_seeded_db.add(pat)
        auth_seeded_db.commit()

    import pytest
    from app.core.exceptions import ConflictError
    with pytest.raises(ConflictError) as exc_info:
        appointment_service.book_appointment(
            auth_seeded_db,
            AppointmentCreate(
                patient_id=pat.id,
                doctor_id=doc.id,
                hospital_id="hosp-001",
                appointment_date=datetime.date.today() + datetime.timedelta(days=2),
                scheduled_start=datetime.time(10, 0),
                scheduled_end=datetime.time(10, 30),
                consultation_mode="in_person",
            ),
        )
    assert exc_info.value.code == "DOCTOR_INACTIVE"


def test_hospital_tenant_isolation_on_lifecycle(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    """Hospital admin bound to hosp-001 cannot deactivate or delete doctors in hosp-002."""
    doc = Doctor(
        profile_id=str(uuid.uuid4()),
        hospital_id="hosp-002",
        license_number=f"LIC-OTHER-HOSP-{str(uuid.uuid4())[:8]}",
        years_of_experience=4,
        is_active=True,
    )
    # Ensure hospital hosp-002 exists
    hosp2 = auth_seeded_db.query(Hospital).filter(Hospital.id == "hosp-002").first()
    if not hosp2:
        hosp2 = Hospital(id="hosp-002", name="St. Jude", code="SJCC")
        auth_seeded_db.add(hosp2)

    auth_seeded_db.add(doc)
    auth_seeded_db.commit()

    # Admin with token restricted to hosp-001 attempts deactivation of hosp-002 doctor
    res_deact = client.patch(
        f"/api/v1/admin/doctors/{doc.id}/status",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert res_deact.status_code == 403
    assert res_deact.json()["error"]["code"] == "CROSS_HOSPITAL_FORBIDDEN"

    # Attempt deletion of hosp-002 doctor
    res_del = client.delete(f"/api/v1/admin/doctors/{doc.id}", headers=admin_headers)
    assert res_del.status_code == 403
    assert res_del.json()["error"]["code"] == "CROSS_HOSPITAL_FORBIDDEN"


def test_prevent_deletion_of_doctor_with_clinical_history(client: TestClient, auth_seeded_db: Session, global_admin_headers: dict):
    """Doctors with dependent appointments or consultations cannot be deleted (preserves medical records)."""
    import datetime
    prof = Profile(
        auth_user_id=f"doc-hist-{str(uuid.uuid4())[:8]}",
        role=UserRole.DOCTOR,
        full_name="Dr. Clinical History",
        email=f"history.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=True,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-HIST-{str(uuid.uuid4())[:8]}",
        years_of_experience=15,
        is_active=True,
    )
    auth_seeded_db.add(doc)
    auth_seeded_db.flush()

    # Create dependent appointment
    appt = Appointment(
        patient_id=str(uuid.uuid4()),
        doctor_id=doc.id,
        hospital_id="hosp-001",
        appointment_date=datetime.date(2026, 10, 30),
        scheduled_start=datetime.time(9, 0),
        scheduled_end=datetime.time(9, 30),
        status=AppointmentStatus.CONFIRMED,
    )
    auth_seeded_db.add(appt)
    auth_seeded_db.commit()

    # Deletion attempt must be rejected with 409
    res = client.delete(f"/api/v1/admin/doctors/{doc.id}", headers=global_admin_headers)
    assert res.status_code == 409
    data = res.json()
    assert data["error"]["code"] == "CANNOT_DELETE_DOCTOR_WITH_CLINICAL_HISTORY"
    assert "retention" in data["error"]["message"].lower()

    # Doctor and dependent appointment must still exist
    assert auth_seeded_db.query(Doctor).filter(Doctor.id == doc.id).first() is not None
    assert auth_seeded_db.query(Appointment).filter(Appointment.id == appt.id).first() is not None


def test_safe_deletion_of_unused_doctor(client: TestClient, auth_seeded_db: Session, global_admin_headers: dict):
    """Safely deletes an unused physician with zero clinical history from DB and Auth."""
    clean_auth_id = str(uuid.uuid4())
    prof = Profile(
        auth_user_id=clean_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Unused Clean",
        email=f"clean.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=True,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-CLEAN-{str(uuid.uuid4())[:8]}",
        years_of_experience=2,
        is_active=True,
    )
    auth_seeded_db.add(doc)
    auth_seeded_db.commit()

    doc_id = doc.id
    prof_id = prof.id

    with patch(
        "app.services.supabase_admin_service.supabase_admin_service.delete_user",
        return_value=True,
    ) as mock_auth_del:
        res = client.delete(f"/api/v1/admin/doctors/{doc_id}", headers=global_admin_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"
        assert mock_auth_del.called

    # Confirm deleted from database
    assert auth_seeded_db.query(Doctor).filter(Doctor.id == doc_id).first() is None
    assert auth_seeded_db.query(Profile).filter(Profile.id == prof_id).first() is None


def test_admin_get_and_configure_doctor_schedules(
    client: TestClient, auth_seeded_db: Session, admin_headers: dict
):
    """Admin configures doctor weekly schedules, immediately reflected in doctor availability."""
    doc_auth_id = f"doc-sched-{str(uuid.uuid4())[:8]}"
    prof = Profile(
        auth_user_id=doc_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Schedule Target",
        email=f"sched.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=True,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-SCHED-{str(uuid.uuid4())[:8]}",
        years_of_experience=4,
        is_active=True,
    )
    auth_seeded_db.add(doc)
    auth_seeded_db.commit()

    # 1. Fetch initial schedules (empty)
    res_get = client.get(f"/api/v1/admin/doctors/{doc.id}/schedules", headers=admin_headers)
    assert res_get.status_code == 200
    assert res_get.json() == []

    # 2. Configure schedules for Monday (day 0) and Wednesday (day 2)
    payload = {
        "schedules": [
            {
                "day_of_week": 0,
                "start_time": "09:00:00",
                "end_time": "12:00:00",
                "slot_duration_minutes": 30,
                "is_active": True,
            },
            {
                "day_of_week": 2,
                "start_time": "14:00:00",
                "end_time": "17:00:00",
                "slot_duration_minutes": 30,
                "is_active": True,
            },
        ]
    }
    res_put = client.put(
        f"/api/v1/admin/doctors/{doc.id}/schedules", headers=admin_headers, json=payload
    )
    assert res_put.status_code == 200
    schedules = res_put.json()
    assert len(schedules) == 2
    assert schedules[0]["day_of_week"] == 0
    assert schedules[1]["day_of_week"] == 2

    # 3. Test patient doctor availability for a Monday vs a Tuesday
    # Find next Monday and Tuesday in future
    today = datetime.datetime.now(datetime.timezone.utc).date()
    days_ahead_mon = (0 - today.weekday()) % 7
    if days_ahead_mon <= 0:
        days_ahead_mon += 7
    next_monday = today + datetime.timedelta(days=days_ahead_mon)
    next_tuesday = next_monday + datetime.timedelta(days=1)

    res_mon = client.get(
        f"/api/v1/doctors/{doc.id}/availability?appointment_date={next_monday.isoformat()}"
    )
    assert res_mon.status_code == 200
    data_mon = res_mon.json()
    assert data_mon["has_schedule"] is True
    assert data_mon["schedule_configured"] is True
    assert len(data_mon["slots"]) == 6  # 09:00 to 12:00 in 30 min slots

    res_tue = client.get(
        f"/api/v1/doctors/{doc.id}/availability?appointment_date={next_tuesday.isoformat()}"
    )
    assert res_tue.status_code == 200
    data_tue = res_tue.json()
    assert data_tue["has_schedule"] is False
    assert data_tue["schedule_configured"] is True
    assert len(data_tue["slots"]) == 0


def test_admin_schedules_forbidden_for_patient_and_doctor(
    client: TestClient, auth_seeded_db: Session, patient_headers: dict, doctor_headers: dict
):
    """Only administrators are authorized to manage doctor schedules."""
    res_pat = client.get("/api/v1/admin/doctors/any-id/schedules", headers=patient_headers)
    assert res_pat.status_code == 403

    res_doc = client.get("/api/v1/admin/doctors/any-id/schedules", headers=doctor_headers)
    assert res_doc.status_code == 403


def test_admin_resend_doctor_invitation_success(
    client: TestClient, auth_seeded_db: Session, admin_headers: dict
):
    """Admin triggers resend invitation for an existing doctor, returning safe link."""
    doc_auth_id = f"doc-resend-{str(uuid.uuid4())[:8]}"
    email = f"resend.{str(uuid.uuid4())[:8]}@hospital.org"
    prof = Profile(
        auth_user_id=doc_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Resend Target",
        email=email,
        hospital_id="hosp-001",
        is_active=True,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-RESEND-{str(uuid.uuid4())[:8]}",
        years_of_experience=6,
        is_active=True,
    )
    auth_seeded_db.add(doc)
    auth_seeded_db.commit()

    with patch(
        "app.services.supabase_admin_service.supabase_admin_service.resend_or_generate_invitation",
        return_value=(
            f"http://localhost:3000/account-setup?mode=set-password&token=recovery-{doc_auth_id}",
            "Physician invitation / password-setup link regenerated successfully.",
            True,
        ),
    ):
        res = client.post(
            f"/api/v1/admin/doctors/{doc.id}/resend-invitation",
            headers=admin_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["doctor_id"] == doc.id
        assert data["email"] == email
        assert data["action_link"] is not None
        assert "/account-setup?mode=set-password" in data["action_link"]
        assert data["auth_provisioned"] is True


def test_admin_resend_doctor_invitation_forbidden_for_patient_and_doctor(
    client: TestClient, auth_seeded_db: Session, patient_headers: dict, doctor_headers: dict
):
    """Non-administrators cannot trigger invitation resends."""
    res_pat = client.post("/api/v1/admin/doctors/any-id/resend-invitation", headers=patient_headers)
    assert res_pat.status_code == 403

    res_doc = client.post("/api/v1/admin/doctors/any-id/resend-invitation", headers=doctor_headers)
    assert res_doc.status_code == 403


def test_admin_onboard_doctor_reject_duplicate_auth_user_id(
    client: TestClient, auth_seeded_db: Session, admin_headers: dict
):
    """Rejects onboarding if auth_user_id is already linked to another Profile."""
    existing_auth_id = str(uuid.uuid4())
    prof = Profile(
        auth_user_id=existing_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Already Linked",
        email=f"linked.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=True,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.commit()

    payload = {
        "full_name": "Dr. Conflict Identity",
        "email": f"conflict.{str(uuid.uuid4())[:8]}@hospital.org",
        "password": "SecurePassword123!",
        "license_number": f"LIC-CONF-{str(uuid.uuid4())[:8]}",
        "hospital_id": "hosp-001",
        "auth_user_id": existing_auth_id,
    }
    res = client.post("/api/v1/admin/doctors/onboard", headers=admin_headers, json=payload)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "AUTH_USER_ALREADY_LINKED"


def test_inactive_doctor_rejected_from_protected_api(
    client: TestClient, auth_seeded_db: Session
):
    """A deactivated doctor cannot access protected doctor APIs, even with an active bearer token."""
    doc_auth_id = f"doc-inactive-{str(uuid.uuid4())[:8]}"
    prof = Profile(
        auth_user_id=doc_auth_id,
        role=UserRole.DOCTOR,
        full_name="Dr. Deactivated User",
        email=f"inactive.{str(uuid.uuid4())[:8]}@hospital.org",
        hospital_id="hosp-001",
        is_active=False,
    )
    auth_seeded_db.add(prof)
    auth_seeded_db.flush()

    doc = Doctor(
        profile_id=prof.id,
        hospital_id="hosp-001",
        license_number=f"LIC-INACT-{str(uuid.uuid4())[:8]}",
        years_of_experience=5,
        is_active=False,
    )
    auth_seeded_db.add(doc)
    auth_seeded_db.commit()

    # Generate token for this doctor
    token = create_access_token(
        subject=doc_auth_id,
        role="doctor",
        additional_claims={"email": prof.email},
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to access a protected endpoint
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_supabase_admin_service_never_falls_back_to_random_uuid_for_existing_user():
    """Verifies that supabase_admin_service never invents a random UUID if existing user lookup fails."""
    import pytest
    from unittest.mock import MagicMock
    from app.services.supabase_admin_service import SupabaseAdminService

    service = SupabaseAdminService()
    with patch.object(SupabaseAdminService, "is_configured", True):
        # Mock post to return 422 (user exists), but get_user_by_email returns None and rec_res returns no id
        mock_post_res1 = MagicMock()
        mock_post_res1.status_code = 422
        mock_post_res1.text = "User already registered"

        mock_post_res2 = MagicMock()
        mock_post_res2.status_code = 200
        mock_post_res2.json.return_value = {"action_link": "https://example.com/recovery"}

        with patch("httpx.Client.post", side_effect=[mock_post_res1, mock_post_res2]):
            with patch.object(service, "get_user_by_email", return_value=None):
                with pytest.raises(RuntimeError) as exc_info:
                    service.invite_or_provision_doctor("unresolvable@hospital.org", "Dr. Test")
                assert "Refusing to generate a random UUID" in str(exc_info.value)


