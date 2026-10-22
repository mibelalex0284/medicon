import datetime
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.profile import UserRole
from app.models.specialty import Specialty
from app.models.triage_assessment import TriageAssessment, TriageUrgency
from app.models.triage_message import TriageMessage
from app.models.triage_session import TriageSession, TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service


@pytest.fixture
def completed_triage_session(db_session: Session):
    """Creates a deterministic completed non-emergency triage session with messages and assessment."""
    # 0. Ensure hospital exists
    from app.models.hospital import Hospital
    hosp = db_session.query(Hospital).filter(Hospital.id == "hosp-001").first()
    if not hosp:
        hosp = Hospital(id="hosp-001", name="Metro General", code="METRO_GEN")
        db_session.add(hosp)
        db_session.flush()

    # 1. Create patient owner (auth_user_id='patient-123')
    pat_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Valid Patient",
            email="valid.patient@example.com",
            hospital_id="hosp-001",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=pat_prof.id, date_of_birth=datetime.date(1991, 3, 15)),
    )

    # 2. Create another patient (auth_user_id='patient-999')
    other_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-999",
            role=UserRole.PATIENT,
            full_name="Other Patient",
            email="other.patient@example.com",
        ),
    )
    patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=other_prof.id, date_of_birth=datetime.date(1993, 7, 20)),
    )

    # 3. Create specialty
    specialty = Specialty(
        name="General Medicine",
        code="GEN_MED",
        description="Primary care and adult general medicine",
    )
    db_session.add(specialty)
    db_session.flush()

    # 4. Create completed triage session
    now = datetime.datetime.now(datetime.timezone.utc)
    session = TriageSession(
        patient_id=patient.id,
        status=TriageSessionStatus.COMPLETED,
        original_input="I have had a persistent dry cough and fatigue for three days",
        confirmed_input="Dry cough for 3 days, no fever, no eye irritation",
        started_at=now - datetime.timedelta(minutes=15),
        completed_at=now,
    )
    db_session.add(session)
    db_session.flush()

    # 5. Attach structured intake conversation messages
    # Turn 1: Patient presents symptoms
    msg_pat_1 = TriageMessage(
        session_id=session.id,
        sender="patient",
        content="I have a cough and fatigue.",
        turn_index=1,
        extracted_evidence=json.dumps([
            {"evidence_code": "E_201", "status": "PRESENT", "value": True},
        ]),
    )
    msg_asst_1 = TriageMessage(
        session_id=session.id,
        sender="assistant",
        content="Do you feel that your eyes produce excessive tears?",
        turn_index=1,
        extracted_evidence=json.dumps({
            "selected_evidence_id": "E_127",
            "information_gain": 0.42,
        }),
    )
    # Turn 2: Patient explicitly denies symptom
    msg_pat_2 = TriageMessage(
        session_id=session.id,
        sender="patient",
        content="No, my eyes are completely fine, no excessive tearing at all.",
        turn_index=2,
        extracted_evidence=json.dumps([
            {"evidence_code": "E_127", "status": "ABSENT"},
        ]),
    )
    msg_asst_2 = TriageMessage(
        session_id=session.id,
        sender="assistant",
        content="Thank you for providing this intake information.",
        turn_index=2,
    )
    db_session.add_all([msg_pat_1, msg_asst_1, msg_pat_2, msg_asst_2])

    # 6. Attach TriageAssessment
    assessment = TriageAssessment(
        triage_session_id=session.id,
        urgency=TriageUrgency.LOW,
        confidence=0.88,
        needs_escalation=False,
        red_flag_detected=False,
        red_flag_codes=[],
        recommended_specialty_id=specialty.id,
        rationale="Standard non-emergency outpatient intake. Patient routed to General Medicine with LOW urgency.",
        assessed_at=now,
    )
    db_session.add(assessment)
    db_session.commit()

    return session


