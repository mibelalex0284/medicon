import datetime
from app.models.specialty import Specialty
from app.models.triage_assessment import TriageAssessment, TriageUrgency
from app.models.triage_session import TriageSession, TriageSessionStatus
from app.schemas.triage import TriageAssessmentResponse, TriageSessionResponse


def test_triage_assessment_guidance_red_flag():
    assessment = TriageAssessment(
        id="ass-red-flag",
        triage_session_id="session-1",
        urgency=TriageUrgency.HIGH,
        confidence=1.0,
        needs_escalation=True,
        red_flag_detected=True,
        red_flag_codes=["RED_FLAG_BREATHING_DIFFICULTY"],
        rationale="Emergency presentation",
        assessed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    assert assessment.red_flag_detected is True
    assert "Emergency warning signs were detected" in assessment.guidance

    # Verify Pydantic serialization
    resp = TriageAssessmentResponse.model_validate(assessment)
    assert resp.guidance == assessment.guidance
    assert resp.red_flag_detected is True
    assert resp.urgency == TriageUrgency.HIGH


def test_triage_assessment_guidance_escalated_uncertain():
    assessment = TriageAssessment(
        id="ass-escalated",
        triage_session_id="session-2",
        urgency=TriageUrgency.MODERATE,
        confidence=0.50,
        needs_escalation=True,
        red_flag_detected=False,
        rationale="Uncertain clinical factors",
        assessed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    assert "uncertain" in assessment.guidance.lower()
    assert "in-person" in assessment.guidance.lower()

    resp = TriageAssessmentResponse.model_validate(assessment)
    assert resp.guidance == assessment.guidance
    assert resp.confidence == 0.50


def test_triage_assessment_guidance_routine():
    specialty = Specialty(id="spec-pulmo", name="Pulmonology", code="PULMO")
    assessment = TriageAssessment(
        id="ass-routine",
        triage_session_id="session-3",
        urgency=TriageUrgency.LOW,
        confidence=0.90,
        needs_escalation=False,
        red_flag_detected=False,
        rationale="Routine outpatient presentation",
        assessed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    assessment.recommended_specialty = specialty
    assert "routine" in assessment.guidance.lower()
    assert assessment.recommended_specialty_name == "Pulmonology"

    resp = TriageAssessmentResponse.model_validate(assessment)
    assert resp.guidance == assessment.guidance
    assert resp.recommended_specialty_name == "Pulmonology"


def test_triage_session_response_serialization_with_assessment():
    session = TriageSession(
        id="sess-full",
        patient_id="pat-1",
        status=TriageSessionStatus.COMPLETED,
        original_input="Cough and fever",
        language="en",
        started_at=datetime.datetime.now(datetime.timezone.utc),
        completed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    assessment = TriageAssessment(
        id="ass-full",
        triage_session_id="sess-full",
        urgency=TriageUrgency.LOW,
        confidence=0.85,
        needs_escalation=False,
        red_flag_detected=False,
        rationale="Routine viral illness",
        assessed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    session.assessment = assessment

    # Serialize via TriageSessionResponse
    session_resp = TriageSessionResponse.model_validate(session)
    assert session_resp.id == "sess-full"
    assert session_resp.status == TriageSessionStatus.COMPLETED
    assert session_resp.assessment is not None
    assert len(session_resp.assessment.guidance) > 0
    assert "routine" in session_resp.assessment.guidance.lower()
