import datetime
import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.profile import Profile, UserRole
from app.models.system_setting import SystemSetting
from app.services.system_setting_service import system_setting_service
from app.cli.admin import create_admin_user


def test_registration_status_public_endpoint(client: TestClient, db_session: Session):
    """Verifies that public unauthenticated visitors can inspect registration availability."""
    # Default state is enabled
    res = client.get("/api/v1/auth/registration-status")
    assert res.status_code == 200
    data = res.json()
    assert "patient_self_registration_enabled" in data
    assert data["patient_self_registration_enabled"] is True

    # When toggled to disabled
    system_setting_service.set_patient_self_registration(db_session, enabled=False)
    res2 = client.get("/api/v1/auth/registration-status")
    assert res2.status_code == 200
    assert res2.json()["patient_self_registration_enabled"] is False


def test_public_patient_registration_enabled_flow(client: TestClient, db_session: Session):
    """Verifies that public patient registration succeeds when enabled."""
    system_setting_service.set_patient_self_registration(db_session, enabled=True)

    unregistered_auth_id = str(uuid.uuid4())
    token = create_access_token(subject=unregistered_auth_id, role="unregistered")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "full_name": "Alice Wonder",
        "date_of_birth": "1994-05-15",
        "email": "alice.wonder@test.org",
        "phone": "+1 (555) 234-5678",
        "preferred_language": "en",
        "emergency_contact": "Bob Wonder (+1 555-9876)",
    }

    res = client.post("/api/v1/auth/complete-patient-profile", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "completed"
    assert data["role"] == "patient"
    assert data["full_name"] == "Alice Wonder"
    assert data["email"] == "alice.wonder@test.org"

    # Verify authoritative database record
    profile = db_session.query(Profile).filter(Profile.auth_user_id == unregistered_auth_id).first()
    assert profile is not None
    assert profile.role == UserRole.PATIENT

    patient = db_session.query(Patient).filter(Patient.profile_id == profile.id).first()
    assert patient is not None
    assert str(patient.date_of_birth) == "1994-05-15"


def test_public_registration_disabled_blocks_direct_api(client: TestClient, db_session: Session):
    """Verifies that direct API attempts to register are blocked with 403 when registration is disabled."""
    # Explicitly disable public patient self-registration
    system_setting_service.set_patient_self_registration(db_session, enabled=False)

    unregistered_auth_id = str(uuid.uuid4())
    token = create_access_token(subject=unregistered_auth_id, role="unregistered")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "full_name": "Bypasser Attempt",
        "date_of_birth": "1990-01-01",
        "email": "bypasser@test.org",
    }

    # Direct POST to completion endpoint
    res = client.post("/api/v1/auth/complete-patient-profile", json=payload, headers=headers)
    assert res.status_code == 403
    err_body = res.json()
    err_code = err_body.get("code") or err_body.get("error", {}).get("code", "")
    assert err_code == "REGISTRATION_DISABLED"

    # Verify no profile or patient was created
    profile = db_session.query(Profile).filter(Profile.auth_user_id == unregistered_auth_id).first()
    assert profile is None



def test_unauthorized_users_cannot_change_registration_setting(
    client: TestClient,
    auth_seeded_db: Session,
    patient_headers: dict,
    doctor_headers: dict,
):
    """Ensures patients, doctors, and anonymous users cannot modify the registration toggle."""
    payload = {"enabled": False}

    # 1. Anonymous attempt -> 401
    res_anon = client.patch("/api/v1/admin/settings/patient-self-registration", json=payload)
    assert res_anon.status_code in (401, 403)

    # 2. Patient attempt -> 403
    res_pat = client.patch(
        "/api/v1/admin/settings/patient-self-registration",
        json=payload,
        headers=patient_headers,
    )
    assert res_pat.status_code == 403

    # 3. Doctor attempt -> 403
    res_doc = client.patch(
        "/api/v1/admin/settings/patient-self-registration",
        json=payload,
        headers=doctor_headers,
    )
    assert res_doc.status_code == 403


def test_authorized_admin_can_toggle_and_persist_setting(
    client: TestClient,
    auth_seeded_db: Session,
    admin_headers: dict,
):
    """Verifies that an authorized administrator can toggle the setting and it persists in the database."""
    # 1. Admin disables registration
    res_disable = client.patch(
        "/api/v1/admin/settings/patient-self-registration",
        json={"enabled": False},
        headers=admin_headers,
    )
    assert res_disable.status_code == 200
    assert res_disable.json()["patient_self_registration_enabled"] is False

    # Check persistence in database
    db_setting = auth_seeded_db.query(SystemSetting).filter(SystemSetting.key == "patient_self_registration").first()
    assert db_setting is not None
    assert db_setting.value == "false"

    # 2. Admin re-enables registration
    res_enable = client.patch(
        "/api/v1/admin/settings/patient-self-registration",
        json={"enabled": True},
        headers=admin_headers,
    )
    assert res_enable.status_code == 200
    assert res_enable.json()["patient_self_registration_enabled"] is True

    # Verify persistence again
    auth_seeded_db.refresh(db_setting)
    assert db_setting.value == "true"


