import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.profile import UserRole
from app.schemas.doctor import DoctorCreate
from app.schemas.doctor_schedule import DoctorScheduleCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service


def test_complete_outpatient_operational_workflow(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    doctor_headers: dict,
):
    """Verifies the complete outpatient workflow:
    Book -> Check-In -> Token -> Queue View -> Call -> Start -> Complete
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()

    # 1. Setup hospital
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="St. Hope Hospital", code="SHH-01")
    )

    # 2. Setup doctor (tied to doctor_headers auth: doctor-456)
    doc_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Marcus Welby",
            email="dr.welby@sthope.org",
            hospital_id=hosp.id,
        ),
    )
    doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc_prof.id,
            hospital_id=hosp.id,
            license_number="LIC-WELBY-1",
        ),
    )
    # Add schedule covering today
    doctor_service.add_schedule(
        db_session,
        doctor_id=doc.id,
        obj_in=DoctorScheduleCreate(
            doctor_id=doc.id,
            hospital_id=hosp.id,
            day_of_week=today.weekday(),
            start_time=datetime.time(8, 0),
            end_time=datetime.time(18, 0),
            slot_duration_minutes=30,
        ),
    )

    # 3. Setup patient (tied to patient_headers auth: patient-123)
    pat_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Arthur Dent",
            email="dent@earth.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=pat_prof.id,
            date_of_birth=datetime.date(1980, 4, 1),
        ),
    )

    # Step 1: Patient checks availability
    res_avail = client.get(
        f"/api/v1/doctors/{doc.id}/availability?appointment_date={today.isoformat()}"
    )
    assert res_avail.status_code == 200
    slots = res_avail.json()["slots"]
    assert len(slots) > 0

    # Step 2: Patient books appointment
    book_payload = {
        "patient_id": patient.id,
        "doctor_id": doc.id,
        "hospital_id": hosp.id,
        "appointment_date": today.isoformat(),
        "scheduled_start": "09:00:00",
        "scheduled_end": "09:30:00",
        "reason": "Routine Checkup",
    }
    res_book = client.post("/api/v1/appointments", json=book_payload, headers=patient_headers)
    assert res_book.status_code == 201
    appt_data = res_book.json()
    appointment_id = appt_data["id"]
    assert appt_data["status"] == "BOOKED"

    # Step 3: Patient checks in
    res_checkin = client.post(
        f"/api/v1/appointments/{appointment_id}/check-in",
        headers=patient_headers,
    )
    assert res_checkin.status_code == 201
    queue_data = res_checkin.json()
    queue_entry_id = queue_data["id"]
    assert queue_data["token_number"] == "A01"
    assert queue_data["status"] == "WAITING"

    # Step 4: Patient views own queue status
    res_q_status = client.get("/api/v1/patients/me/queue", headers=patient_headers)
    assert res_q_status.status_code == 200
    p_status = res_q_status.json()
    assert p_status["token_number"] == "A01"
    assert p_status["patients_ahead"] == 0
    assert p_status["wait_estimate"]["expected_minutes"] >= 5

    # Step 5: Doctor views current queue
    res_doc_q = client.get(f"/api/v1/queues/{doc.id}/current", headers=doctor_headers)
    assert res_doc_q.status_code == 200
    doc_entries = res_doc_q.json()
    assert len(doc_entries) == 1
    assert doc_entries[0]["id"] == queue_entry_id

    # Step 6: Doctor calls patient
    res_call = client.post(f"/api/v1/queues/{queue_entry_id}/call", headers=doctor_headers)
    assert res_call.status_code == 200
    assert res_call.json()["status"] == "CALLED"

    # Step 7: Doctor starts consultation
    res_start = client.post(f"/api/v1/queues/{queue_entry_id}/start", headers=doctor_headers)
    assert res_start.status_code == 200
    consultation_data = res_start.json()
    assert consultation_data["status"] == "IN_PROGRESS"
    assert consultation_data["started_at"] is not None

    # Step 8: Doctor completes consultation
    res_complete = client.post(
        f"/api/v1/queues/{queue_entry_id}/complete", headers=doctor_headers
    )
    assert res_complete.status_code == 200
    final_consult = res_complete.json()
    assert final_consult["status"] == "COMPLETED"
    assert final_consult["completed_at"] is not None
    assert final_consult["duration_seconds"] is not None

    # Verify Appointment is now COMPLETED
    res_appt_final = client.get(
        f"/api/v1/appointments/{appointment_id}", headers=patient_headers
    )
    assert res_appt_final.status_code == 200
    assert res_appt_final.json()["status"] == "COMPLETED"


def test_cross_patient_booking_and_checkin_forbidden(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    other_patient_headers: dict,
):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Hosp Sec", code="HSEC-01")
    )
    # Doctor
    doc_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-sec",
            role=UserRole.DOCTOR,
            full_name="Dr. Sec",
            email="sec@clinic.org",
            hospital_id=hosp.id,
        ),
    )
    doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(profile_id=doc_prof.id, hospital_id=hosp.id, license_number="LIC-SEC"),
    )
    doctor_service.add_schedule(
        db_session,
        doctor_id=doc.id,
        obj_in=DoctorScheduleCreate(
            doctor_id=doc.id,
            hospital_id=hosp.id,
            day_of_week=today.weekday(),
            start_time=datetime.time(8, 0),
            end_time=datetime.time(18, 0),
        ),
    )

    # Patient 1 (patient-123)
    p1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Patient One",
            email="p1@test.org",
        ),
    )
    p1 = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p1_prof.id, date_of_birth=datetime.date(1990, 1, 1)),
    )

    # Patient 2 (patient-999)
    p2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-999",
            role=UserRole.PATIENT,
            full_name="Patient Two",
            email="p2@test.org",
        ),
    )
    p2 = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p2_prof.id, date_of_birth=datetime.date(1995, 1, 1)),
    )

    # 1. Patient 1 attempts to book using Patient 2's ID -> Forbidden
    res_fraud_book = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": p2.id,
            "doctor_id": doc.id,
            "hospital_id": hosp.id,
            "appointment_date": today.isoformat(),
            "scheduled_start": "10:00:00",
            "scheduled_end": "10:15:00",
        },
        headers=patient_headers,
    )
    assert res_fraud_book.status_code == 403
    assert res_fraud_book.json()["error"]["code"] == "FORBIDDEN_PATIENT_BOOKING"

    # 2. Patient 1 books own appointment
    res_valid_book = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": p1.id,
            "doctor_id": doc.id,
            "hospital_id": hosp.id,
            "appointment_date": today.isoformat(),
            "scheduled_start": "10:00:00",
            "scheduled_end": "10:15:00",
        },
        headers=patient_headers,
    )
    assert res_valid_book.status_code == 201
    appt_id = res_valid_book.json()["id"]

    # 3. Patient 2 attempts to check in Patient 1's appointment -> Forbidden
    res_fraud_checkin = client.post(
        f"/api/v1/appointments/{appt_id}/check-in",
        headers=other_patient_headers,
    )
    assert res_fraud_checkin.status_code == 403
    assert res_fraud_checkin.json()["error"]["code"] == "FORBIDDEN_CHECK_IN"


def test_doctor_cannot_operate_another_doctors_queue(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    other_hospital_doctor_headers: dict,
):
    today = datetime.datetime.now(datetime.timezone.utc).date()
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Doc Op Hosp", code="DOP-01")
    )

    # Doctor 1 (doctor-456)
    d1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Assigned",
            email="assigned@clinic.org",
            hospital_id=hosp.id,
        ),
    )
    d1 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(profile_id=d1_prof.id, hospital_id=hosp.id, license_number="LIC-D1"),
    )
    doctor_service.add_schedule(
        db_session,
        doctor_id=d1.id,
        obj_in=DoctorScheduleCreate(
            doctor_id=d1.id,
            hospital_id=hosp.id,
            day_of_week=today.weekday(),
            start_time=datetime.time(8, 0),
            end_time=datetime.time(18, 0),
        ),
    )

    # Doctor 2 (doctor-other)
    d2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-other",
            role=UserRole.DOCTOR,
            full_name="Dr. Intruder",
            email="intruder@clinic.org",
            hospital_id=hosp.id,
        ),
    )
    doctor_service.create_doctor(
        db_session,
        DoctorCreate(profile_id=d2_prof.id, hospital_id=hosp.id, license_number="LIC-D2"),
    )

    # Patient (patient-123)
    p_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Patient User",
            email="user@test.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p_prof.id, date_of_birth=datetime.date(1990, 1, 1)),
    )

    # Book and check in with Doctor 1
    res_book = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient.id,
            "doctor_id": d1.id,
            "hospital_id": hosp.id,
            "appointment_date": today.isoformat(),
            "scheduled_start": "11:00:00",
            "scheduled_end": "11:15:00",
        },
        headers=patient_headers,
    )
    appt_id = res_book.json()["id"]
    res_checkin = client.post(
        f"/api/v1/appointments/{appt_id}/check-in",
        headers=patient_headers,
    )
    queue_entry_id = res_checkin.json()["id"]

    # Doctor 2 (other_hospital_doctor_headers) attempts to call Doctor 1's patient -> Forbidden
    res_call_intruder = client.post(
        f"/api/v1/queues/{queue_entry_id}/call",
        headers=other_hospital_doctor_headers,
    )
    assert res_call_intruder.status_code == 403
    assert res_call_intruder.json()["error"]["code"] == "NOT_ASSIGNED_DOCTOR"
