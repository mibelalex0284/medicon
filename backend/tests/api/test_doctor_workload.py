import uuid
from datetime import datetime, date, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.consultation import Consultation, ConsultationStatus
from app.models.department import Department
from app.models.doctor import Doctor
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.profile import Profile
from app.models.queue_entry import QueueEntry, QueueStatus


def test_doctor_workload_requires_doctor(client: TestClient, patient_headers: dict, admin_headers: dict):
    # Unauthenticated
    res = client.get("/api/v1/doctors/me/workload")
    assert res.status_code == 401

    # Forbidden for patient
    res = client.get("/api/v1/doctors/me/workload", headers=patient_headers)
    assert res.status_code == 403

    # Forbidden for admin
    res = client.get("/api/v1/doctors/me/workload", headers=admin_headers)
    assert res.status_code == 403


def test_doctor_workload_empty_database(
    client: TestClient,
    db_session: Session,
    auth_seeded_db: Session,
    doctor_headers: dict,
):
    # Ensure Hospital and Department exist
    hosp = Hospital(id="hosp-001", name="City Hospital", code="CH1", is_active=True)
    dept = Department(id=str(uuid.uuid4()), hospital_id="hosp-001", name="General Medicine", code="GEN", is_active=True)
    db_session.add_all([hosp, dept])

    # Ensure Doctor record exists for doctor-456
    doc_prof = db_session.query(Profile).filter(Profile.auth_user_id == "doctor-456").first()
    doctor = Doctor(
        id=str(uuid.uuid4()),
        profile_id=doc_prof.id,
        hospital_id="hosp-001",
        department_id=dept.id,
        license_number="LIC-456",
        is_active=True,
    )
    db_session.add(doctor)
    db_session.commit()

    res = client.get("/api/v1/doctors/me/workload", headers=doctor_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["patients_completed_today"] == 0
    assert data["active_in_room_or_waiting"] == 0
    assert data["mean_consult_duration_minutes"] == 0.0
    assert data["clinical_utilization_rate"] == 0.0
    assert data["hourly_flow"] == []


def test_doctor_workload_metrics_and_isolation(
    client: TestClient,
    db_session: Session,
    auth_seeded_db: Session,
    doctor_headers: dict,
):
    today = date.today()
    now_utc = datetime.now(timezone.utc)

    # 1. Setup Hospital
    hosp = Hospital(id="hosp-001", name="City Hospital", code="CH1", is_active=True)
    dept1 = Department(id=str(uuid.uuid4()), hospital_id="hosp-001", name="Cardiology Clinic", code="CARD", is_active=True)
    dept2 = Department(id=str(uuid.uuid4()), hospital_id="hosp-001", name="General Clinic", code="GEN", is_active=True)
    db_session.add_all([hosp, dept1, dept2])

    # 2. Setup Doctor 1 (me) and Doctor 2 (other)
    doc_prof1 = db_session.query(Profile).filter(Profile.auth_user_id == "doctor-456").first()
    doc1 = Doctor(
        id=str(uuid.uuid4()),
        profile_id=doc_prof1.id,
        hospital_id="hosp-001",
        department_id=dept1.id,
        license_number="LIC-1",
        is_active=True,
    )
    doc_prof2 = db_session.query(Profile).filter(Profile.auth_user_id == "doctor-other").first()
    doc2 = Doctor(
        id=str(uuid.uuid4()),
        profile_id=doc_prof2.id,
        hospital_id="hosp-001",
        department_id=dept2.id,
        license_number="LIC-2",
        is_active=True,
    )
    db_session.add_all([doc1, doc2])

    # 3. Setup Patient
    pat_prof = db_session.query(Profile).filter(Profile.auth_user_id == "patient-123").first()
    pat = Patient(
        id=str(uuid.uuid4()),
        profile_id=pat_prof.id,
        date_of_birth=date(1992, 5, 10),
    )
    db_session.add(pat)
    db_session.commit()

    # 4. Doc 1: 1 completed consultation (duration: 900s = 15.0m) and 1 waiting in queue
    q1 = QueueEntry(
        id=str(uuid.uuid4()),
        appointment_id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id="hosp-001",
        queue_date=today,
        token_number="C01",
        status=QueueStatus.COMPLETED,
        checked_in_at=now_utc - timedelta(minutes=30),
        called_at=now_utc - timedelta(minutes=15),
        completed_at=now_utc,
    )
    q_wait = QueueEntry(
        id=str(uuid.uuid4()),
        appointment_id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id="hosp-001",
        queue_date=today,
        token_number="C02",
        status=QueueStatus.WAITING,
        checked_in_at=now_utc - timedelta(minutes=5),
    )
    db_session.add_all([q1, q_wait])

    c1 = Consultation(
        id=str(uuid.uuid4()),
        queue_entry_id=q1.id,
        appointment_id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id="hosp-001",
        started_at=now_utc - timedelta(minutes=15),
        completed_at=now_utc,
        status=ConsultationStatus.COMPLETED,
        duration_seconds=900,
    )
    db_session.add(c1)

    # 5. Doc 2 (Other Doctor): 2 completed consultations and 2 waiting (should NOT appear in Doc 1 workload)
    q_other = QueueEntry(
        id=str(uuid.uuid4()),
        appointment_id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc2.id,
        hospital_id="hosp-001",
        queue_date=today,
        token_number="D01",
        status=QueueStatus.WAITING,
        checked_in_at=now_utc - timedelta(minutes=5),
    )
    c_other = Consultation(
        id=str(uuid.uuid4()),
        queue_entry_id=str(uuid.uuid4()),
        appointment_id=str(uuid.uuid4()),
        patient_id=pat.id,
        doctor_id=doc2.id,
        hospital_id="hosp-001",
        started_at=now_utc - timedelta(minutes=20),
        completed_at=now_utc,
        status=ConsultationStatus.COMPLETED,
        duration_seconds=1200,
    )
    db_session.add_all([q_other, c_other])
    db_session.commit()

    # Query workload for Doc 1
    res = client.get("/api/v1/doctors/me/workload", headers=doctor_headers)
    assert res.status_code == 200
    data = res.json()

    # Verify metrics strictly isolated to Doc 1
    assert data["patients_completed_today"] == 1
    assert data["active_in_room_or_waiting"] == 1
    assert round(data["mean_consult_duration_minutes"], 1) == 15.0
    assert len(data["hourly_flow"]) == 1
    assert data["hourly_flow"][0]["count"] == 1
    assert data["hourly_flow"][0]["avg_minutes"] == 15.0
