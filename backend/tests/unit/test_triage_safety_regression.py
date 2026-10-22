import datetime
import json
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import TriageLLMUnavailableError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.schemas.triage import TriageSessionCreate
from app.services.llm.gemini import (
    GeminiProvider,
    FAILURE_CATEGORY_QUOTA_EXCEEDED,
    FAILURE_CATEGORY_AUTHENTICATION_ERROR,
    FAILURE_CATEGORY_NETWORK_ERROR,
    classify_gemini_error,
    log_gemini_failure,
)
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)
from app.schemas.patient_state import PatientState
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.services.triage.evidence_provider import ddxplus_provider
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage_service import TriageService, triage_service


class StubLLM(LLMProvider):
    """Deterministic test stub at LLMProvider interface for safety regression tests."""

    def __init__(self, extracted_items=None, exc_on_extract=None):
        self.extracted_items = extracted_items or []
        self.exc_on_extract = exc_on_extract
        self.last_context = None

    def extract_patient_evidence(self, message: str, context=None) -> ExtractedEvidenceResult:
        self.last_context = context
        if self.exc_on_extract:
            raise self.exc_on_extract
        return ExtractedEvidenceResult(
            chief_complaint=message[:100],
            items=self.extracted_items,
        )

    def phrase_question(self, controlled_question: str, evidence_id: str, context=None) -> str:
        return f"Could you tell us: {controlled_question}"

    def summarize_conversation(self, messages) -> str:
        return "Summary"


@pytest.fixture
def safety_test_patient(db_session: Session):
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-safety-usr-2",
            role=UserRole.PATIENT,
            full_name="Safety Regression Patient",
            email="safety.reg@test.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=prof.id, date_of_birth=datetime.date(1992, 4, 15)),
    )
    for name, code in [
        ("General Medicine", "GEN"),
        ("Emergency Medicine", "EMERG"),
        ("Cardiology", "CARDIO"),
        ("Pulmonology", "PULM"),
    ]:
        try:
            specialty_service.create_specialty(
                db_session, SpecialtyCreate(name=name, code=code)
            )
        except Exception:
            pass
    return patient


# ==============================================================================
# 8.A: BREATHING DIFFICULTY RED FLAG (E_66)
# ==============================================================================

def test_regression_breathing_difficulty_e66_escalation(db_session: Session, safety_test_patient):
    """Active question E_66 -> Patient answers 'yes' -> E_66 PRESENT -> RED_FLAG_BREATHING_DIFFICULTY -> HIGH urgency, halt."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Trouble breathing"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    stub_llm = StubLLM(
        extracted_items=[
            ExtractedEvidenceItem(evidence_code="E_66", status=EvidenceStatus.PRESENT)
        ]
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=stub_llm,
    )

    result = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="yes",
        actor_auth_user_id="pat-safety-usr-2",
    )

    # 1. Immediate emergency stop
    assert result.is_complete is True
    assert result.stop_reason == "EMERGENCY_RED_FLAG"
    assert "RED_FLAG_BREATHING_DIFFICULTY" in result.safety_flags

    # 2. Urgency HIGH and red_flag_detected
    assert result.assessment is not None
    assert result.assessment.urgency == TriageUrgency.HIGH
    assert result.assessment.red_flag_detected is True
    assert result.assessment.needs_escalation is True

    # 3. No further questioning
    assert result.selected_question is None

    # 4. DB state verified
    db_session.refresh(session)
    assert session.status == TriageSessionStatus.ESCALATED


# ==============================================================================
# 8.B: LOSS OF CONSCIOUSNESS RED FLAG (E_159)
# ==============================================================================

def test_regression_loss_of_consciousness_e159_escalation(db_session: Session, safety_test_patient):
    """Active question E_159 -> Patient answers 'yes' -> E_159 PRESENT -> RED_FLAG_LOSS_OF_CONSCIOUSNESS -> HIGH urgency."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Passed out"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    stub_llm = StubLLM(
        extracted_items=[
            ExtractedEvidenceItem(evidence_code="E_159", status=EvidenceStatus.PRESENT)
        ]
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=stub_llm,
    )

    result = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="yes",
        actor_auth_user_id="pat-safety-usr-2",
    )

    assert result.is_complete is True
    assert result.stop_reason == "EMERGENCY_RED_FLAG"
    assert "RED_FLAG_LOSS_OF_CONSCIOUSNESS" in result.safety_flags
    assert result.assessment.urgency == TriageUrgency.HIGH
    assert result.assessment.red_flag_detected is True
    assert result.selected_question is None


