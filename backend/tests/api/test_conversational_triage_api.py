import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.profile import UserRole
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service


def test_conversational_triage_turn_api(
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
            full_name="Eva Conversational",
            email="eva.conv@example.com",
        ),
    )
    patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=pat_prof.id, date_of_birth=datetime.date(1990, 8, 12)),
    )

    # 1. Start triage session
    res_create = client.post(
        "/api/v1/triage/sessions",
        json={"original_input": "I have had a mild headache and fatigue."},
        headers=patient_headers,
    )
    assert res_create.status_code == 201
    session_id = res_create.json()["id"]

    # 2. Send first message to conversational triage endpoint
    res_msg1 = client.post(
        f"/api/v1/triage/sessions/{session_id}/messages",
        json={"content": "I have had a headache for 2 days, but no fever and no nausea."},
        headers=patient_headers,
    )
    assert res_msg1.status_code == 200
    turn1 = res_msg1.json()
    assert turn1["session_id"] == session_id
    assert turn1["conversation_turn"] == 1
    assert turn1["is_complete"] is False
    assert turn1["selected_question"] is not None
    assert len(turn1["assistant_message"]) > 0
    assert turn1["uncertainty_score"] > 0

    # 3. Fetch conversation messages
    res_hist = client.get(
        f"/api/v1/triage/sessions/{session_id}/messages",
        headers=patient_headers,
    )
    assert res_hist.status_code == 200
    messages = res_hist.json()
    assert len(messages) == 2
    assert messages[0]["sender"] == "patient"
    assert messages[1]["sender"] == "assistant"


def test_conversational_triage_emergency_red_flag_api(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
):
    # Setup patient
    pat_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Frank Emergency",
            email="frank.emerg@example.com",
        ),
    )
    patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=pat_prof.id, date_of_birth=datetime.date(1985, 4, 10)),
    )

    # 1. Start session
    res_create = client.post(
        "/api/v1/triage/sessions",
        json={"original_input": "Sudden illness"},
        headers=patient_headers,
    )
    session_id = res_create.json()["id"]

    # 2. Patient reports emergency red flag
    res_emerg = client.post(
        f"/api/v1/triage/sessions/{session_id}/messages",
        json={"content": "I am experiencing sudden crushing chest pain and shortness of breath!"},
        headers=patient_headers,
    )
    assert res_emerg.status_code == 200
    turn = res_emerg.json()
    assert turn["is_complete"] is True
    assert turn["stop_reason"] == "EMERGENCY_RED_FLAG"
    assert "RED_FLAG_CHEST_PAIN_SEVERE" in turn["safety_flags"]
    assert turn["assessment"] is not None
    assert turn["assessment"]["urgency"] == "HIGH"
    assert turn["assessment"]["red_flag_detected"] is True
    assert "emergency" in turn["assistant_message"].lower()

    # 3. Further message on escalated session should fail with 400
    res_blocked = client.post(
        f"/api/v1/triage/sessions/{session_id}/messages",
        json={"content": "Should I still take aspirin?"},
        headers=patient_headers,
    )
    assert res_blocked.status_code == 400
    assert "SESSION_NOT_IN_PROGRESS" in res_blocked.json()["error"]["code"]

    # 4. Fetch emergency session details (regression test for conversational triage completion)
    res_get = client.get(
        f"/api/v1/triage/sessions/{session_id}",
        headers=patient_headers,
    )
    assert res_get.status_code == 200
    s_data = res_get.json()
    assert s_data["status"] == "ESCALATED"
    assert s_data["assessment"] is not None
    assert s_data["assessment"]["red_flag_detected"] is True
    assert "Emergency warning signs were detected" in s_data["assessment"]["guidance"]
