import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.models.profile import Profile, UserRole
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.hospital import Hospital
from app.models.specialty import Specialty
from app.models.doctor_specialty import DoctorSpecialty
from app.models.appointment import Appointment, AppointmentStatus
from app.schemas.doctor_recommendation import DoctorRecommendationRequest
from app.services.doctor_recommendation_service import doctor_recommendation_service
from app.services.system_setting_service import system_setting_service
import datetime


@pytest.fixture
def setup_doctor_test_env(db_session: Session):
    """Sets up two doctors in the same hospital for authorization and recommendation tests."""
    hosp = Hospital(
        id="hosp-intake-001",
        name="Metro Intake General Hospital",
        code="MIGH-01",
        timezone="UTC",
        is_active=True,
    )
    db_session.add(hosp)

    spec = Specialty(
        id="spec-intake-001",
        name="General Medicine",
        code="GENMED",
        is_active=True,
    )
    db_session.add(spec)

    # Doctor 1: Active, owned by doctor-auth-1
    prof1 = Profile(
        id="prof-intake-001",
        auth_user_id="doctor-auth-1",
        role=UserRole.DOCTOR,
        full_name="Dr. Evelyn Shaw",
        email="eshaw@migh.org",
        hospital_id=hosp.id,
        is_active=True,
    )
    db_session.add(prof1)
    db_session.flush()

    doc1 = Doctor(
        id="doc-intake-001",
        profile_id=prof1.id,
        hospital_id=hosp.id,
        license_number="LIC-INTAKE-001",
        years_of_experience=10,
        consultation_mode="both",
        average_rating=4.8,
        rating_count=20,
        languages="en",
        is_active=True,
    )
    db_session.add(doc1)
    db_session.flush()

    ds1 = DoctorSpecialty(doctor_id=doc1.id, specialty_id=spec.id, is_primary=True)
    db_session.add(ds1)

    # Doctor 1 Schedule
    for day in range(5):
        db_session.add(
            DoctorSchedule(
                doctor_id=doc1.id,
                hospital_id=hosp.id,
                day_of_week=day,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(17, 0),
                slot_duration_minutes=30,
                is_active=True,
            )
        )

    # Doctor 2: Owned by doctor-auth-2
    prof2 = Profile(
        id="prof-intake-002",
        auth_user_id="doctor-auth-2",
        role=UserRole.DOCTOR,
        full_name="Dr. Tariq Vance",
        email="tvance@migh.org",
        hospital_id=hosp.id,
        is_active=True,
    )
    db_session.add(prof2)
    db_session.flush()

    doc2 = Doctor(
        id="doc-intake-002",
        profile_id=prof2.id,
        hospital_id=hosp.id,
        license_number="LIC-INTAKE-002",
        years_of_experience=8,
        consultation_mode="both",
        average_rating=4.7,
        rating_count=15,
        languages="en",
        is_active=True,
    )
    db_session.add(doc2)
    db_session.flush()

    ds2 = DoctorSpecialty(doctor_id=doc2.id, specialty_id=spec.id, is_primary=True)
    db_session.add(ds2)

    db_session.commit()
    return {
        "hospital": hosp,
        "specialty": spec,
        "doctor1": doc1,
        "doctor2": doc2,
        "profile1": prof1,
        "profile2": prof2,
    }


