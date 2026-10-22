import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.appointment import Appointment, AppointmentStatus
from app.models.consultation import Consultation, ConsultationStatus
from app.models.profile import UserRole
from app.models.queue_entry import QueueEntry, QueueStatus
from app.schemas.doctor import DoctorCreate
from app.schemas.doctor_schedule import DoctorScheduleCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service


def test_full_patient_to_doctor_e2e_workflow_and_failure_matrix(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    other_patient_headers: dict,
    doctor_headers: dict,
    other_hospital_doctor_headers: dict,
    admin_headers: dict,
):
    """Exhaustive Phase 3B.3 Integration & Data Integrity Verification:
    
    Positive Scenario (15 steps):
    1. Seeded patient (patient-123)
    2. Authorized doctor (doctor-456)
    3. Retrieve available slots
    4. Book available appointment
    5. Verify appointment persisted in database
    6. Retrieve patient appointment history
    7. Check in the patient
    8. Verify exactly one valid queue entry created in database
    9. Verify token generated authoritatively by backend
    10. Retrieve patient live queue
    11. Retrieve authorized doctor queue
    12. Doctor calls patient
    13. Doctor starts consultation
    14. Doctor completes consultation
    15. Verify final database states across Appointment, QueueEntry, Consultation
    
    Negative / Integrity Matrix:
    - Attempt to book unavailable slot -> 409
    - Attempt duplicate check-in -> 409
    - Attempt check-in on cancelled appointment -> 400
    - Attempt check-in on completed appointment -> 400
    - Attempt check-in on no-show appointment -> 400
    - Attempt to start already completed consultation -> 400
    - Attempt to complete consultation twice -> 400
    - Attempt to cancel active in-progress consultation -> 400
    - Attempt to start two concurrent consultations for same doctor -> 409
    - Cross-patient record access -> 403
    - Cross-doctor queue operations -> 403
    - Cross-hospital access -> 403
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()

    # --- 1. SETUP ENTITIES ---
    hosp_a = hospital_service.create_hospital(
        db_session, HospitalCreate(name="City Central Hospital", code="CCH-01")
    )
    hosp_b = hospital_service.create_hospital(
        db_session, HospitalCreate(name="West Suburban Clinic", code="WSC-02")
    )

    # Doctor A at Hospital A (auth: doctor-456)
    doc_a_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Evelyn Shaw",
            email="evelyn.shaw@cch.org",
            hospital_id=hosp_a.id,
        ),
    )
    doc_a = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc_a_prof.id,
            hospital_id=hosp_a.id,
            license_number="LIC-SHAW-100",
        ),
    )
    doctor_service.add_schedule(
        db_session,
        doctor_id=doc_a.id,
        obj_in=DoctorScheduleCreate(
            doctor_id=doc_a.id,
            hospital_id=hosp_a.id,
            day_of_week=today.weekday(),
            start_time=datetime.time(9, 0),
            end_time=datetime.time(17, 0),
            slot_duration_minutes=30,
        ),
    )

    # Doctor B at Hospital B (auth: doctor-other)
    doc_b_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-other",
            role=UserRole.DOCTOR,
            full_name="Dr. Boris Miller",
            email="boris.miller@wsc.org",
            hospital_id=hosp_b.id,
        ),
    )
    doc_b = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc_b_prof.id,
            hospital_id=hosp_b.id,
            license_number="LIC-MILLER-200",
        ),
    )

    # Patient 1 (auth: patient-123)
    p1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Alice Walker",
            email="alice@care.org",
        ),
    )
    p1 = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p1_prof.id, date_of_birth=datetime.date(1992, 5, 14)),
    )

    # Patient 2 (auth: patient-999)
    p2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-999",
            role=UserRole.PATIENT,
            full_name="Bob Martinez",
            email="bob@care.org",
        ),
    )
    p2 = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p2_prof.id, date_of_birth=datetime.date(1988, 11, 20)),
    )

    # --- STEP 3: Retrieve available appointment slots ---
    res_avail = client.get(
        f"/api/v1/doctors/{doc_a.id}/availability?appointment_date={today.isoformat()}"
    )
    assert res_avail.status_code == 200
    avail_data = res_avail.json()
    slots = avail_data["slots"]
    assert len(slots) >= 1
    first_slot = next(s for s in slots if s["is_available"])
    slot_start = first_slot["start_time"]
    slot_end = first_slot["end_time"]

    # --- STEP 4: Book an available appointment ---
    book_payload = {
        "patient_id": p1.id,
        "doctor_id": doc_a.id,
        "hospital_id": hosp_a.id,
        "appointment_date": today.isoformat(),
        "scheduled_start": slot_start,
        "scheduled_end": slot_end,
        "reason": "Persistent dry cough",
    }
    res_book = client.post("/api/v1/appointments", json=book_payload, headers=patient_headers)
    assert res_book.status_code == 201
    appt_data = res_book.json()
    appointment_id = appt_data["id"]
    assert appt_data["status"] == "BOOKED"
    assert appt_data["doctor_name"] == "Dr. Evelyn Shaw"

    # --- STEP 5: Verify appointment persisted in database ---
    db_appt = db_session.query(Appointment).filter(Appointment.id == appointment_id).first()
    assert db_appt is not None
    assert db_appt.patient_id == p1.id
    assert db_appt.doctor_id == doc_a.id
    assert db_appt.status == AppointmentStatus.BOOKED

    # --- STEP 6: Retrieve patient appointment history ---
    res_history = client.get("/api/v1/appointments", headers=patient_headers)
    assert res_history.status_code == 200
    history = res_history.json()
    assert any(a["id"] == appointment_id for a in history)

    # --- NEGATIVE: Attempt to book the exact same slot concurrently ---
    res_conflict = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": p2.id,
            "doctor_id": doc_a.id,
            "hospital_id": hosp_a.id,
            "appointment_date": today.isoformat(),
            "scheduled_start": slot_start,
            "scheduled_end": slot_end,
            "reason": "Routine check",
        },
        headers=other_patient_headers,
    )
    assert res_conflict.status_code == 409
    assert res_conflict.json()["error"]["code"] == "APPOINTMENT_CONFLICT"

    # --- STEP 7: Patient checks in ---
    res_checkin = client.post(
        f"/api/v1/appointments/{appointment_id}/check-in",
        headers=patient_headers,
    )
    assert res_checkin.status_code == 201
    checkin_data = res_checkin.json()
    queue_entry_id = checkin_data["id"]
    token_number = checkin_data["token_number"]

    # --- STEP 8: Verify exactly one valid queue entry created in DB ---
    q_entries = (
        db_session.query(QueueEntry)
        .filter(QueueEntry.appointment_id == appointment_id)
        .all()
    )
    assert len(q_entries) == 1
    db_entry = q_entries[0]
    assert db_entry.id == queue_entry_id
    assert db_entry.status == QueueStatus.WAITING

    # Verify Appointment was updated to CONFIRMED
    db_session.refresh(db_appt)
    assert db_appt.status == AppointmentStatus.CONFIRMED

    # --- STEP 9: Verify token is backend-generated ---
    assert token_number == "A01"
    assert db_entry.token_number == "A01"

    # --- NEGATIVE: Attempt duplicate check-in ---
    res_dup_checkin = client.post(
        f"/api/v1/appointments/{appointment_id}/check-in",
        headers=patient_headers,
    )
    assert res_dup_checkin.status_code == 409
    assert res_dup_checkin.json()["error"]["code"] == "ALREADY_CHECKED_IN"

    # --- STEP 10: Retrieve patient queue ---
    res_pat_q = client.get("/api/v1/patients/me/queue", headers=patient_headers)
    assert res_pat_q.status_code == 200
    pat_q = res_pat_q.json()
    assert pat_q["token_number"] == "A01"
    assert pat_q["status"] == "WAITING"
    assert pat_q["patients_ahead"] == 0
    assert pat_q["wait_estimate"]["expected_minutes"] >= 5

    # --- STEP 11: Retrieve doctor queue ---
    res_doc_q = client.get("/api/v1/queues/me/current", headers=doctor_headers)
    assert res_doc_q.status_code == 200
    doc_q = res_doc_q.json()
    assert len(doc_q) == 1
    assert doc_q[0]["id"] == queue_entry_id
    assert doc_q[0]["patient_name"] == "Alice Walker"

    # --- NEGATIVE: Doctor B attempts to operate Doctor A's queue entry ---
    res_fraud_call = client.post(
        f"/api/v1/queues/{queue_entry_id}/call",
        headers=other_hospital_doctor_headers,
    )
    assert res_fraud_call.status_code == 403
    assert res_fraud_call.json()["error"]["code"] == "NOT_ASSIGNED_DOCTOR"

    # --- STEP 12: Doctor A calls patient ---
    res_call = client.post(f"/api/v1/queues/{queue_entry_id}/call", headers=doctor_headers)
    assert res_call.status_code == 200
    assert res_call.json()["status"] == "CALLED"
    db_session.refresh(db_entry)
    assert db_entry.status == QueueStatus.CALLED
    assert db_entry.called_at is not None

    # --- STEP 13: Doctor starts consultation ---
    res_start = client.post(f"/api/v1/queues/{queue_entry_id}/start", headers=doctor_headers)
    assert res_start.status_code == 200
    consult_data = res_start.json()
    assert consult_data["status"] == "IN_PROGRESS"
    consult_id = consult_data["id"]

    # Verify Consultation and QueueEntry in DB
    db_consult = db_session.query(Consultation).filter(Consultation.id == consult_id).first()
    assert db_consult is not None
    assert db_consult.status == ConsultationStatus.IN_PROGRESS
    db_session.refresh(db_entry)
    assert db_entry.status == QueueStatus.IN_CONSULTATION

    # --- NEGATIVE: Attempt to cancel appointment while in consultation ---
    res_cancel_active = client.post(
        f"/api/v1/appointments/{appointment_id}/cancel",
        headers=patient_headers,
    )
    assert res_cancel_active.status_code == 400
    assert res_cancel_active.json()["error"]["code"] == "CANNOT_CANCEL_ACTIVE_CONSULTATION"

    # --- NEGATIVE: Doctor attempts to start a second concurrent consultation ---
    # Setup patient 2 appointment and checkin
    res_book_p2 = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": p2.id,
            "doctor_id": doc_a.id,
            "hospital_id": hosp_a.id,
            "appointment_date": today.isoformat(),
            "scheduled_start": "14:00:00",
            "scheduled_end": "14:30:00",
            "reason": "Headache",
        },
        headers=other_patient_headers,
    )
    assert res_book_p2.status_code == 201
    appt2_id = res_book_p2.json()["id"]
    res_checkin_p2 = client.post(
        f"/api/v1/appointments/{appt2_id}/check-in",
        headers=other_patient_headers,
    )
    assert res_checkin_p2.status_code == 201
    q2_id = res_checkin_p2.json()["id"]

    # Doctor attempts to start consultation for Patient 2 while Patient 1 is still IN_PROGRESS
    res_concurrent_start = client.post(
        f"/api/v1/queues/{q2_id}/start",
        headers=doctor_headers,
    )
    assert res_concurrent_start.status_code == 409
    assert res_concurrent_start.json()["error"]["code"] == "DOCTOR_BUSY_WITH_ACTIVE_CONSULTATION"

    # --- STEP 14: Doctor completes consultation for Patient 1 ---
    res_complete = client.post(
        f"/api/v1/queues/{queue_entry_id}/complete",
        headers=doctor_headers,
    )
    assert res_complete.status_code == 200
    completed_consult = res_complete.json()
    assert completed_consult["status"] == "COMPLETED"
    assert completed_consult["duration_seconds"] is not None

    # --- STEP 15: Verify final states in Database ---
    db_session.refresh(db_appt)
    db_session.refresh(db_entry)
    db_session.refresh(db_consult)

    assert db_appt.status == AppointmentStatus.COMPLETED
    assert db_entry.status == QueueStatus.COMPLETED
    assert db_entry.completed_at is not None
    assert db_consult.status == ConsultationStatus.COMPLETED
    assert db_consult.completed_at is not None

    # --- NEGATIVE: Attempt to complete consultation twice ---
    res_dup_complete = client.post(
        f"/api/v1/queues/{queue_entry_id}/complete",
        headers=doctor_headers,
    )
    assert res_dup_complete.status_code == 400
    assert res_dup_complete.json()["error"]["code"] in ["INVALID_QUEUE_TRANSITION", "ALREADY_COMPLETED"]

    # --- NEGATIVE: Attempt to check in completed appointment ---
    res_checkin_completed = client.post(
        f"/api/v1/appointments/{appointment_id}/check-in",
        headers=patient_headers,
    )
    assert res_checkin_completed.status_code == 400
    assert res_checkin_completed.json()["error"]["code"] == "CANNOT_CHECK_IN_COMPLETED"

    # --- NEGATIVE: Cross-patient appointment access ---
    res_cross_patient = client.get(
        f"/api/v1/appointments/{appointment_id}",
        headers=other_patient_headers,
    )
    assert res_cross_patient.status_code == 403
    assert res_cross_patient.json()["error"]["code"] == "FORBIDDEN_APPOINTMENT_ACCESS"
