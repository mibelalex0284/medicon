import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.profile import UserRole
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service


def test_triage_api_end_to_end_flow(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
):
    # Setup patient (tied to patient_headers auth: patient-123)
    pat_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Alice Triage",
            email="alice.triage@example.com",
        ),
    )
    patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=pat_prof.id, date_of_birth=datetime.date(1992, 5, 1)),
    )

    # 1. Start triage session
    res_create = client.post(
        "/api/v1/triage/sessions",
        json={"original_input": "Persistent cough and mild low fever for four days"},
        headers=patient_headers,
    )
    assert res_create.status_code == 201
    session_data = res_create.json()
    session_id = session_data["id"]
    assert session_data["status"] == "IN_PROGRESS"

    # 2. Confirm input
    res_confirm = client.post(
        f"/api/v1/triage/sessions/{session_id}/confirm",
        json={"confirmed_input": "Dry cough for 4 days with mild fever, no chest pain"},
        headers=patient_headers,
    )
    assert res_confirm.status_code == 200
    assert "Dry cough" in res_confirm.json()["confirmed_input"]

    # 3. Get next question
    res_q = client.get(
        f"/api/v1/triage/sessions/{session_id}/next-question",
        headers=patient_headers,
    )
    assert res_q.status_code == 200
    q_data = res_q.json()
    assert q_data is not None
    question_id = q_data["id"]

    # 4. Answer question
    res_ans = client.post(
        f"/api/v1/triage/sessions/{session_id}/answers",
        json={"question_id": question_id, "answer_value": "NO"},
        headers=patient_headers,
    )
    assert res_ans.status_code == 201
    assert res_ans.json()["answer_value"] == "NO"

    # 5. Assess session
    res_assess = client.post(
        f"/api/v1/triage/sessions/{session_id}/assess",
        headers=patient_headers,
    )
    assert res_assess.status_code == 200
    assessment = res_assess.json()
    assert assessment["red_flag_detected"] is False
    assert assessment["urgency"] in ["LOW", "MODERATE"]
    assert assessment["confidence"] >= 0.60
    assert "guidance" in assessment
    assert assessment["recommended_specialty_name"] is not None

    # 6. Fetch completed session details (regression test for assessment serialization & guidance)
    res_get = client.get(
        f"/api/v1/triage/sessions/{session_id}",
        headers=patient_headers,
    )
    assert res_get.status_code == 200
    session_details = res_get.json()
    assert session_details["assessment"] is not None
    assert "guidance" in session_details["assessment"]
    assert len(session_details["assessment"]["guidance"]) > 0
    assert session_details["assessment"]["recommended_specialty_name"] is not None


def test_triage_api_emergency_red_flag(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
):
    pat_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Alice Triage",
            email="alice.triage2@example.com",
        ),
    )
    patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=pat_prof.id, date_of_birth=datetime.date(1992, 5, 1)),
    )

    # Patient presents with severe chest pain
    res_create = client.post(
        "/api/v1/triage/sessions",
        json={"original_input": "I am having severe crushing chest pain radiating to my left jaw and shortness of breath"},
        headers=patient_headers,
    )
    assert res_create.status_code == 201
    session_id = res_create.json()["id"]

    # Assess immediately
    res_assess = client.post(
        f"/api/v1/triage/sessions/{session_id}/assess",
        headers=patient_headers,
    )
    assert res_assess.status_code == 200
    ass = res_assess.json()
    assert ass["red_flag_detected"] is True
    assert ass["urgency"] == "HIGH"
    assert ass["needs_escalation"] is True
    assert "RED_FLAG_CHEST_PAIN_SEVERE" in ass["red_flag_codes"]
    assert "Emergency warning signs were detected" in ass["guidance"]

    # Verify completed emergency session details GET serialization
    res_get_emerg = client.get(
        f"/api/v1/triage/sessions/{session_id}",
        headers=patient_headers,
    )
    assert res_get_emerg.status_code == 200
    emerg_details = res_get_emerg.json()
    assert emerg_details["assessment"] is not None
    assert emerg_details["assessment"]["red_flag_detected"] is True
    assert "Emergency warning signs were detected" in emerg_details["assessment"]["guidance"]


def test_cross_patient_triage_access_forbidden(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    other_patient_headers: dict,
):
    # Patient 1 (patient-123)
    p1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Patient One",
            email="p1@triage.org",
        ),
    )
    patient_service.create_patient(
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
            email="p2@triage.org",
        ),
    )
    patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p2_prof.id, date_of_birth=datetime.date(1995, 1, 1)),
    )

    # Patient 1 creates a triage session
    res_p1 = client.post(
        "/api/v1/triage/sessions",
        json={"original_input": "Headache and fever"},
        headers=patient_headers,
    )
    s_id = res_p1.json()["id"]

    # Patient 2 attempts to view Patient 1's triage session -> 403 Forbidden
    res_intruder = client.get(
        f"/api/v1/triage/sessions/{s_id}",
        headers=other_patient_headers,
    )
    assert res_intruder.status_code == 403
    assert res_intruder.json()["error"]["code"] == "FORBIDDEN_TRIAGE_ACCESS"