# ==============================================================================
# 8.C: GEMINI 429 / QUOTA EXCEEDED
# ==============================================================================

def test_regression_gemini_429_quota_exceeded(db_session: Session, safety_test_patient, caplog):
    """Simulate Gemini 429 RESOURCE_EXHAUSTED -> structured QUOTA_EXCEEDED log, HTTP 503, no mock fallback."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Cough and fever"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    gemini = GeminiProvider(api_key="valid-test-key-mocked")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError(
        "429 RESOURCE_EXHAUSTED: Quota exceeded for metric: generativelanguage.googleapis.com"
    )
    gemini._client = mock_client

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=gemini,
    )

    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="yes, I have had it for 3 days",
            actor_auth_user_id="pat-safety-usr-2",
        )

    assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
    assert exc_info.value.status_code == 503

    # Verify structured failure log
    log_records = [r.message for r in caplog.records if "[GEMINI_FAILURE]" in r.message]
    assert len(log_records) > 0
    event = json.loads(log_records[0].replace("[GEMINI_FAILURE] ", ""))
    assert event["provider"] == "gemini"
    assert event["failure_category"] == "QUOTA_EXCEEDED"
    assert event["http_status"] == 429
    assert event["is_quota_limit"] is True
    assert event["operation"] == "evidence_extraction"

    # Verify security: no api key or patient text logged in failure event
    assert "valid-test-key-mocked" not in log_records[0]
    assert "I have had it for 3 days" not in log_records[0]

    # Verify session in DB was NOT completed or corrupted with partial assessment
    db_session.refresh(session)
    assert session.status == TriageSessionStatus.IN_PROGRESS


# ==============================================================================
# 8.D: GEMINI AUTHENTICATION FAILURE
# ==============================================================================

def test_regression_gemini_auth_failure(db_session: Session, safety_test_patient, caplog):
    """Simulate Gemini 401 UNAUTHENTICATED -> structured AUTHENTICATION_ERROR log, HTTP 503, no mock fallback."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Headache"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    gemini = GeminiProvider(api_key="invalid-api-key-test")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError(
        "401 UNAUTHENTICATED: API_KEY_INVALID"
    )
    gemini._client = mock_client

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=gemini,
    )

    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="my head hurts",
            actor_auth_user_id="pat-safety-usr-2",
        )

    assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
    assert exc_info.value.status_code == 503

    log_records = [r.message for r in caplog.records if "[GEMINI_FAILURE]" in r.message]
    assert len(log_records) > 0
    event = json.loads(log_records[0].replace("[GEMINI_FAILURE] ", ""))
    assert event["failure_category"] == "AUTHENTICATION_ERROR"
    assert event["http_status"] == 401


# ==============================================================================
# 8.E: GEMINI NETWORK FAILURE
# ==============================================================================

