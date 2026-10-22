import datetime
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import InvalidStateTransitionError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.schemas.triage import TriageSessionCreate
from app.services.llm.gemini import GeminiProvider
from app.services.llm.provider import EvidenceStatus
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.services.triage.evidence_provider import ddxplus_provider
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage_service import triage_service

import os

# Condition to determine if live Gemini API tests should run
run_live = os.getenv("RUN_LIVE_GEMINI_TESTS", "").strip().lower() in ("true", "1")
is_gemini_configured = bool(
    run_live
    and settings.GEMINI_API_KEY
    and settings.GEMINI_API_KEY != "your-gemini-api-key-here"
    and len(settings.GEMINI_API_KEY) > 10
)

skip_reason = "Live Gemini tests disabled by default (set RUN_LIVE_GEMINI_TESTS=true with valid GEMINI_API_KEY to run live tests)."


@pytest.fixture
def gemini_provider():
    if not is_gemini_configured:
        pytest.skip(skip_reason)
    return GeminiProvider()


from app.core.exceptions import InvalidStateTransitionError, TriageLLMUnavailableError

@pytest.fixture(autouse=True)
def rate_limit_pacer():
    try:
        yield
    except TriageLLMUnavailableError as exc:
        pytest.skip(f"Live Gemini quota limit reached (429 / fail-fast): {exc}")


@pytest.fixture
def live_triage_patient(db_session: Session):
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-live-usr-1",
            role=UserRole.PATIENT,
            full_name="Live Gemini Patient",
            email="live.gemini@test.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=prof.id, date_of_birth=datetime.date(1992, 4, 10)),
    )
    for name, code in [
        ("General Medicine", "GEN-MED"),
        ("Cardiology", "CARDIO"),
        ("Neurology", "NEURO"),
        ("Emergency", "EMERG"),
    ]:
        try:
            specialty_service.create_specialty(
                db_session, SpecialtyCreate(name=name, code=code)
            )
        except Exception:
            pass
    return patient


# ==============================================================================
# SECTION 18: CONTROLLED LIVE TEST MATRIX (CASES A - I)
# ==============================================================================

@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_a_basic_symptom(gemini_provider):
    """Case A: 'I have a headache.' -> valid structured response, headache E_127, no invented evidence."""
    res = gemini_provider.extract_patient_evidence("I have a headache.")
    assert res is not None
    ev_dict = {item.evidence_code: item.status for item in res.items}
    assert "E_127" in ev_dict
    assert ev_dict["E_127"] == EvidenceStatus.PRESENT
    # Must only contain valid DDXPlus evidence codes
    for code in ev_dict.keys():
        assert ddxplus_provider.get_evidence(code) is not None


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_b_multiple_symptoms(gemini_provider):
    """Case B: 'I have a headache and feel exhausted.' -> headache PRESENT, fatigue/exhaustion PRESENT."""
    res = gemini_provider.extract_patient_evidence("I have a headache and feel exhausted.")
    ev_dict = {item.evidence_code: item.status for item in res.items}
    assert "E_127" in ev_dict
    assert ev_dict["E_127"] == EvidenceStatus.PRESENT
    assert ("E_24" in ev_dict or "E_148" in ev_dict)
    fatigue_code = "E_24" if "E_24" in ev_dict else "E_148"
    assert ev_dict[fatigue_code] == EvidenceStatus.PRESENT


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_c_explicit_negation(gemini_provider):
    """Case C: 'I don't have a fever.' -> fever E_91 ABSENT."""
    res = gemini_provider.extract_patient_evidence("I don't have a fever.")
    ev_dict = {item.evidence_code: item.status for item in res.items}
    assert "E_91" in ev_dict
    assert ev_dict["E_91"] == EvidenceStatus.ABSENT


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_d_uncertainty(gemini_provider):
    """Case D: 'I'm not sure if I have a fever.' -> fever E_91 UNKNOWN."""
    res = gemini_provider.extract_patient_evidence("I'm not sure if I have a fever.")
    ev_dict = {item.evidence_code: item.status for item in res.items}
    assert "E_91" in ev_dict
    assert ev_dict["E_91"] == EvidenceStatus.UNKNOWN


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_e_duration(gemini_provider):
    """Case E: 'My headache started three days ago.' -> duration approximately 3 days."""
    res = gemini_provider.extract_patient_evidence("My headache started three days ago.")
    assert res.duration is not None
    assert any(w in res.duration.lower() for w in ["3", "three", "day"])


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_f_severity(gemini_provider):
    """Case F: 'The pain is around 7 out of 10.' -> severity = 7."""
    res = gemini_provider.extract_patient_evidence("The pain is around 7 out of 10.")
    assert res.severity == 7


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_g_natural_phrasing(gemini_provider):
    """Case G: Controlled question phrasing -> natural question, evidence ID preserved, no diagnosis."""
    controlled_q = "Do you have a fever (either felt or measured with a thermometer)?"
    evidence_id = "E_91"
    phrased = gemini_provider.phrase_question(controlled_q, evidence_id)
    assert isinstance(phrased, str)
    assert len(phrased) >= 10
    assert phrased.endswith("?")
    # Must not contain diagnoses or prescriptions
    lower = phrased.lower()
    assert "you have" not in lower
    assert "diagnos" not in lower
    assert "prescrib" not in lower


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_h_unknown_symptom(gemini_provider):
    """Case H: Unknown symptom outside DDXPlus -> no invented evidence ID, filtered safely."""
    res = gemini_provider.extract_patient_evidence("My fingernails turned neon purple with sparkles.")
    # Gemini must not invent an arbitrary evidence code
    for item in res.items:
        assert ddxplus_provider.get_evidence(item.evidence_code) is not None


