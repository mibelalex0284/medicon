import datetime
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.profile import Profile, UserRole
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorSchedule
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.appointment import Appointment, AppointmentStatus
from app.services.doctor_service import doctor_service
from app.services.appointment_service import appointment_service
from app.core.security import create_access_token


@pytest.fixture
def schedule_test_env(db_session: Session):
    """Sets up a test hospital, doctors, and patient for scheduling tests."""
    hospital = Hospital(
        id="hosp-sched-001",
        name="Metropolitan Care Hospital",
        code="MCH-SCHED",
        timezone="America/New_York",
        is_active=True,
    )
    db_session.add(hospital)

    # Doctor 1: With valid weekday schedule (Mon-Fri 09:00 - 17:00)
    prof1 = Profile(
        id=str(uuid.uuid4()),
        auth_user_id="auth-doc-1",
        role=UserRole.DOCTOR,
        full_name="Dr. Javad Test",
        email="javad.test@hospital.org",
        hospital_id=hospital.id,
        is_active=True,
    )
    db_session.add(prof1)
    db_session.flush()

    doc1 = Doctor(
        id=str(uuid.uuid4()),
        profile_id=prof1.id,
        hospital_id=hospital.id,
        license_number="LIC-JAVAD-001",
        years_of_experience=12,
        consultation_mode="both",
        is_active=True,
    )
    db_session.add(doc1)
    db_session.flush()

    # Doctor 2: Unscheduled doctor (no schedule records)
    prof2 = Profile(
        id=str(uuid.uuid4()),
        auth_user_id="auth-doc-2",
        role=UserRole.DOCTOR,
        full_name="Dr. Marcus Unscheduled",
        email="marcus.unscheduled@hospital.org",
        hospital_id=hospital.id,
        is_active=True,
    )
    db_session.add(prof2)
    db_session.flush()

    doc2 = Doctor(
        id=str(uuid.uuid4()),
        profile_id=prof2.id,
        hospital_id=hospital.id,
        license_number="LIC-UNSCHED-002",
        years_of_experience=8,
        consultation_mode="in_person",
        is_active=True,
    )
    db_session.add(doc2)

    # Doctor 3: Tuesday-only doctor
    prof3 = Profile(
        id=str(uuid.uuid4()),
        auth_user_id="auth-doc-3",
        role=UserRole.DOCTOR,
        full_name="Dr. Tuesday Only",
        email="tuesday.only@hospital.org",
        hospital_id=hospital.id,
        is_active=True,
    )
    db_session.add(prof3)
    db_session.flush()

    doc3 = Doctor(
        id=str(uuid.uuid4()),
        profile_id=prof3.id,
        hospital_id=hospital.id,
        license_number="LIC-TUES-003",
        years_of_experience=15,
        consultation_mode="both",
        is_active=True,
    )
    db_session.add(doc3)
    db_session.flush()

    # Give Doc 3 only Tuesday (day_of_week=1)
    db_session.add(
        DoctorSchedule(
            doctor_id=doc3.id,
            hospital_id=hospital.id,
            day_of_week=1,  # Tuesday
            start_time=datetime.time(10, 0),
            end_time=datetime.time(14, 0),
            slot_duration_minutes=30,
            is_active=True,
        )
    )

    # Give Doc 1 Mon-Fri schedules
    for dow in range(5):
        db_session.add(
            DoctorSchedule(
                doctor_id=doc1.id,
                hospital_id=hospital.id,
                day_of_week=dow,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(17, 0),
                slot_duration_minutes=30,
                is_active=True,
            )
        )

    # Admin profile for auth
    admin_prof = Profile(
        id=str(uuid.uuid4()),
        auth_user_id="auth-admin-sched",
        role=UserRole.ADMIN,
        full_name="Admin Scheduling",
        email="admin.sched@hospital.org",
        hospital_id=hospital.id,
        is_active=True,
    )
    db_session.add(admin_prof)

    # Patient profile & entity
    patient_prof = Profile(
        id=str(uuid.uuid4()),
        auth_user_id="auth-patient-sched",
        role=UserRole.PATIENT,
        full_name="Patient Sched",
        email="patient.sched@hospital.org",
        hospital_id=hospital.id,
        is_active=True,
    )
    db_session.add(patient_prof)
    db_session.flush()

    patient_entity = Patient(
        id=str(uuid.uuid4()),
        profile_id=patient_prof.id,
        date_of_birth=datetime.date(1990, 1, 1),
        preferred_language="en",
    )
    db_session.add(patient_entity)

    db_session.commit()

    return {
        "hospital": hospital,
        "doc1": doc1,
        "doc2": doc2,
        "doc3": doc3,
        "admin_prof": admin_prof,
        "patient_prof": patient_prof,
        "patient_entity": patient_entity,
    }