def test_regression_gemini_network_failure(db_session: Session, safety_test_patient, caplog):
    """Simulate connection timeout -> structured NETWORK_ERROR log, HTTP 503, no mock fallback."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Nausea"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    gemini = GeminiProvider(api_key="valid-test-key-mocked")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ConnectionError(
        "Connection timed out while connecting to googleapis"
    )
    gemini._client = mock_client

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=gemini,
    )

    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="feeling nauseous",
            actor_auth_user_id="pat-safety-usr-2",
        )

    assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
    assert exc_info.value.status_code == 503

    log_records = [r.message for r in caplog.records if "[GEMINI_FAILURE]" in r.message]
    assert len(log_records) > 0
    event = json.loads(log_records[0].replace("[GEMINI_FAILURE] ", ""))
    assert event["failure_category"] == "NETWORK_ERROR"


# ==============================================================================
# 8.F: NO MOCKLLM REMAINS IN RUNTIME TRIAGE
# ==============================================================================

def test_regression_no_mock_llm_in_runtime():
    """Verify MockLLMProvider is completely deleted from app.services.llm and orchestrator."""
    import app.services.llm as llm_module
    assert not hasattr(llm_module, "MockLLMProvider"), "MockLLMProvider must NOT be exported in app.services.llm"

    import app.services.triage.orchestrator as orch_module
    assert not hasattr(orch_module, "MockLLMProvider"), "MockLLMProvider must NOT be in orchestrator module"


# ==============================================================================
# 8.G: PATIENT-FACING DIAGNOSTIC PROTECTION
# ==============================================================================

def test_regression_patient_facing_diagnostic_protection(db_session: Session, safety_test_patient):
    """Verify patient-facing message and assessment rationale NEVER contain disease claims or diagnoses."""
    from app.schemas.patient_state import PatientState

    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Mild fever and fatigue"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    stub_llm = StubLLM(extracted_items=[])
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=stub_llm)

    state = PatientState(
        session_id=session.id,
        patient_id=safety_test_patient.id,
        conversation_turn=5,
        chief_complaint="Fever and fatigue",
        symptom_duration="1 week",
        patient_reported_severity=4,
    )
    state.mark_present("E_91", True)

    response = orchestrator._finalize_session(
        session=session,
        state=state,
        patient_message_text="no other symptoms",
        turn_count=5,
        stop_reason="STOP_SUFFICIENT_EVIDENCE",
        needs_escalation=False,
        extracted_data=[],
    )

    # 1. Verify patient-facing message NEVER contains provisional diagnostic claim
    msg = response.assistant_message
    assert "HIV" not in msg, f"Prohibited disease name leaked into assistant message: {msg}"
    assert "initial infection" not in msg
    assert "most consistent with" not in msg
    assert "you have" not in msg.lower()
    assert not hasattr(response, "top_candidate_conditions")

    # 2. Verify assessment rationale does NOT assert disease diagnosis
    assert "HIV" not in response.assessment.rationale

    # 3. Verify safe care navigation is communicated
    assert response.assessment.urgency == TriageUrgency.MODERATE
    assert "routed your care to" in msg or "navigated your care to" in msg


# ==============================================================================
# 8.H: EMERGENCY DETERMINISTIC SAFETY OVERRIDES DIFFERENTIAL
# ==============================================================================

def test_regression_emergency_overrides_differential(db_session: Session, safety_test_patient):
    """A deterministic red flag (E_66) must trip HIGH urgency regardless of candidate conditions."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Breathing issue"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    # Simulate presence of breathing difficulty evidence E_66
    stub_llm = StubLLM(
        extracted_items=[
            ExtractedEvidenceItem(evidence_code="E_66", status=EvidenceStatus.PRESENT)
        ]
    )

    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=stub_llm)

    result = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="yes",
        actor_auth_user_id="pat-safety-usr-2",
    )

    assert result.is_complete is True
    assert result.assessment.urgency == TriageUrgency.HIGH
    assert result.assessment.red_flag_detected is True
    assert result.assessment.needs_escalation is True
    assert "RED_FLAG_BREATHING_DIFFICULTY" in result.safety_flags


# ==============================================================================
# 8.I: DDXPLUS ONTOLOGY REGRESSION VERIFICATION
# ==============================================================================

def test_regression_ddxplus_ontology_evidence_mappings():
    """Verify actual DDXPlus ontology definitions against release_evidences.json."""
    ev_66 = ddxplus_provider.get_evidence("E_66")
    assert ev_66 is not None
    q66 = ev_66["question_en"].lower()
    assert "shortness of breath" in q66 or "difficulty breathing" in q66

    ev_159 = ddxplus_provider.get_evidence("E_159")
    assert ev_159 is not None
    q159 = ev_159["question_en"].lower()
    assert "lose consciousness" in q159

    # Verify that E_88 is fatigue, NOT breathing difficulty
    ev_88 = ddxplus_provider.get_evidence("E_88")
    assert ev_88 is not None
    q88 = ev_88["question_en"].lower()
    assert "tired" in q88 or "unable to do your usual activities" in q88
    assert "shortness of breath" not in q88

    # Verify that E_201 is cough, NOT loss of consciousness
    ev_201 = ddxplus_provider.get_evidence("E_201")
    assert ev_201 is not None
    q201 = ev_201["question_en"].lower()
    assert "cough" in q201
    assert "consciousness" not in q201


