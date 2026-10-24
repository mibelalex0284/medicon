import datetime
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.profile import Profile, UserRole
from app.schemas.doctor import DoctorCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service


def test_token_verification_valid_and_invalid(client: TestClient, db_session: Session):
    """Verifies that valid tokens are accepted, while invalid/malformed tokens are rejected with 401."""
    # 1. Missing Authorization header
    res_missing = client.get("/api/v1/auth/me")
    assert res_missing.status_code == 401
    assert res_missing.json()["error"]["code"] == "AUTHORIZATION_HEADER_MISSING"

    # 2. Malformed Authorization header
    res_malformed = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Token not-bearer"}
    )
    assert res_malformed.status_code == 401
    assert res_malformed.json()["error"]["code"] == "INVALID_AUTH_HEADER"

    # 3. Invalid signature
    bad_token = jwt.encode(
        {"sub": "attacker-001", "role": "admin", "exp": 1999999999},
        "wrong-secret-key-1234567890",
        algorithm="HS256",
    )
    res_bad_sig = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_token}"}
    )
    assert res_bad_sig.status_code == 401
    assert res_bad_sig.json()["error"]["code"] == "INVALID_TOKEN"

    # 4. Valid token
    good_token = create_access_token(
        subject="valid-test-user",
        role="patient",
    )
    res_good = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {good_token}"}
    )
    assert res_good.status_code == 200
    data = res_good.json()
    assert data["auth_user_id"] == "valid-test-user"
    assert data["has_profile"] is False
    assert data["role"] == "unregistered"


def test_token_verification_expired(client: TestClient):
    """Verifies that expired tokens are cleanly rejected with TOKEN_EXPIRED."""
    expired_token = create_access_token(
        subject="expired-user",
        role="patient",
        expires_delta=datetime.timedelta(seconds=-10),
    )
    res = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_auth_identity_to_profile_mapping_and_role_escalation_prevention(
    client: TestClient, db_session: Session
):
    """Verifies that user role is derived strictly from DB Profile, never client-supplied token claims."""
    # Create patient profile in DB
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="legit-patient-id",
            role=UserRole.PATIENT,
            full_name="Legit Patient",
            email="patient@test.com",
        ),
    )

    # An attacker crafts a token with sub='legit-patient-id' but attempts privilege escalation to 'admin'
    tampered_token = create_access_token(
        subject="legit-patient-id",
        role="admin",
        additional_claims={
            "app_metadata": {"role": "admin"},
            "user_metadata": {"role": "admin"},
        },
    )

    # Calling /auth/me must return role='patient' (from DB), not 'admin'
    res_me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"}
    )
    assert res_me.status_code == 200
    data = res_me.json()
    assert data["role"] == "patient"
    assert data["has_profile"] is True
    assert data["profile_id"] == prof.id

    # The patient cannot access admin route despite token claim
    res_admin = client.get(
        "/api/v1/doctors/admin/list",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert res_admin.status_code == 403
    assert res_admin.json()["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"


def test_inactive_profile_is_forbidden(client: TestClient, db_session: Session):
    """Verifies that inactive doctor/patient profiles are rejected with ACCOUNT_INACTIVE."""
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="inactive-user-id",
            role=UserRole.DOCTOR,
            full_name="Dr. Suspended",
            email="suspended@doc.org",
            is_active=False,
        ),
    )
    token = create_access_token(subject="inactive-user-id", role="doctor")

    res = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ACCOUNT_INACTIVE"