@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_case_i_emergency_deterministic_safety_wins(db_session: Session, live_triage_patient, gemini_provider):
    """Case I: 'Sudden severe crushing chest pain and I can't breathe.' -> Deterministic safety engine wins."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Chest problem"),
        actor_auth_user_id="pat-live-usr-1",
    )
    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=gemini_provider,
    )
    result = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="Sudden severe crushing chest pain and I can't breathe.",
        actor_auth_user_id="pat-live-usr-1",
    )
    assert result.is_complete is True
    assert result.stop_reason == "EMERGENCY_RED_FLAG"
    assert result.assessment is not None
    assert result.assessment.urgency == TriageUrgency.HIGH
    assert result.assessment.red_flag_detected is True
    assert result.selected_question is None
    assert "emergency" in result.assistant_message.lower()


# ==============================================================================
# SECTION 20: END-TO-END ORCHESTRATOR TEST WITH REAL GEMINI
# ==============================================================================

@pytest.mark.skipif(not is_gemini_configured, reason=skip_reason)
def test_live_end_to_end_orchestrator_turn(db_session: Session, live_triage_patient, gemini_provider):
    """Verifies complete end-to-end flow with real Gemini:
    Patient text -> Gemini extraction -> PatientState -> Deterministic Safety ->
    DDXPlus -> Mutual Information Selector -> Gemini question phrasing
    """
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Feeling sick"),
        actor_auth_user_id="pat-live-usr-1",
    )
    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=gemini_provider,
    )

    turn1 = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I've had a headache for three days and I'm exhausted.",
        actor_auth_user_id="pat-live-usr-1",
    )

    # 1. Verification of state and extraction
    assert turn1.conversation_turn == 1
    assert turn1.is_complete is False
    assert len(turn1.extracted_evidences) > 0
    extracted_codes = [e["evidence_code"] for e in turn1.extracted_evidences]
    assert "E_127" in extracted_codes

    # 2. Verification of adaptive question selection by backend QuestionSelector
    assert turn1.selected_question is not None
    assert turn1.selected_question.evidence_id is not None
    assert turn1.selected_question.evidence_id != "E_127"  # Cannot ask what is already known

    # 3. Verification of Gemini question phrasing
    assert turn1.assistant_message is not None
    assert len(turn1.assistant_message) > 10
    assert turn1.assistant_message.endswith("?")