# ==============================================================================
# 8.J: ACTIVE QUESTION CONTEXT PASSED TO EXTRACTION
# ==============================================================================

def test_regression_active_question_context_passed_to_llm(db_session: Session, safety_test_patient):
    """Verify that the previous assistant question and evidence ID are correctly forwarded in context."""
    from app.repositories.triage_repository import triage_repo

    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Fever and cough"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    # Simulate assistant asked about breathing difficulty in previous turn
    triage_repo.add_message(
        db=db_session,
        session_id=session.id,
        sender="patient",
        content="I have a fever",
        turn_index=1,
    )
    triage_repo.add_message(
        db=db_session,
        session_id=session.id,
        sender="assistant",
        content="Are you experiencing shortness of breath or difficulty breathing in a significant way?",
        turn_index=1,
        extracted_evidence=json.dumps({"selected_evidence_id": "E_66", "information_gain": 0.45}),
    )

    stub_llm = StubLLM(
        extracted_items=[
            ExtractedEvidenceItem(evidence_code="E_66", status=EvidenceStatus.PRESENT)
        ]
    )

    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=stub_llm)

    orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I think so",
        actor_auth_user_id="pat-safety-usr-2",
    )

    # Check that extraction received active question context
    ctx = stub_llm.last_context
    assert ctx is not None
    assert ctx["active_evidence_id"] == "E_66"
    assert "shortness of breath" in ctx["active_question_text"].lower()


# ==============================================================================
# PHASE 1 REGRESSION SUITE: OBJECTIVES A, B, C, D
# ==============================================================================

# --- Objective A: Red-Flag Negation & Polarity Handling ---

def test_regression_red_flag_scenarios_a_through_g():
    """Verify conservative clinical negation, polarity splitting, and uncertainty handling."""
    # Scenario A: Explicitly affirmed emergency warning sign
    flags_a, unc_a = TriageService._screen_red_flags_detailed("I have severe crushing chest pain.")
    assert "RED_FLAG_CHEST_PAIN_SEVERE" in flags_a or "RED_FLAG_CHEST_PAIN" in flags_a
    assert len(unc_a) == 0

    # Scenario B: Negated warning sign must NOT trigger emergency
    flags_b, unc_b = TriageService._screen_red_flags_detailed("I don't have chest pain.")
    assert "RED_FLAG_CHEST_PAIN" not in flags_b
    assert "RED_FLAG_CHEST_PAIN_SEVERE" not in flags_b

    # Scenario C: Denied breathing difficulty must NOT trigger emergency
    flags_c, unc_c = TriageService._screen_red_flags_detailed("I have no shortness of breath.")
    assert "RED_FLAG_BREATHING_DIFFICULTY" not in flags_c

    # Scenario D: Compound sentence with independent polarities
    # Affirmative chest pain must NOT be suppressed by denied breathing difficulty
    flags_d, unc_d = TriageService._screen_red_flags_detailed(
        "I have chest pain, but I don't have breathing difficulty."
    )
    assert any(f in flags_d for f in ["RED_FLAG_CHEST_PAIN", "RED_FLAG_CHEST_PAIN_SEVERE"])
    assert "RED_FLAG_BREATHING_DIFFICULTY" not in flags_d

    # Scenario E: Uncertain statement preserves uncertainty without silent assumption
    flags_e, unc_e = TriageService._screen_red_flags_detailed("I am not sure whether I have chest pain.")
    assert len(flags_a) > 0  # sanity check that chest pain is a flag
    assert not any(f in flags_e for f in ["RED_FLAG_CHEST_PAIN", "RED_FLAG_CHEST_PAIN_SEVERE"])
    assert any(f in unc_e for f in ["RED_FLAG_CHEST_PAIN", "RED_FLAG_CHEST_PAIN_SEVERE"])

    # Scenario F: Post-symptom 'not improved' does not negate existence of symptom
    flags_f, unc_f = TriageService._screen_red_flags_detailed("My chest pain has not improved.")
    assert any(f in flags_f for f in ["RED_FLAG_CHEST_PAIN", "RED_FLAG_CHEST_PAIN_SEVERE"])

    # Scenario G: Multi-word negation several words before symptom
    flags_g, unc_g = TriageService._screen_red_flags_detailed(
        "I definitely do not experience any chest pain whatsoever."
    )
    assert not any(f in flags_g for f in ["RED_FLAG_CHEST_PAIN", "RED_FLAG_CHEST_PAIN_SEVERE"])