def test_doctor_with_valid_weekday_schedule_returns_slots(client: TestClient, schedule_test_env, db_session: Session):
    """Requirement 1: A doctor with a valid weekday schedule receives the expected available slots."""
    doc1 = schedule_test_env["doc1"]
    
    # Choose a Monday far in future: 2027-01-04 is a Monday
    monday_date = datetime.date(2027, 1, 4)
    assert monday_date.weekday() == 0

    response = client.get(f"/api/v1/doctors/{doc1.id}/availability?appointment_date={monday_date.isoformat()}")
    assert response.status_code == 200
    data = response.json()

    assert data["doctor_id"] == doc1.id
    assert data["has_schedule"] is True
    assert data["schedule_configured"] is True
    assert data["is_fully_booked"] is False
    # From 09:00 to 17:00 in 30 min intervals = 16 slots
    assert len(data["slots"]) == 16
    assert sum(1 for s in data["slots"] if s["is_available"]) == 16
    assert data["slots"][0]["start_time"] == "09:00:00"
    assert data["slots"][-1]["end_time"] == "17:00:00"


def test_doctor_without_schedule_returns_no_schedule_response(client: TestClient, schedule_test_env):
    """Requirement 2: A doctor without a schedule receives an accurate no-schedule response."""
    doc2 = schedule_test_env["doc2"]
    
    # 2027-01-04 is Monday
    monday_date = datetime.date(2027, 1, 4)

    response = client.get(f"/api/v1/doctors/{doc2.id}/availability?appointment_date={monday_date.isoformat()}")
    assert response.status_code == 200
    data = response.json()

    assert data["doctor_id"] == doc2.id
    assert data["has_schedule"] is False
    assert data["schedule_configured"] is False
    assert data["is_fully_booked"] is False
    assert len(data["slots"]) == 0
    assert data["next_available_date"] is None


def test_doctor_with_schedule_on_another_weekday_returns_correct_result_with_next_date(client: TestClient, schedule_test_env):
    """Requirement 3: A doctor with a schedule on another weekday receives correct result and next available date."""
    doc3 = schedule_test_env["doc3"]  # Has schedule ONLY on Tuesday (day_of_week=1)
    
    # Query for Monday 2027-01-04
    monday_date = datetime.date(2027, 1, 4)
    assert monday_date.weekday() == 0

    response = client.get(f"/api/v1/doctors/{doc3.id}/availability?appointment_date={monday_date.isoformat()}")
    assert response.status_code == 200
    data = response.json()

    assert data["doctor_id"] == doc3.id
    assert data["has_schedule"] is False
    assert data["schedule_configured"] is True  # Doctor HAS schedules configured, just not on Monday!
    assert data["is_fully_booked"] is False
    assert len(data["slots"]) == 0
    # Next available date should be Tuesday 2027-01-05
    assert data["next_available_date"] == "2027-01-05"