def test_admin_created_patient_available_when_public_registration_disabled(
    client: TestClient,
    auth_seeded_db: Session,
    admin_headers: dict,
):
    """Ensures clinic administrators can register patients even when public registration is disabled."""
    # Disable public self-registration
    system_setting_service.set_patient_self_registration(auth_seeded_db, enabled=False)

    payload = {
        "full_name": "Clinic Managed Patient",
        "email": "clinic.patient@test.org",
        "date_of_birth": "1975-12-25",
        "phone": "+1 (555) 789-0123",
        "emergency_contact": "Spouse (+1 555-4567)",
        "preferred_language": "en",
    }

    res = client.post("/api/v1/admin/patients/register", json=payload, headers=admin_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "created"
    assert data["role"] == "patient"
    assert data["email"] == "clinic.patient@test.org"

    # Confirm authoritative records created in DB
    created_profile = auth_seeded_db.query(Profile).filter(Profile.email == "clinic.patient@test.org").first()
    assert created_profile is not None
    assert created_profile.role == UserRole.PATIENT


def test_admin_register_patient_duplicate_email_conflict(
    client: TestClient,
    auth_seeded_db: Session,
    admin_headers: dict,
):
    """Verifies that creating a patient with a duplicate email returns 409 Conflict."""
    payload = {
        "full_name": "Duplicate Test",
        "email": "p123@test.org",  # Pre-seeded in auth_seeded_db
        "date_of_birth": "1980-01-01",
    }

    res = client.post("/api/v1/admin/patients/register", json=payload, headers=admin_headers)
    assert res.status_code == 409
    err_body = res.json()
    err_code = err_body.get("code") or err_body.get("error", {}).get("code", "")
    assert err_code == "EMAIL_ALREADY_EXISTS"


def test_doctor_self_registration_prevented_and_admin_onboarding(
    client: TestClient,
    auth_seeded_db: Session,
    admin_headers: dict,
    patient_headers: dict,
):
    """Verifies doctor self-registration is rejected and only admins can onboard physicians."""
    # 1. Non-admin attempting to onboard doctor -> 403
    doc_payload = {
        "full_name": "Dr. Hacker Claim",
        "email": "hacker.doc@test.org",
        "password": "SecurePassword123!",
        "license_number": "MD-99999",
        "hospital_id": "hosp-001",
    }
    res_forbidden = client.post("/api/v1/admin/doctors/onboard", json=doc_payload, headers=patient_headers)
    assert res_forbidden.status_code == 403

    # Ensure hospital exists in DB with valid required code
    hosp = auth_seeded_db.query(Hospital).filter(Hospital.id == "hosp-001").first()
    if not hosp:
        auth_seeded_db.add(Hospital(id="hosp-001", code="CGH", name="City General Hospital"))
        auth_seeded_db.commit()

    # 2. Admin onboards doctor -> 201 (mock Supabase Auth operations)
    with patch(
        "app.services.supabase_admin_service.supabase_admin_service.get_user_by_email",
        return_value=None,
    ), patch(
        "app.services.supabase_admin_service.supabase_admin_service.create_doctor_user",
        return_value=(str(uuid.uuid4()), True, "Physician onboarded successfully.", True),
    ):
        res_admin = client.post("/api/v1/admin/doctors/onboard", json=doc_payload, headers=admin_headers)
        assert res_admin.status_code == 201
        doc_data = res_admin.json()
        assert doc_data["role"] == "doctor"

        # 3. Duplicate license number rejected -> 409
        dup_payload = {
            "full_name": "Dr. Another Doctor",
            "email": "another.doc@test.org",
            "password": "SecurePassword123!",
            "license_number": "MD-99999",  # Duplicate license
            "hospital_id": "hosp-001",
        }
        res_dup = client.post("/api/v1/admin/doctors/onboard", json=dup_payload, headers=admin_headers)
        assert res_dup.status_code == 409
        dup_err = res_dup.json()
        assert (dup_err.get("code") or dup_err.get("error", {}).get("code")) == "LICENSE_ALREADY_REGISTERED"



def test_admin_bootstrap_cli_safety(db_session: Session):
    """Verifies the backend-only admin CLI bootstrap command and validation checks."""
    # 1. Dry run succeeds without committing records
    dry_run_success = create_admin_user(
        email="dryrun.admin@test.org",
        full_name="Dry Run Admin",
        dry_run=True,
    )
    assert dry_run_success is True

    # 2. Invalid email rejected
    invalid_email_res = create_admin_user(
        email="notanemail",
        full_name="Invalid Admin",
        dry_run=True,
    )
    assert invalid_email_res is False


def test_existing_login_and_auth_me_preserved(
    client: TestClient,
    auth_seeded_db: Session,
    patient_headers: dict,
    doctor_headers: dict,
    admin_headers: dict,
):
    """Ensures existing authenticated sessions continue resolving roles correctly."""
    # Patient
    res_pat = client.get("/api/v1/auth/me", headers=patient_headers)
    assert res_pat.status_code == 200
    assert res_pat.json()["role"] == "patient"

    # Doctor
    res_doc = client.get("/api/v1/auth/me", headers=doctor_headers)
    assert res_doc.status_code == 200
    assert res_doc.json()["role"] == "doctor"

    # Admin
    res_adm = client.get("/api/v1/auth/me", headers=admin_headers)
    assert res_adm.status_code == 200
    assert res_adm.json()["role"] == "admin"