# --- Objective B: Controlled Evidence Mappings ---

def test_regression_controlled_evidence_map_audit():
    """Verify CONTROLLED_EVIDENCE_MAP does not map abdominal complaints to sweating."""
    from app.services.llm.gemini import CONTROLLED_EVIDENCE_MAP

    # A & B: Stomach / epigastric pain must NOT map to E_50 (sweating)
    for phrase in ["stomach pain", "stomach ache", "epigastric pain", "abdominal pain"]:
        assert CONTROLLED_EVIDENCE_MAP.get(phrase) != "E_50", f"'{phrase}' illegally maps to E_50"

    # D: Sweating mapping is preserved for sweating phrases
    assert CONTROLLED_EVIDENCE_MAP.get("sweating") == "E_50"
    assert CONTROLLED_EVIDENCE_MAP.get("increased sweating") == "E_50"

    # Verify all entries in CONTROLLED_EVIDENCE_MAP exist in the canonical DDXPlus ontology
    for phrase, code in CONTROLLED_EVIDENCE_MAP.items():
        base_code = code.split("_@_")[0]
        ev = ddxplus_provider.get_evidence(base_code)
        assert ev is not None, f"Mapping '{phrase}' -> '{code}' is not in canonical DDXPlus ontology"

    # Unsupported or hallucinated evidence codes must be rejected by validator
    is_valid, _ = ddxplus_provider.validate_evidence("E_NON_EXISTENT_9999", True)
    assert is_valid is False


# --- Objective C: Acuity and Urgency Logic ---

def test_regression_acuity_keyword_negation_and_deduplication(db_session: Session):
    """Verify that negated keywords do not inflate acuity and duplicate codes are deduplicated."""
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=StubLLM())

    # Scenario A: 'Slight fever' with no other confirmed findings -> not HIGH
    state_a = PatientState(
        session_id="s-a",
        patient_id="p-a",
        conversation_turn=1,
        chief_complaint="Slight fever",
    )
    state_a.mark_present("E_91", True, name="Fever")
    urgency_a, _, _ = orchestrator._calculate_acuity_and_urgency(state_a)
    assert urgency_a != TriageUrgency.HIGH
    assert urgency_a == TriageUrgency.MODERATE  # fever keyword (2) + present symptom (1) = 3 (MODERATE)

    # Scenario B: 'No severe pain' -> must not get points for 'severe' or 'pain'
    state_b = PatientState(
        session_id="s-b",
        patient_id="p-b",
        conversation_turn=1,
        chief_complaint="No severe pain",
    )
    urgency_b, _, _ = orchestrator._calculate_acuity_and_urgency(state_b)
    assert urgency_b == TriageUrgency.LOW

    # Scenario C: 'I have mild pain, no vomiting, and no breathing difficulty'
    state_c = PatientState(
        session_id="s-c",
        patient_id="p-c",
        conversation_turn=1,
        chief_complaint="I have mild pain, no vomiting, and no breathing difficulty",
    )
    state_c.mark_present("E_MILD_PAIN", True)
    state_c.mark_absent("E_148")  # vomiting absent
    state_c.mark_absent("E_66")   # dyspnea absent
    urgency_c, _, _ = orchestrator._calculate_acuity_and_urgency(state_c)
    assert urgency_c != TriageUrgency.HIGH

    # Scenario D: Emergency override remains intact
    state_d = PatientState(
        session_id="s-d",
        patient_id="p-d",
        conversation_turn=1,
        chief_complaint="Normal complaint",
    )
    state_d.emergency_detected = True
    urgency_d, conf_d, _ = orchestrator._calculate_acuity_and_urgency(state_d)
    assert urgency_d == TriageUrgency.HIGH
    assert conf_d == 1.0

    # Scenario E: Duplicate evidence counting
    # E_54 and compound code E_54_@_V_180 must count once as a single base symptom
    state_e = PatientState(
        session_id="s-e",
        patient_id="p-e",
        conversation_turn=1,
        chief_complaint="General checkup",
    )
    state_e.mark_present("E_54", True)
    state_e.mark_present("E_54_@_V_180", True)
    urgency_e, _, _ = orchestrator._calculate_acuity_and_urgency(state_e)
    # E_54 is non-cardio base symptom (+1), deduplicated by base code
    assert urgency_e == TriageUrgency.LOW