def test_booked_slot_exclusion_and_prevent_double_booking(client: TestClient, schedule_test_env, db_session: Session):
    """Requirements 4 & 5: Fully booked slots are marked unavailable and existing appointments prevent double booking."""
    doc1 = schedule_test_env["doc1"]
    patient_prof = schedule_test_env["patient_prof"]
    patient_entity = schedule_test_env["patient_entity"]
    monday_date = datetime.date(2027, 1, 4)

    # Book 09:00 to 09:30
    appt = Appointment(
        patient_id=patient_entity.id,
        doctor_id=doc1.id,
        hospital_id=doc1.hospital_id,
        appointment_date=monday_date,
        scheduled_start=datetime.time(9, 0),
        scheduled_end=datetime.time(9, 30),
        status=AppointmentStatus.BOOKED,
    )
    db_session.add(appt)
    db_session.commit()

    response = client.get(f"/api/v1/doctors/{doc1.id}/availability?appointment_date={monday_date.isoformat()}")
    assert response.status_code == 200
    data = response.json()

    assert len(data["slots"]) == 16
    assert sum(1 for s in data["slots"] if s["is_available"]) == 15
    # First slot (09:00:00) should be is_available=False
    slot_0900 = next(s for s in data["slots"] if s["start_time"] == "09:00:00")
    assert slot_0900["is_available"] is False

    # Second slot (09:30:00) should be is_available=True
    slot_0930 = next(s for s in data["slots"] if s["start_time"] == "09:30:00")
    assert slot_0930["is_available"] is True

    # Attempting to book the already booked slot must fail
    token = create_access_token(subject=patient_prof.auth_user_id, role="patient", hospital_id=doc1.hospital_id)
    headers = {"Authorization": f"Bearer {token}"}
    book_payload = {
        "patient_id": patient_entity.id,
        "doctor_id": doc1.id,
        "hospital_id": doc1.hospital_id,
        "appointment_date": monday_date.isoformat(),
        "scheduled_start": "09:00:00",
        "scheduled_end": "09:30:00",
        "consultation_mode": "in_person",
    }
    book_resp = client.post("/api/v1/appointments/", headers=headers, json=book_payload)
    assert book_resp.status_code == 409
    err_msg = (book_resp.json().get("error") or {}).get("message") or book_resp.json().get("detail", "")
    assert "overlaps with an existing booking" in err_msg.lower()


def test_past_appointment_date_cannot_be_booked(client: TestClient, schedule_test_env):
    """Requirement 6: Past appointment slots cannot be booked."""
    doc1 = schedule_test_env["doc1"]
    patient_prof = schedule_test_env["patient_prof"]
    patient_entity = schedule_test_env["patient_entity"]

    past_date = datetime.date(2020, 1, 6)  # Monday in past
    assert past_date.weekday() == 0

    token = create_access_token(subject=patient_prof.auth_user_id, role="patient", hospital_id=doc1.hospital_id)
    headers = {"Authorization": f"Bearer {token}"}
    book_payload = {
        "patient_id": patient_entity.id,
        "doctor_id": doc1.id,
        "hospital_id": doc1.hospital_id,
        "appointment_date": past_date.isoformat(),
        "scheduled_start": "09:00:00",
        "scheduled_end": "09:30:00",
        "consultation_mode": "in_person",
    }
    book_resp = client.post("/api/v1/appointments/", headers=headers, json=book_payload)
    assert book_resp.status_code == 400
    err_msg = (book_resp.json().get("error") or {}).get("message") or book_resp.json().get("detail", "")
    assert "past" in err_msg.lower()


def test_weekday_mapping_accuracy(client: TestClient, schedule_test_env):
    """Requirement 7: Weekday mapping is strictly ISO/Python compliant (0=Monday to 6=Sunday)."""
    doc1 = schedule_test_env["doc1"]

    # Test all 7 days of a specific week: 2027-01-04 (Mon) to 2027-01-10 (Sun)
    expected_active_days = {
        datetime.date(2027, 1, 4): True,   # Monday (0)
        datetime.date(2027, 1, 5): True,   # Tuesday (1)
        datetime.date(2027, 1, 6): True,   # Wednesday (2)
        datetime.date(2027, 1, 7): True,   # Thursday (3)
        datetime.date(2027, 1, 8): True,   # Friday (4)
        datetime.date(2027, 1, 9): False,  # Saturday (5)
        datetime.date(2027, 1, 10): False, # Sunday (6)
    }

    for dt, expected_has_schedule in expected_active_days.items():
        resp = client.get(f"/api/v1/doctors/{doc1.id}/availability?appointment_date={dt.isoformat()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_schedule"] is expected_has_schedule, f"Failed for {dt} (weekday {dt.weekday()})"


