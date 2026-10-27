import uuid
from datetime import datetime, date, time, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.appointment import Appointment, AppointmentStatus
from app.models.consultation import Consultation, ConsultationStatus
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.profile import Profile
from app.models.queue_entry import QueueEntry, QueueStatus


def test_admin_analytics_requires_admin(client: TestClient, patient_headers: dict, doctor_headers: dict):
    # Unauthenticated
    res = client.get("/api/v1/admin/analytics/overview")
    assert res.status_code == 401

    # Forbidden for patient
    res = client.get("/api/v1/admin/analytics/overview", headers=patient_headers)
    assert res.status_code == 403

    # Forbidden for doctor
    res = client.get("/api/v1/admin/analytics/overview", headers=doctor_headers)
    assert res.status_code == 403


def test_admin_analytics_empty_database(client: TestClient, auth_seeded_db: Session, admin_headers: dict):
    res = client.get("/api/v1/admin/analytics/overview", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_patients_today"] == 0
    assert data["active_queue_count"] == 0
    assert data["completed_today"] == 0
    assert data["mean_wait_minutes"] == 0.0
    assert data["p90_wait_minutes"] == 0.0
    assert data["doctor_utilization_rate"] == 0.0
    assert data["punctuality_rate"] == 100.0
    assert data["departments"] == []
    assert len(data["hourly_flow"]) == 10
    assert all(h["arrivals"] == 0 and h["completed"] == 0 for h in data["hourly_flow"])


def test_admin_analytics_with_data_and_tenant_isolation(
    client: TestClient,
    db_session: Session,
    auth_seeded_db: Session,
    admin_headers: dict,
):
    today = date.today()
    now_utc = datetime.now(timezone.utc)

    # 1. Create Hospital 1 & Hospital 2
    hosp1 = Hospital(id="hosp-001", name="City General", code="CGH", is_active=True)
    hosp2 = Hospital(id="hosp-002", name="Metro Health", code="MTH", is_active=True)
    db_session.add_all([hosp1, hosp2])

    # 2. Create Departments
    dept1 = Department(id=str(uuid.uuid4()), hospital_id="hosp-001", name="Cardiology Clinic", code="CARD", is_active=True)
    dept2 = Department(id=str(uuid.uuid4()), hospital_id="hosp-002", name="Neurology Clinic", code="NEUR", is_active=True)
    db_session.add_all([dept1, dept2])

    # 3. Create Doctors
    doc_prof1 = db_session.query(Profile).filter(Profile.auth_user_id == "doctor-456").first()
    doc1 = Doctor(
        id=str(uuid.uuid4()),
        profile_id=doc_prof1.id,
        hospital_id="hosp-001",
        department_id=dept1.id,
        license_number="LIC-111",
        is_active=True,
    )
    doc_prof2 = db_session.query(Profile).filter(Profile.auth_user_id == "doctor-other").first()
    doc2 = Doctor(
        id=str(uuid.uuid4()),
        profile_id=doc_prof2.id,
        hospital_id="hosp-002",
        department_id=dept2.id,
        license_number="LIC-222",
        is_active=True,
    )
    db_session.add_all([doc1, doc2])

    # 4. Create Patient
    pat_prof = db_session.query(Profile).filter(Profile.auth_user_id == "patient-123").first()
    pat = Patient(
        id=str(uuid.uuid4()),
        profile_id=pat_prof.id,
        date_of_birth=date(1990, 1, 1),
    )
    db_session.add(pat)
    db_session.commit()

    # 5. Add Hospital 1 Appointment (Completed)
    appt1 = Appointment(
        id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id="hosp-001",
        appointment_date=today,
        scheduled_start=time(9, 0),
        scheduled_end=time(9, 30),
        appointment_type="in_person",
        status=AppointmentStatus.COMPLETED,
    )
    # Add Hospital 2 Appointment (Other tenant)
    appt_other = Appointment(
        id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc2.id,
        hospital_id="hosp-002",
        appointment_date=today,
        scheduled_start=time(10, 0),
        scheduled_end=time(10, 30),
        appointment_type="in_person",
        status=AppointmentStatus.COMPLETED,
    )
    db_session.add_all([appt1, appt_other])
    db_session.commit()

    # 6. Queue entry for Hosp 1 with checked_in_at 20 mins before called_at
    check_in_time = now_utc - timedelta(minutes=40)
    called_time = now_utc - timedelta(minutes=20)
    q1 = QueueEntry(
        id=str(uuid.uuid4()),
        appointment_id=appt1.id,
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id="hosp-001",
        queue_date=today,
        token_number="A01",
        status=QueueStatus.COMPLETED,
        checked_in_at=check_in_time,
        called_at=called_time,
        completed_at=now_utc,
    )
    # Queue entry active (waiting)
    q_active = QueueEntry(
        id=str(uuid.uuid4()),
        appointment_id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id="hosp-001",
        queue_date=today,
        token_number="A02",
        status=QueueStatus.WAITING,
        checked_in_at=now_utc - timedelta(minutes=10),
    )
    db_session.add_all([q1, q_active])

    # 7. Consultation for Hosp 1 (duration: 1200 seconds = 20 minutes)
    c1 = Consultation(
        id=str(uuid.uuid4()),
        queue_entry_id=q1.id,
        appointment_id=appt1.id,
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id="hosp-001",
        started_at=called_time,
        completed_at=now_utc,
        status=ConsultationStatus.COMPLETED,
        duration_seconds=1200,
    )
    db_session.add(c1)
    db_session.commit()

    # Execute analytics overview request as Admin 789 (scoped to hosp-001)
    res = client.get("/api/v1/admin/analytics/overview", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()

    # Assert tenant isolation (Hospital 1 records only)
    assert data["total_patients_today"] == 1
    assert data["active_queue_count"] == 1
    assert data["completed_today"] == 1
    # Mean wait time for completed: called_at - checked_in_at = 20 minutes
    assert round(data["mean_wait_minutes"], 1) == 20.0
    assert round(data["p90_wait_minutes"], 1) == 20.0
    # Department metrics should only have Cardiology Clinic
    assert len(data["departments"]) == 1
    assert data["departments"][0]["name"] == "Cardiology Clinic"
    assert data["departments"][0]["total_waiting"] == 1