# --- Objective D: Patient-State Consistency and Correction ---

def test_regression_patient_state_correction_and_subcode_cleanup():
    """Verify that later denials cleanly evict compound present codes and maintain source attribution."""
    state = PatientState(session_id="s-corr", patient_id="p-corr", conversation_turn=1)

    # Turn 1: Patient affirms severe chest pain subcode
    state.mark_present("E_54_@_V_180", True, name="Crushing chest pain", source_message_id="msg-1")
    assert "E_54_@_V_180" in state.known_present_evidence
    assert state.observations["E_54_@_V_180"].status == EvidenceStatus.PRESENT
    assert state.observations["E_54_@_V_180"].source_message_id == "msg-1"

    # Turn 2: Patient corrects: denies chest pain (base E_54)
    state.mark_absent("E_54", name="Chest pain", source_message_id="msg-2")

    # Stale affirmative subcode must be completely removed from known_present_evidence
    assert "E_54" not in state.known_present_evidence
    assert "E_54_@_V_180" not in state.known_present_evidence
    assert "E_54" in state.known_absent_evidence
    assert state.observations["E_54_@_V_180"].status == EvidenceStatus.ABSENT
    assert state.observations["E_54"].source_message_id == "msg-2"


def test_regression_reconstruct_patient_state_with_corrections(db_session: Session):
    """Verify _reconstruct_patient_state replaying history correctly applies later corrections."""
    from app.models.triage_session import TriageSession
    from app.models.triage_message import TriageMessage

    session = TriageSession(
        id="sess-001",
        patient_id="p-test",
        original_input="Chest discomfort",
        status=TriageSessionStatus.IN_PROGRESS,
    )

    msg1 = TriageMessage(
        id="msg-001",
        session_id=session.id,
        sender="patient",
        content="I might have chest pain",
        turn_index=1,
        extracted_evidence=json.dumps([
            {"evidence_code": "E_54_@_V_180", "status": "PRESENT", "value": True}
        ]),
    )
    msg2 = TriageMessage(
        id="msg-002",
        session_id=session.id,
        sender="assistant",
        content="Are you sure the chest pain is crushing?",
        turn_index=1,
        extracted_evidence=json.dumps({"selected_evidence_id": "E_54"}),
    )
    msg3 = TriageMessage(
        id="msg-003",
        session_id=session.id,
        sender="patient",
        content="No, I made a mistake, I have no chest pain at all.",
        turn_index=2,
        extracted_evidence=json.dumps([
            {"evidence_code": "E_54", "status": "ABSENT", "value": False}
        ]),
    )

    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=StubLLM())
    state = orchestrator._reconstruct_patient_state(session, [msg1, msg2, msg3], turn_count=3)

    # After msg3 correction, E_54 and its compound subcode must not be PRESENT
    assert "E_54" not in state.known_present_evidence
    assert "E_54_@_V_180" not in state.known_present_evidence
    assert "E_54" in state.known_absent_evidence
    assert state.observations["E_54"].status == EvidenceStatus.ABSENT
    assert state.observations["E_54"].source_message_id == "msg-003"


def test_regression_orchestrator_turn_with_negated_red_flag_does_not_escalate(
    db_session: Session, safety_test_patient
):
    """Orchestrator does not trigger emergency escalation for 'I don't have chest pain'."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Routine check"),
        actor_auth_user_id="pat-safety-usr-2",
    )

    stub_llm = StubLLM(extracted_items=[])
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=stub_llm)

    response = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I don't have chest pain, just feeling a bit tired.",
        actor_auth_user_id="pat-safety-usr-2",
    )

    # Should NOT be escalated to emergency
    assert response.is_complete is False
    assert response.stop_reason != "EMERGENCY_RED_FLAG"