def test_new_doctor_onboarding_creates_default_schedule(client: TestClient, schedule_test_env, db_session: Session):
    """Requirement 9: New doctor onboarding creates expected schedule without duplicates."""
    admin = schedule_test_env["admin_prof"]
    hospital = schedule_test_env["hospital"]

    admin_token = create_access_token(subject=admin.auth_user_id, role="admin", hospital_id=hospital.id)
    headers = {"Authorization": f"Bearer {admin_token}"}

    unique_id = str(uuid.uuid4())[:8]
    onboard_payload = {
        "full_name": f"Dr. New Onboard {unique_id}",
        "email": f"new.onboard.{unique_id}@hospital.org",
        "password": "Password123!",
        "license_number": f"LIC-NEW-{unique_id}",
        "hospital_id": hospital.id,
        "years_of_experience": 5,
        "consultation_mode": "both",
    }

    resp = client.post("/api/v1/admin/doctors/onboard", headers=headers, json=onboard_payload)
    assert resp.status_code == 201
    doctor_id = resp.json()["entity_id"]

    # Verify 5 DoctorSchedule records created (days 0 to 4)
    schedules = (
        db_session.query(DoctorSchedule)
        .filter(DoctorSchedule.doctor_id == doctor_id)
        .order_by(DoctorSchedule.day_of_week)
        .all()
    )
    assert len(schedules) == 5
    for idx, s in enumerate(schedules):
        assert s.day_of_week == idx
        assert s.start_time == datetime.time(9, 0)
        assert s.end_time == datetime.time(17, 0)
        assert s.slot_duration_minutes == 30
        assert s.is_active is True


def test_existing_schedules_preserved_during_onboarding_retries(schedule_test_env, db_session: Session):
    """Requirement 10: Existing schedules are preserved during retry and not duplicated."""
    doc1 = schedule_test_env["doc1"]
    
    # Doc 1 already has 5 schedules. Calling create_default_schedules with overwrite=False must preserve them.
    created = doctor_service.create_default_schedules(db_session, doc1.id, overwrite=False)
    assert len(created) == 5

    # Total schedules count must still be exactly 5
    total = db_session.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doc1.id).count()
    assert total == 5


def test_admin_initialize_default_schedules_and_repair_workflow(client: TestClient, schedule_test_env, db_session: Session):
    """Requirement 11 & 12: Admin can initialize schedules for unscheduled doctor and execute dry-run repair."""
    admin = schedule_test_env["admin_prof"]
    hospital = schedule_test_env["hospital"]
    doc2 = schedule_test_env["doc2"]  # Unscheduled doctor

    admin_token = create_access_token(subject=admin.auth_user_id, role="admin", hospital_id=hospital.id)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Test Dry Run Repair
    repair_dry_resp = client.post(
        f"/api/v1/admin/doctors/repair-schedules?hospital_id={hospital.id}&dry_run=true",
        headers=headers,
    )
    assert repair_dry_resp.status_code == 200
    dry_data = repair_dry_resp.json()
    assert dry_data["dry_run"] is True
    assert dry_data["unscheduled_count"] >= 1
    # Ensure doctor 2 is in repair candidate details
    candidate_ids = [d["doctor_id"] for d in dry_data["doctors"]]
    assert doc2.id in candidate_ids

    # Doc 2 must STILL have 0 schedules after dry-run
    count_before = db_session.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doc2.id).count()
    assert count_before == 0

    # 2. Test Initialize Default Schedules endpoint for Doc 2
    init_resp = client.post(
        f"/api/v1/admin/doctors/{doc2.id}/schedules/initialize-default?overwrite=false",
        headers=headers,
    )
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert len(init_data) == 5

    # Verify doc 2 now has 5 schedules
    count_after = db_session.query(DoctorSchedule).filter(DoctorSchedule.doctor_id == doc2.id).count()
    assert count_after == 5

    # 3. Verify doc 2 availability now succeeds
    monday_date = datetime.date(2027, 1, 4)
    avail_resp = client.get(f"/api/v1/doctors/{doc2.id}/availability?appointment_date={monday_date.isoformat()}")
    assert avail_resp.status_code == 200
    avail_data = avail_resp.json()
    assert avail_data["has_schedule"] is True
    assert avail_data["schedule_configured"] is True
    assert len(avail_data["slots"]) == 16
