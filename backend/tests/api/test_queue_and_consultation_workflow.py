import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.models.appointment import Appointment, AppointmentStatus
from app.models.profile import UserRole
from app.models.queue_entry import QueueEntry, QueueStatus
from app.schemas.doctor import DoctorCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.queue_service import queue_service


def test_queue_and_consultation_lifecycle_and_security(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    doctor_headers: dict,
    admin_headers: dict,
):
    today = datetime.datetime.now(datetime.timezone.utc).date()

    # 1. Setup Hospital
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="City Central Hospital", code="CCH-01")
    )

    # 2. Setup Primary Doctor (doctor-456)
    doc1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Marcus Welby",
            email="welby@citycentral.org",
            hospital_id=hosp.id,
        ),
    )
    doc1 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc1_prof.id,
            hospital_id=hosp.id,
            license_number="LIC-WELBY-777",
        ),
    )

    # 3. Setup Secondary Doctor (doctor-999)
    doc2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-999",
            role=UserRole.DOCTOR,
            full_name="Dr. Stephen Strange",
            email="strange@citycentral.org",
            hospital_id=hosp.id,
        ),
    )
    doc2 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc2_prof.id,
            hospital_id=hosp.id,
            license_number="LIC-STRANGE-888",
        ),
    )
    token_doc2 = create_access_token(
        subject="doctor-999", role="doctor", hospital_id=hosp.id
    )
    doc2_headers = {"Authorization": f"Bearer {token_doc2}"}

    # 4. Setup Patient 1 (patient-123)
    pat1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Arthur Dent",
            email="dent@galaxy.org",
        ),
    )
    pat1 = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=pat1_prof.id,
            date_of_birth=datetime.date(1980, 4, 1),
        ),
    )

    # 5. Setup Patient 2 (patient-789)
    pat2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-789",
            role=UserRole.PATIENT,
            full_name="Ford Prefect",
            email="ford@galaxy.org",
        ),
    )
    pat2 = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=pat2_prof.id,
            date_of_birth=datetime.date(1982, 5, 2),
        ),
    )

    # 6. Setup Admin Profile (admin-789)
    profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="admin-789",
            role=UserRole.ADMIN,
            full_name="Admin Ops",
            email="admin789@citycentral.org",
            hospital_id=hosp.id,
        ),
    )

    # Test Case 3: Patient with no queue entry receives 404 NO_ACTIVE_QUEUE_ENTRY
    res_no_queue = client.get("/api/v1/patients/me/queue", headers=patient_headers)
    assert res_no_queue.status_code == 404
    data_no_queue = res_no_queue.json()
    assert data_no_queue.get("error", {}).get("code") == "NO_ACTIVE_QUEUE_ENTRY" or "not found" in res_no_queue.text.lower()

    # Create Appointment and Check-In Patient 1
    appt1 = Appointment(
        patient_id=pat1.id,
        doctor_id=doc1.id,
        hospital_id=hosp.id,
        appointment_date=today,
        scheduled_start=datetime.time(9, 0),
        scheduled_end=datetime.time(9, 30),
        status=AppointmentStatus.BOOKED,
        reason="Persistent morning cough",
    )
    db_session.add(appt1)
    db_session.commit()
    db_session.refresh(appt1)

    # Check In Patient 1
    q_entry1 = queue_service.check_in(
        db_session, appt1.id, actor_auth_user_id="patient-123"
    )
    assert q_entry1.token_number == "A01"
    assert q_entry1.status == QueueStatus.WAITING

    # Test Case 1: Authenticated Patient 1 retrieves their own queue
    res_patient_queue = client.get("/api/v1/patients/me/queue", headers=patient_headers)
    assert res_patient_queue.status_code == 200
    pat_q_data = res_patient_queue.json()
    assert pat_q_data["token_number"] == "A01"
    assert pat_q_data["status"] == "WAITING"
    assert pat_q_data["patients_ahead"] == 0
    assert "wait_estimate" in pat_q_data

    # Test Case 2: Patient cannot retrieve another patient's queue
    # The endpoint /api/v1/patients/me/queue derives identity strictly from JWT
    token_pat2 = create_access_token(
        subject="patient-789", role="patient"
    )
    pat2_headers = {"Authorization": f"Bearer {token_pat2}"}
    res_pat2_queue = client.get("/api/v1/patients/me/queue", headers=pat2_headers)
    # Patient 2 has no active entry -> 404, cannot see Patient 1's queue
    assert res_pat2_queue.status_code == 404

    # Test Case 4: Doctor 1 retrieves their authorized queue (both /me and explicit ID)
    res_doc_queue_me = client.get("/api/v1/queues/me/current", headers=doctor_headers)
    assert res_doc_queue_me.status_code == 200
    doc_q_data = res_doc_queue_me.json()
    assert len(doc_q_data) == 1
    assert doc_q_data[0]["token_number"] == "A01"
    assert doc_q_data[0]["patient_name"] == "Arthur Dent"

    res_doc_queue_id = client.get(f"/api/v1/queues/{doc1.id}/current", headers=doctor_headers)
    assert res_doc_queue_id.status_code == 200

    # Test Case 5: Doctor 2 CANNOT access Doctor 1's queue
    res_cross_doc = client.get(f"/api/v1/queues/{doc1.id}/current", headers=doc2_headers)
    assert res_cross_doc.status_code == 403
    assert "forbidden" in res_cross_doc.text.lower()

    # Test Case 5b: Patient CANNOT access doctor queue (/api/v1/queues/me/current)
    res_pat_doc_queue = client.get("/api/v1/queues/me/current", headers=patient_headers)
    assert res_pat_doc_queue.status_code == 403
    assert "forbidden" in res_pat_doc_queue.text.lower() or "doctor" in res_pat_doc_queue.text.lower()

    # Test Case 5c: Doctor CANNOT access patient queue (/api/v1/patients/me/queue)
    res_doc_pat_queue = client.get("/api/v1/patients/me/queue", headers=doctor_headers)
    assert res_doc_pat_queue.status_code == 403

    # Test Case 5d: Administrator calling /api/v1/queues/me/current receives 200 with empty list (no 403)
    res_admin_doc_queue = client.get("/api/v1/queues/me/current", headers=admin_headers)
    assert res_admin_doc_queue.status_code == 200
    assert res_admin_doc_queue.json() == []

    # Test Case 6: Unauthorized requests rejected
    res_unauth = client.get(f"/api/v1/queues/{doc1.id}/current")
    assert res_unauth.status_code == 401

    # Test Case 7: Call next patient transitions to CALLED
    res_call = client.post(f"/api/v1/queues/{q_entry1.id}/call", headers=doctor_headers)
    assert res_call.status_code == 200
    call_data = res_call.json()
    assert call_data["status"] == "CALLED"
    assert call_data["called_at"] is not None

    # Patient queue reflects CALLED status
    res_patient_called = client.get("/api/v1/patients/me/queue", headers=patient_headers)
    assert res_patient_called.status_code == 200
    assert res_patient_called.json()["status"] == "CALLED"

    # Test Case 8: Start consultation transitions to IN_CONSULTATION and activates Consultation
    res_start = client.post(f"/api/v1/queues/{q_entry1.id}/start", headers=doctor_headers)
    assert res_start.status_code == 200
    start_data = res_start.json()
    assert start_data["status"] == "IN_PROGRESS"
    assert start_data["queue_entry_id"] == q_entry1.id

    # Active consultation endpoint
    res_active_consult = client.get("/api/v1/queues/active-consultation", headers=doctor_headers)
    assert res_active_consult.status_code == 200
    active_data = res_active_consult.json()
    assert active_data["id"] == start_data["id"]
    assert active_data["status"] == "IN_PROGRESS"

    # Test Case 9: Complete consultation transitions to COMPLETED
    res_complete = client.post(f"/api/v1/queues/{q_entry1.id}/complete", headers=doctor_headers)
    assert res_complete.status_code == 200
    complete_data = res_complete.json()
    assert complete_data["status"] == "COMPLETED"
    assert complete_data["completed_at"] is not None

    # Test Case 10 & 11: Invalid transition and duplicate complete
    res_dup_complete = client.post(f"/api/v1/queues/{q_entry1.id}/complete", headers=doctor_headers)
    assert res_dup_complete.status_code == 400

    # Cannot call a completed entry
    res_call_completed = client.post(f"/api/v1/queues/{q_entry1.id}/call", headers=doctor_headers)
    assert res_call_completed.status_code == 400

    # Test Case 12: Doctor Me profile
    res_doc_me = client.get("/api/v1/doctors/me", headers=doctor_headers)
    assert res_doc_me.status_code == 200
    doc_me_data = res_doc_me.json()
    assert doc_me_data["id"] == doc1.id
    assert doc_me_data["profile"]["full_name"] == "Dr. Marcus Welby"

    # Test Case 13: Multiple queue entries and ordering
    appt2 = Appointment(
        patient_id=pat2.id,
        doctor_id=doc1.id,
        hospital_id=hosp.id,
        appointment_date=today,
        scheduled_start=datetime.time(10, 0),
        scheduled_end=datetime.time(10, 30),
        status=AppointmentStatus.BOOKED,
        reason="Follow-up consultation",
    )
    db_session.add(appt2)
    db_session.commit()
    db_session.refresh(appt2)

    q_entry2 = queue_service.check_in(
        db_session, appt2.id, actor_auth_user_id="patient-789"
    )
    assert q_entry2.token_number == "A02"
    assert q_entry2.status == QueueStatus.WAITING

    # Test Case 14: Mark as NO_SHOW
    res_no_show = client.post(f"/api/v1/queues/{q_entry2.id}/no-show", headers=doctor_headers)
    assert res_no_show.status_code == 200
    assert res_no_show.json()["status"] == "NO_SHOW"

    # Cannot call a NO_SHOW entry
    res_call_noshow = client.post(f"/api/v1/queues/{q_entry2.id}/call", headers=doctor_headers)
    assert res_call_noshow.status_code == 400

    # Test Case 15: Doctor 1 can check in their assigned patient
    appt3 = Appointment(
        patient_id=pat1.id,
        doctor_id=doc1.id,
        hospital_id=hosp.id,
        appointment_date=today,
        scheduled_start=datetime.time(11, 0),
        scheduled_end=datetime.time(11, 30),
        status=AppointmentStatus.BOOKED,
        reason="Prescription renewal",
    )
    db_session.add(appt3)
    db_session.commit()
    db_session.refresh(appt3)

    # Doctor 2 CANNOT check in Doctor 1's appointment
    res_doc2_checkin = client.post(f"/api/v1/appointments/{appt3.id}/check-in", headers=doc2_headers)
    assert res_doc2_checkin.status_code == 403
    assert "another doctor" in res_doc2_checkin.text.lower() or "not_assigned_doctor" in res_doc2_checkin.text.lower()

    # Doctor 1 CAN check in their patient
    res_doc1_checkin = client.post(f"/api/v1/appointments/{appt3.id}/check-in", headers=doctor_headers)
    assert res_doc1_checkin.status_code == 201
    q_entry3_data = res_doc1_checkin.json()
    assert q_entry3_data["status"] == "WAITING"
    assert q_entry3_data["token_number"] == "A03"

    # Verify Appointment lists include patient_name
    res_appts = client.get("/api/v1/appointments", headers=doctor_headers)
    assert res_appts.status_code == 200
    appts_data = res_appts.json()
    assert any(a["patient_name"] == "Arthur Dent" for a in appts_data)

    # Call and start consultation for entry 3
    client.post(f"/api/v1/queues/{q_entry3_data['id']}/call", headers=doctor_headers)
    res_start3 = client.post(f"/api/v1/queues/{q_entry3_data['id']}/start", headers=doctor_headers)
    assert res_start3.status_code == 200
    consult3_id = res_start3.json()["id"]

    # Test Case 16: Resuming in-progress consultation is idempotent
    res_resume = client.post(f"/api/v1/queues/{q_entry3_data['id']}/start", headers=doctor_headers)
    assert res_resume.status_code == 200
    assert res_resume.json()["id"] == consult3_id

    # Test Case 17: Save clinical notes, diagnosis, prescriptions to backend
    notes_payload = {
        "clinical_notes": "Patient reports mild fatigue. Vitals normal. BP 120/80.",
        "diagnosis": "Mild viral rhinitis",
        "prescriptions": "Rest, hydration, cetirizine 10mg PRN",
        "follow_up_instructions": "Return in 7 days if symptoms persist",
    }
    res_save_notes = client.put(
        f"/api/v1/queues/consultation/{consult3_id}/notes",
        headers=doctor_headers,
        json=notes_payload,
    )
    assert res_save_notes.status_code == 200
    saved_data = res_save_notes.json()
    assert saved_data["clinical_notes"] == notes_payload["clinical_notes"]
    assert saved_data["diagnosis"] == notes_payload["diagnosis"]
    assert saved_data["prescriptions"] == notes_payload["prescriptions"]
    assert saved_data["follow_up_instructions"] == notes_payload["follow_up_instructions"]

    # Test Case 18: Doctor 2 cannot update Doctor 1's consultation notes
    res_doc2_notes = client.put(
        f"/api/v1/queues/consultation/{consult3_id}/notes",
        headers=doc2_headers,
        json={"clinical_notes": "Tampered note"},
    )
    assert res_doc2_notes.status_code == 403

    # Test Case 19: Complete consultation with updated final notes
    complete_payload = {
        "clinical_notes": "Patient reports mild fatigue. Vitals normal. BP 120/80. Final review complete.",
        "diagnosis": "Mild viral rhinitis (resolved)",
    }
    res_complete3 = client.post(
        f"/api/v1/queues/{q_entry3_data['id']}/complete",
        headers=doctor_headers,
        json=complete_payload,
    )
    assert res_complete3.status_code == 200
    assert res_complete3.json()["status"] == "COMPLETED"
    assert res_complete3.json()["clinical_notes"] == complete_payload["clinical_notes"]
    assert res_complete3.json()["diagnosis"] == complete_payload["diagnosis"]

    # Consultation notes cannot be updated after completion
    res_post_complete_update = client.put(
        f"/api/v1/queues/consultation/{consult3_id}/notes",
        headers=doctor_headers,
        json={"clinical_notes": "Late edit"},
    )
    assert res_post_complete_update.status_code == 400