def test_doctor_intake_toggle_activation_and_deactivation(client: TestClient, setup_doctor_test_env: dict):
    """Doctor can toggle intake status between active and paused via authenticated PATCH."""
    doc1 = setup_doctor_test_env["doctor1"]
    token = create_access_token(
        subject="doctor-auth-1", role="doctor", hospital_id=setup_doctor_test_env["hospital"].id
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Initially defaults to accepting patients
    get_res = client.get("/api/v1/doctors/me", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["is_accepting_patients"] is True

    # 2. Pause intake station
    patch_res = client.patch(
        f"/api/v1/doctors/{doc1.id}/intake-status",
        json={"is_accepting_patients": False},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_accepting_patients"] is False
    assert patch_res.json()["status"] == "Station Paused"

    # 3. Verify persistence on profile retrieval
    get_res2 = client.get("/api/v1/doctors/me", headers=headers)
    assert get_res2.status_code == 200
    assert get_res2.json()["is_accepting_patients"] is False

    # 4. Reactivate intake station via /me/intake-status alias
    patch_res2 = client.patch(
        "/api/v1/doctors/me/intake-status",
        json={"is_accepting_patients": True},
        headers=headers,
    )
    assert patch_res2.status_code == 200
    assert patch_res2.json()["is_accepting_patients"] is True
    assert patch_res2.json()["status"] == "Accepting Patients"

    # 5. Verify persistence
    get_res3 = client.get(f"/api/v1/doctors/{doc1.id}")
    assert get_res3.status_code == 200
    assert get_res3.json()["is_accepting_patients"] is True


def test_unauthorized_user_cannot_update_another_doctor_intake_status(client: TestClient, setup_doctor_test_env: dict):
    """A doctor is strictly forbidden from changing another physician's station intake status."""
    doc1 = setup_doctor_test_env["doctor1"]
    # Authenticate as Doctor 2
    token_doc2 = create_access_token(
        subject="doctor-auth-2", role="doctor", hospital_id=setup_doctor_test_env["hospital"].id
    )
    headers = {"Authorization": f"Bearer {token_doc2}"}

    # Attempt to pause Doctor 1's station
    res = client.patch(
        f"/api/v1/doctors/{doc1.id}/intake-status",
        json={"is_accepting_patients": False},
        headers=headers,
    )
    assert res.status_code == 403
    assert "FORBIDDEN_DOCTOR_STATUS_UPDATE" in res.text


def test_patient_cannot_update_doctor_intake_status(client: TestClient, setup_doctor_test_env: dict):
    """Patient role cannot update physician station intake status."""
    doc1 = setup_doctor_test_env["doctor1"]
    patient_token = create_access_token(
        subject="patient-999", role="patient"
    )
    headers = {"Authorization": f"Bearer {patient_token}"}

    res = client.patch(
        f"/api/v1/doctors/{doc1.id}/intake-status",
        json={"is_accepting_patients": False},
        headers=headers,
    )
    assert res.status_code == 403


def test_intake_status_preserves_schedules_and_existing_appointments(
    client: TestClient, db_session: Session, setup_doctor_test_env: dict
):
    """Changing intake status does not alter consultation schedules or existing appointments."""
    doc1 = setup_doctor_test_env["doctor1"]
    token = create_access_token(
        subject="doctor-auth-1", role="doctor", hospital_id=setup_doctor_test_env["hospital"].id
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Create an existing appointment
    appt = Appointment(
        patient_id="patient-dummy-123",
        doctor_id=doc1.id,
        hospital_id=doc1.hospital_id,
        appointment_date=datetime.date(2026, 10, 26),
        scheduled_start=datetime.time(10, 0),
        scheduled_end=datetime.time(10, 30),
        status=AppointmentStatus.BOOKED,
    )
    db_session.add(appt)
    db_session.commit()

    # Verify schedules count before
    schedules_before = (
        db_session.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doc1.id).count()
    )
    assert schedules_before == 5

    # Pause intake station
    patch_res = client.patch(
        f"/api/v1/doctors/{doc1.id}/intake-status",
        json={"is_accepting_patients": False},
        headers=headers,
    )
    assert patch_res.status_code == 200

    # Verify schedules count after is identical
    schedules_after = (
        db_session.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doc1.id).count()
    )
    assert schedules_after == schedules_before

    # Verify existing appointment remains BOOKED and intact
    db_appt = db_session.query(Appointment).filter(Appointment.id == appt.id).first()
    assert db_appt is not None
    assert db_appt.status == AppointmentStatus.BOOKED


def test_triage_recommendations_exclude_paused_station_doctors(
    db_session: Session, setup_doctor_test_env: dict
):
    """Triage recommendations route only to active, accepting doctors and exclude paused station doctors."""
    doc1 = setup_doctor_test_env["doctor1"]
    doc2 = setup_doctor_test_env["doctor2"]
    spec = setup_doctor_test_env["specialty"]
    hosp = setup_doctor_test_env["hospital"]

    # 1. Both active by default -> both eligible for recommendation
    req = DoctorRecommendationRequest(specialty_id=spec.id, hospital_id=hosp.id)
    user = type("MockUser", (), {"id": "patient-1", "is_patient": True, "hospital_id": hosp.id})()
    resp1 = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    rec_ids = [item.doctor_id for item in resp1.recommendations]
    assert doc1.id in rec_ids
    assert doc2.id in rec_ids

    # 2. Pause Doctor 1's station
    system_setting_service.set_doctor_intake_status(db_session, doc1.id, is_accepting=False)

    # 3. Doctor 1 is excluded, Doctor 2 is recommended
    resp2 = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    rec_ids2 = [item.doctor_id for item in resp2.recommendations]
    assert doc1.id not in rec_ids2
    assert doc2.id in rec_ids2

    # 4. Reactivate Doctor 1's station
    system_setting_service.set_doctor_intake_status(db_session, doc1.id, is_accepting=True)
    resp3 = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    rec_ids3 = [item.doctor_id for item in resp3.recommendations]
    assert doc1.id in rec_ids3


def test_deactivated_doctor_cannot_update_intake_status(client: TestClient, db_session: Session, setup_doctor_test_env: dict):
    """An admin-deactivated doctor cannot update their intake status."""
    doc1 = setup_doctor_test_env["doctor1"]
    doc1.is_active = False
    db_session.commit()

    token = create_access_token(
        subject="doctor-auth-1", role="doctor", hospital_id=setup_doctor_test_env["hospital"].id
    )
    headers = {"Authorization": f"Bearer {token}"}

    res = client.patch(
        f"/api/v1/doctors/{doc1.id}/intake-status",
        json={"is_accepting_patients": True},
        headers=headers,
    )
    assert res.status_code == 403
    assert "ACCOUNT_INACTIVE" in res.text or "DOCTOR_DEACTIVATED" in res.text