def test_patient_profile_completion_transactional_flow(
    client: TestClient, db_session: Session
):
    """Verifies Phase D: Transactional patient profile completion, duplicate prevention, and role restriction."""
    token = create_access_token(
        subject="new-supabase-patient-uuid",
        role="authenticated",
        additional_claims={"email": "new.patient@test.org"},
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Before completion: /auth/me returns has_profile=False, role='unregistered'
    res_before = client.get("/api/v1/auth/me", headers=headers)
    assert res_before.status_code == 200
    assert res_before.json()["has_profile"] is False
    assert res_before.json()["role"] == "unregistered"

    # Attempt to access protected patient endpoint before profile completion -> 403
    res_pat_unreg = client.get("/api/v1/patients/me", headers=headers)
    assert res_pat_unreg.status_code == 403
    assert res_pat_unreg.json()["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    # Complete profile
    payload = {
        "full_name": "Maya Lin",
        "date_of_birth": "1994-06-15",
        "phone": "+1-555-0192",
        "preferred_language": "en",
        "emergency_contact": "John Lin (+1-555-0193)",
        "accessibility_notes": "Wheelchair access required",
    }
    res_complete = client.post(
        "/api/v1/auth/complete-patient-profile", json=payload, headers=headers
    )
    assert res_complete.status_code == 201
    comp_data = res_complete.json()
    assert comp_data["status"] == "completed"
    assert comp_data["role"] == "patient"
    assert comp_data["full_name"] == "Maya Lin"
    assert comp_data["email"] == "new.patient@test.org"

    # Verify atomic DB persistence
    db_prof = (
        db_session.query(Profile)
        .filter(Profile.auth_user_id == "new-supabase-patient-uuid")
        .first()
    )
    assert db_prof is not None
    assert db_prof.role == UserRole.PATIENT
    assert db_prof.patient_profile is not None
    assert db_prof.patient_profile.date_of_birth == datetime.date(1994, 6, 15)

    # Duplicate profile completion for same auth user -> 409 Conflict
    res_duplicate = client.post(
        "/api/v1/auth/complete-patient-profile", json=payload, headers=headers
    )
    assert res_duplicate.status_code == 409
    assert res_duplicate.json()["error"]["code"] == "PROFILE_ALREADY_EXISTS"

    # After completion: user is recognized as genuine PATIENT
    res_me_after = client.get("/api/v1/auth/me", headers=headers)
    assert res_me_after.status_code == 200
    assert res_me_after.json()["has_profile"] is True
    assert res_me_after.json()["role"] == "patient"


def test_patient_profile_completion_rollback_on_conflict(
    client: TestClient, db_session: Session
):
    """Verifies that patient profile completion rolls back atomically if an error occurs."""
    # Pre-register a profile with a specific email
    profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="user-one-id",
            role=UserRole.PATIENT,
            full_name="User One",
            email="shared@test.org",
        ),
    )

    # A second auth user attempts to register with the same email
    token2 = create_access_token(
        subject="user-two-id",
        role="authenticated",
        additional_claims={"email": "shared@test.org"},
    )
    res_conflict = client.post(
        "/api/v1/auth/complete-patient-profile",
        json={"full_name": "User Two", "date_of_birth": "1990-01-01"},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res_conflict.status_code == 409
    assert res_conflict.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    # Verify no partial profile was created for user-two-id
    p2_check = (
        db_session.query(Profile)
        .filter(Profile.auth_user_id == "user-two-id")
        .first()
    )
    assert p2_check is None


def test_patient_record_authorization_idor_remediation(
    client: TestClient, db_session: Session
):
    """Verifies Phase E: GET /api/v1/patients/{patient_id} authorization hardening.
    
    1. Patient can access own record.
    2. Patient cannot access another patient's record (403 ACCESS_FORBIDDEN).
    3. Doctor cannot access patient without active clinical relationship or same hospital (403 CROSS_HOSPITAL_FORBIDDEN).
    4. Doctor with appointment can access patient (200).
    5. Admin within hospital tenant boundary can access patient (200).
    6. Admin across hospital tenant boundary is rejected (403 CROSS_HOSPITAL_FORBIDDEN).
    7. Unregistered identity cannot access (403 INSUFFICIENT_ROLE_PERMISSIONS).
    """
    # Hospitals
    hosp_a = hospital_service.create_hospital(
        db_session, HospitalCreate(name="St. Marys", code="STM-01")
    )
    hosp_b = hospital_service.create_hospital(
        db_session, HospitalCreate(name="General East", code="GNE-02")
    )

    # Patient 1 (in hosp_a)
    p1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-p1",
            role=UserRole.PATIENT,
            full_name="Patient 1",
            email="p1@hospa.org",
            hospital_id=hosp_a.id,
        ),
    )
    p1 = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p1_prof.id, date_of_birth=datetime.date(1990, 1, 1)),
    )

    # Patient 2 (in hosp_b)
    p2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-p2",
            role=UserRole.PATIENT,
            full_name="Patient 2",
            email="p2@hospb.org",
            hospital_id=hosp_b.id,
        ),
    )
    p2 = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p2_prof.id, date_of_birth=datetime.date(1992, 2, 2)),
    )

    # Doctor A (in hosp_a)
    doc_a_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-doc-a",
            role=UserRole.DOCTOR,
            full_name="Dr. Alpha",
            email="doc.a@hospa.org",
            hospital_id=hosp_a.id,
        ),
    )
    doc_a = doctor_service.create_doctor(
        db_session,
        DoctorCreate(profile_id=doc_a_prof.id, hospital_id=hosp_a.id, license_number="LIC-A-01"),
    )

    # Doctor B (in hosp_b)
    doc_b_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-doc-b",
            role=UserRole.DOCTOR,
            full_name="Dr. Beta",
            email="doc.b@hospb.org",
            hospital_id=hosp_b.id,
        ),
    )
    doc_b = doctor_service.create_doctor(
        db_session,
        DoctorCreate(profile_id=doc_b_prof.id, hospital_id=hosp_b.id, license_number="LIC-B-02"),
    )

    # Admin A (in hosp_a)
    admin_a_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-admin-a",
            role=UserRole.ADMIN,
            full_name="Admin Alpha",
            email="admin.a@hospa.org",
            hospital_id=hosp_a.id,
        ),
    )

    # Tokens
    token_p1 = create_access_token("auth-p1", "patient")
    token_p2 = create_access_token("auth-p2", "patient")
    token_doc_a = create_access_token("auth-doc-a", "doctor", hospital_id=hosp_a.id)
    token_doc_b = create_access_token("auth-doc-b", "doctor", hospital_id=hosp_b.id)
    token_admin_a = create_access_token("auth-admin-a", "admin", hospital_id=hosp_a.id)
    token_unreg = create_access_token("auth-unreg-uuid", "authenticated")

    # 1. Patient 1 accesses own record -> 200
    res_own = client.get(
        f"/api/v1/patients/{p1.id}",
        headers={"Authorization": f"Bearer {token_p1}"},
    )
    assert res_own.status_code == 200
    assert res_own.json()["id"] == p1.id

    # 2. Patient 2 attempts to access Patient 1's record -> 403 ACCESS_FORBIDDEN
    res_cross_pat = client.get(
        f"/api/v1/patients/{p1.id}",
        headers={"Authorization": f"Bearer {token_p2}"},
    )
    assert res_cross_pat.status_code == 403
    assert res_cross_pat.json()["error"]["code"] == "ACCESS_FORBIDDEN"

    # 3. Doctor B (hosp_b) attempts to access Patient 1 (hosp_a) without clinical relationship -> 403 CROSS_HOSPITAL_FORBIDDEN
    res_cross_doc = client.get(
        f"/api/v1/patients/{p1.id}",
        headers={"Authorization": f"Bearer {token_doc_b}"},
    )
    assert res_cross_doc.status_code == 403
    assert res_cross_doc.json()["error"]["code"] == "CROSS_HOSPITAL_FORBIDDEN"

    # 4. Doctor A (hosp_a) accesses Patient 1 (hosp_a) -> 200
    res_same_hosp_doc = client.get(
        f"/api/v1/patients/{p1.id}",
        headers={"Authorization": f"Bearer {token_doc_a}"},
    )
    assert res_same_hosp_doc.status_code == 200
    assert res_same_hosp_doc.json()["id"] == p1.id

    # 5. Doctor B establishes a clinical appointment with Patient 1 -> Doctor B now permitted
    appt = Appointment(
        patient_id=p1.id,
        doctor_id=doc_b.id,
        hospital_id=hosp_b.id,
        appointment_date=datetime.datetime.now(datetime.timezone.utc).date(),
        scheduled_start=datetime.time(10, 0),
        scheduled_end=datetime.time(10, 30),
        status=AppointmentStatus.BOOKED,
    )
    db_session.add(appt)
    db_session.commit()

    res_doc_b_with_appt = client.get(
        f"/api/v1/patients/{p1.id}",
        headers={"Authorization": f"Bearer {token_doc_b}"},
    )
    assert res_doc_b_with_appt.status_code == 200
    assert res_doc_b_with_appt.json()["id"] == p1.id

    # 6. Admin A accesses Patient 1 (same hospital) -> 200
    res_admin_a = client.get(
        f"/api/v1/patients/{p1.id}",
        headers={"Authorization": f"Bearer {token_admin_a}"},
    )
    assert res_admin_a.status_code == 200

    # 7. Admin A attempts to access Patient 2 (different hospital) -> 403 CROSS_HOSPITAL_FORBIDDEN
    res_admin_cross = client.get(
        f"/api/v1/patients/{p2.id}",
        headers={"Authorization": f"Bearer {token_admin_a}"},
    )
    assert res_admin_cross.status_code == 403
    assert res_admin_cross.json()["error"]["code"] == "CROSS_HOSPITAL_FORBIDDEN"

    # 8. Unregistered / unverified user without a role profile -> 403 INSUFFICIENT_ROLE_PERMISSIONS
    res_unreg = client.get(
        f"/api/v1/patients/{p1.id}",
        headers={"Authorization": f"Bearer {token_unreg}"},
    )
    assert res_unreg.status_code == 403
    assert res_unreg.json()["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"