def test_get_pre_consultation_report_success(
    client: TestClient,
    completed_triage_session: TriageSession,
    patient_headers: dict,
):
    """Regression Test: Valid completed non-emergency triage session retrieves its report (HTTP 200)."""
    session_id = completed_triage_session.id
    response = client.get(
        f"/api/v1/triage/sessions/{session_id}/report",
        headers=patient_headers,
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    # Core structured pre-consultation information
    assert data["session_id"] == session_id
    assert data["patient_id"] == completed_triage_session.patient_id
    assert data["urgency"] == "LOW"
    assert data["recommended_specialty_name"] == "General Medicine"
    assert "dry cough" in data["chief_complaint"].lower()

    # Present symptoms separated from explicitly denied / pertinent negatives
    assert isinstance(data["present_symptoms"], list)
    assert isinstance(data["absent_symptoms"], list)
    assert len(data["present_symptoms"]) >= 1
    assert len(data["absent_symptoms"]) >= 1

    # Verify separation
    present_text = " ".join(data["present_symptoms"]).lower()
    absent_text = " ".join(data["absent_symptoms"]).lower()
    assert "cough" in present_text
    assert "denied" in absent_text

    present_set = set(data["present_symptoms"])
    absent_set = set(data["absent_symptoms"])
    assert present_set.isdisjoint(absent_set), "Present and denied symptoms must remain separate"

    # Non-diagnostic notice must remain present
    assert "notice" in data
    assert "It is not a diagnosis" in data["notice"]
    assert "responsibility of the treating physician" in data["notice"]

    # Verify conversation summary
    assert "conversation_summary" in data
    assert len(data["conversation_summary"]) > 0

    # Ensure NO forbidden disease-prediction runtime keys or diagnostic claims are introduced
    forbidden_keys = [
        "candidate_conditions",
        "top_candidate_conditions",
        "differential_diagnosis",
        "disease_probability",
        "disease_probabilities",
        "disease_candidates",
    ]
    for key in forbidden_keys:
        assert key not in data, f"Forbidden diagnostic claim key '{key}' found in report response"


def test_get_pre_consultation_report_authorization(
    client: TestClient,
    completed_triage_session: TriageSession,
    patient_headers: dict,
    other_patient_headers: dict,
    doctor_headers: dict,
    other_hospital_doctor_headers: dict,
    admin_headers: dict,
):
    """Authorization Test:
    - Other patient cannot retrieve patient-123's report (HTTP 403)
    - Cross-hospital doctor cannot retrieve the report (HTTP 403)
    - Cross-hospital admin cannot retrieve the report (HTTP 403)
    - Same-hospital doctor can retrieve the report (HTTP 200)
    - Same-hospital admin can retrieve the report (HTTP 200)
    - Unauthenticated user cannot retrieve the report (HTTP 401)
    """
    from app.core.security import create_access_token

    session_id = completed_triage_session.id

    # 1. Intruder patient (patient-999) cannot access patient-123's report -> 403
    res_intruder = client.get(
        f"/api/v1/triage/sessions/{session_id}/report",
        headers=other_patient_headers,
    )
    assert res_intruder.status_code == 403
    assert res_intruder.json()["error"]["code"] == "FORBIDDEN_TRIAGE_ACCESS"

    # 2. Cross-hospital doctor (hospital hosp-002) accessing hosp-001 patient -> 403
    res_cross_doctor = client.get(
        f"/api/v1/triage/sessions/{session_id}/report",
        headers=other_hospital_doctor_headers,
    )
    assert res_cross_doctor.status_code == 403
    assert res_cross_doctor.json()["error"]["code"] == "FORBIDDEN_REPORT_ACCESS"

    # 3. Cross-hospital admin (hospital hosp-002) accessing hosp-001 patient -> 403
    cross_admin_token = create_access_token(
        subject="admin-other",
        role="admin",
        hospital_id="hosp-002",
    )
    res_cross_admin = client.get(
        f"/api/v1/triage/sessions/{session_id}/report",
        headers={"Authorization": f"Bearer {cross_admin_token}"},
    )
    assert res_cross_admin.status_code == 403
    assert res_cross_admin.json()["error"]["code"] == "FORBIDDEN_REPORT_ACCESS"

    # 4. Same-hospital doctor (hospital hosp-001) -> 200
    res_doctor = client.get(
        f"/api/v1/triage/sessions/{session_id}/report",
        headers=doctor_headers,
    )
    assert res_doctor.status_code == 200
    assert res_doctor.json()["session_id"] == session_id

    # 5. Same-hospital admin (hospital hosp-001) -> 200
    res_admin = client.get(
        f"/api/v1/triage/sessions/{session_id}/report",
        headers=admin_headers,
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["session_id"] == session_id

    # 6. Unauthenticated caller -> 401
    res_unauth = client.get(f"/api/v1/triage/sessions/{session_id}/report")
    assert res_unauth.status_code == 401


def test_get_pre_consultation_report_not_found(
    client: TestClient,
    patient_headers: dict,
):
    """404 Test: Non-existent session returns 404."""
    res_404 = client.get(
        "/api/v1/triage/sessions/00000000-0000-0000-0000-000000000000/report",
        headers=patient_headers,
    )
    assert res_404.status_code == 404
