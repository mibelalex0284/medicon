import datetime
import pytest
from sqlalchemy.orm import Session

from unittest.mock import MagicMock
from app.core.exceptions import ForbiddenError, InvalidStateTransitionError, TriageLLMUnavailableError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.schemas.triage import TriageSessionCreate
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage_service import triage_service


class DeterministicTestLLM(LLMProvider):
    """Test-boundary deterministic stub implementing LLMProvider interface for unit testing."""

    def __init__(self, items=None, phrase_prefix="Stub question: "):
        self.items = items or []
        self.phrase_prefix = phrase_prefix

    def extract_patient_evidence(self, message: str, context=None) -> ExtractedEvidenceResult:
        if not self.items:
            # Basic deterministic extraction for test cases
            if "cough" in message.lower():
                return ExtractedEvidenceResult(
                    chief_complaint=message[:100],
                    items=[
                        ExtractedEvidenceItem(evidence_code="E_201", status=EvidenceStatus.PRESENT),
                        ExtractedEvidenceItem(evidence_code="E_127", status=EvidenceStatus.PRESENT),
                    ],
                )
        return ExtractedEvidenceResult(
            chief_complaint=message[:100],
            items=self.items,
        )

    def phrase_question(self, controlled_question: str, evidence_id: str, context=None) -> str:
        return f"{self.phrase_prefix}{controlled_question}"

    def propose_next_question(self, context):
        from app.services.llm.provider import AdaptiveQuestionProposal, AdaptiveQuestionStatus
        gaps = context.get("information_gaps", [])
        past = context.get("questions_asked", [])
        complaint = context.get("chief_complaint", "symptoms")

        q_duration = f"How long have you had this {complaint}?"
        q_severity = "How severe is your discomfort on a scale of 1 to 10?"
        q_progression = "Have your symptoms been getting better or worse?"
        q_impact = "Is this preventing you from daily activities?"
        q_associated = "Do you have any chills or body aches?"
        q_character = "Are your symptoms constant or intermittent?"

        if not any(q_duration in str(p) for p in past):
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question=q_duration,
                intent="Determine duration",
                target_information=["duration_onset"],
                reason="Duration gap",
            )
        elif not any(q_severity in str(p) for p in past):
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question=q_severity,
                intent="Determine severity",
                target_information=["severity_progression"],
                reason="Severity gap",
            )
        elif not any(q_progression in str(p) for p in past):
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question=q_progression,
                intent="Determine progression",
                target_information=["symptom_progression"],
                reason="Progression gap",
            )
        elif not any(q_impact in str(p) for p in past):
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question=q_impact,
                intent="Determine functional impact",
                target_information=["functional_impact"],
                reason="Functional impact gap",
            )
        elif not any(q_associated in str(p) for p in past):
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question=q_associated,
                intent="Check associated symptoms",
                target_information=["associated_symptoms_and_pertinent_negatives"],
                reason="Associated symptoms gap",
            )
        elif not any(q_character in str(p) for p in past):
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question=q_character,
                intent="Check character",
                target_information=["symptom_character_location"],
                reason="Character gap",
            )
        return AdaptiveQuestionProposal(
            status=AdaptiveQuestionStatus.SUFFICIENT,
            question=None,
            intent="Intake completed",
            target_information=[],
            reason="Core information gathered",
        )

    def summarize_conversation(self, messages) -> str:
        return "Test summary"


@pytest.fixture
def test_patient(db_session: Session):
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-orch-usr-1",
            role=UserRole.PATIENT,
            full_name="Alex Conversational",
            email="alex.conv@test.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=prof.id, date_of_birth=datetime.date(1995, 5, 20)),
    )
    for name, code in [
        ("Dermatology", "DERM"),
        ("ENT", "ENT"),
        ("Orthopedics", "ORTHO"),
        ("Cardiology", "CARDIO"),
        ("General Medicine", "GEN"),
    ]:
        try:
            specialty_service.create_specialty(
                db_session, SpecialtyCreate(name=name, code=code)
            )
        except Exception:
            pass
    return patient


def test_orchestrator_emergency_red_flag_hard_gate(db_session: Session, test_patient):
    """Verify that a message with crushing chest pain immediately trips emergency escalation."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="I don't feel well"),
        actor_auth_user_id="pat-orch-usr-1",
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=DeterministicTestLLM(),
    )

    result = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I have severe crushing chest pain and shortness of breath",
        actor_auth_user_id="pat-orch-usr-1",
    )

    assert result.is_complete is True
    assert result.stop_reason == "EMERGENCY_RED_FLAG"
    assert "RED_FLAG_CHEST_PAIN_SEVERE" in result.safety_flags
    assert result.assessment is not None
    assert result.assessment.urgency == TriageUrgency.HIGH
    assert result.assessment.red_flag_detected is True
    assert "emergency" in result.assistant_message.lower()

    # Verify session is escalated in db
    db_session.refresh(session)
    assert session.status == TriageSessionStatus.ESCALATED


def test_orchestrator_normal_conversational_turn(db_session: Session, test_patient):
    """Verify normal presentation extracts symptoms and selects next adaptive question."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Mild fever"),
        actor_auth_user_id="pat-orch-usr-1",
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=DeterministicTestLLM(),
    )

    turn1 = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I have had a mild cough and headache for 2 days.",
        actor_auth_user_id="pat-orch-usr-1",
    )

    assert turn1.is_complete is False
    assert turn1.conversation_turn == 1
    assert turn1.selected_question is not None
    assert len(turn1.selected_question.question_text) > 0
    assert len(turn1.assistant_message) > 0
    assert not hasattr(turn1, "top_candidate_conditions")
    assert turn1.completeness_score >= 0.0

    # Verify session remains IN_PROGRESS
    db_session.refresh(session)
    assert session.status == TriageSessionStatus.IN_PROGRESS


def test_orchestrator_non_owner_forbidden(db_session: Session, test_patient):
    """Verify other patients cannot access or message another user's session."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Sore throat"),
        actor_auth_user_id="pat-orch-usr-1",
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=DeterministicTestLLM(),
    )

    with pytest.raises(ForbiddenError):
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="Hello",
            actor_auth_user_id="different-malicious-user",
        )


def test_orchestrator_completed_session_transition_error(db_session: Session, test_patient):
    """Verify messages sent to completed session are rejected."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Feeling sick"),
        actor_auth_user_id="pat-orch-usr-1",
    )
    # Manually complete session
    session.status = TriageSessionStatus.COMPLETED
    db_session.commit()

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=DeterministicTestLLM(),
    )

    with pytest.raises(InvalidStateTransitionError):
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="Can I ask another question?",
            actor_auth_user_id="pat-orch-usr-1",
        )


def test_orchestrator_llm_failure_raises_unavailable(db_session: Session, test_patient):
    """Verify that when LLM provider fails, system raises TriageLLMUnavailableError (HTTP 503) without mock fallback."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Skin rash"),
        actor_auth_user_id="pat-orch-usr-1",
    )

    failing_provider = MagicMock(spec=LLMProvider)
    failing_provider.extract_patient_evidence.side_effect = TriageLLMUnavailableError(
        message="Conversational triage is temporarily unavailable. Please try again later or contact your care provider directly.",
        code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=failing_provider,
    )

    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="I have a red rash on my arm.",
            actor_auth_user_id="pat-orch-usr-1",
        )

    assert exc_info.value.code == "TRIAGE_LLM_SERVICE_UNAVAILABLE"
    assert exc_info.value.status_code == 503


# ==============================================================================
# NEW REQUIREMENT TESTS: PATIENT STATE, ROUTING, URGENCY, REPORT, SAFETY
# ==============================================================================

def test_patient_state_observations_and_structure():
    """Verify PatientState stores observations with present, absent, unknown, duration, severity."""
    from app.schemas.patient_state import PatientState, SymptomObservation

    state = PatientState(session_id="s_test", patient_id="p_test", chief_complaint="persistent headache")
    state.symptom_duration = "5 days"
    state.patient_reported_severity = 8

    state.mark_present("E_91", True)
    state.mark_absent("E_66")
    state.mark_unknown("E_53")

    assert state.is_known("E_91") is True
    assert state.is_known("E_66") is True
    assert state.is_known("E_53") is True
    assert state.known_present_evidence["E_91"] is True
    assert "E_66" in state.known_absent_evidence
    assert "E_53" in state.unknown_evidence
    assert state.symptom_duration == "5 days"
    assert state.patient_reported_severity == 8

    # Observations dictionary
    state.observations["E_91"] = SymptomObservation(
        code="E_91",
        name="Fever",
        status=EvidenceStatus.PRESENT,
        value=True,
        confidence=1.0,
        category="GENERAL",
    )
    assert len(state.observations) == 3
    assert state.observations["E_91"].code == "E_91"
    assert state.observations["E_66"].status == EvidenceStatus.ABSENT
    assert state.observations["E_53"].status == EvidenceStatus.UNKNOWN


def test_specialty_routing_deterministic(db_session: Session, test_patient):
    """Verify symptom clusters route deterministically to correct medical specialties."""
    from app.schemas.patient_state import PatientState

    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=DeterministicTestLLM())

    # Dermatology routing
    state_derm = PatientState(session_id="s_d", patient_id="p1", chief_complaint="itchy skin rash and eczema")
    spec_derm = orchestrator._determine_specialty(state_derm)
    assert spec_derm is not None
    assert spec_derm.code == "DERM" or "dermatology" in spec_derm.name.lower()

    # Musculoskeletal / Orthopedics routing
    state_ortho = PatientState(session_id="s_o", patient_id="p1", chief_complaint="swollen knee joint pain and back stiffness")
    spec_ortho = orchestrator._determine_specialty(state_ortho)
    assert spec_ortho is not None
    assert spec_ortho.code == "ORTHO" or "orthopedics" in spec_ortho.name.lower()

    # ENT routing
    state_ent = PatientState(session_id="s_e", patient_id="p1", chief_complaint="severe sore throat and ear pain")
    spec_ent = orchestrator._determine_specialty(state_ent)
    assert spec_ent is not None
    assert spec_ent.code == "ENT" or "ent" in spec_ent.name.lower()

    # Cardiology routing
    state_cardio = PatientState(session_id="s_c", patient_id="p1", chief_complaint="heart palpitations and rapid pulse")
    spec_cardio = orchestrator._determine_specialty(state_cardio)
    assert spec_cardio is not None
    assert spec_cardio.code == "CARDIO" or "cardiology" in spec_cardio.name.lower()

    # General Medicine fallback
    state_gen = PatientState(session_id="s_g", patient_id="p1", chief_complaint="general fatigue and mild malaise")
    spec_gen = orchestrator._determine_specialty(state_gen)
    assert spec_gen is not None
    assert "general" in spec_gen.name.lower() or spec_gen.code in ("GEN", "GEN-MED")


def test_urgency_calculation_rules(db_session: Session, test_patient):
    """Verify urgency calculation based on patient severity, duration, and red flags (never disease prediction)."""
    from app.schemas.patient_state import PatientState

    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=DeterministicTestLLM())

    # 1. Emergency detected -> authoritative HIGH
    state_emerg = PatientState(session_id="s_em", patient_id="p1", emergency_detected=True)
    urg_em, conf_em, rationale_em = orchestrator._calculate_acuity_and_urgency(state_emerg)
    assert urg_em == TriageUrgency.HIGH
    assert conf_em == 1.0
    assert "emergency" in rationale_em.lower()

    # 2. Severe non-emergency (severity 9/10) -> HIGH
    state_sev = PatientState(
        session_id="s_sev",
        patient_id="p1",
        chief_complaint="severe headache",
        patient_reported_severity=9,
    )
    urg_sev, _, _ = orchestrator._calculate_acuity_and_urgency(state_sev)
    assert urg_sev == TriageUrgency.HIGH

    # 3. Moderate presentation (severity 6/10) -> MODERATE
    state_mod = PatientState(
        session_id="s_mod",
        patient_id="p1",
        chief_complaint="persistent cough",
        patient_reported_severity=6,
    )
    urg_mod, _, _ = orchestrator._calculate_acuity_and_urgency(state_mod)
    assert urg_mod == TriageUrgency.MODERATE

    # 4. Mild routine presentation -> LOW
    state_low = PatientState(
        session_id="s_low",
        patient_id="p1",
        chief_complaint="mild sniffles",
        patient_reported_severity=2,
    )
    urg_low, _, _ = orchestrator._calculate_acuity_and_urgency(state_low)
    assert urg_low == TriageUrgency.LOW


def test_pre_consultation_report_format_and_safety(db_session: Session, test_patient):
    """Verify Pre-Consultation Intake Report formats present, absent, unknown symptoms and safety without disease claims."""
    from app.schemas.patient_state import PatientState

    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=DeterministicTestLLM())

    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Fever and rash"),
        actor_auth_user_id="pat-orch-usr-1",
    )

    state = PatientState(
        session_id=session.id,
        patient_id=session.patient_id,
        chief_complaint="fever and localized itchy skin rash",
        symptom_duration="4 days",
        patient_reported_severity=6,
    )
    state.mark_present("E_91", True)
    state.mark_absent("E_66")

    report_text = orchestrator._build_pre_consultation_report(
        session=session,
        state=state,
        urgency=TriageUrgency.MODERATE,
        specialty_name="Dermatology",
        guidance="Please schedule an outpatient appointment.",
    )

    # 1. Structure verification
    assert "PRE-CONSULTATION INTAKE SUMMARY" in report_text
    assert "Chief Complaint:" in report_text
    assert "fever and localized itchy skin rash" in report_text
    assert "Duration:" in report_text
    assert "4 days" in report_text
    assert "Patient-Reported Severity (1-10):" in report_text
    assert "6" in report_text
    assert "Present Symptoms" in report_text
    assert "E_91" in report_text
    assert "Explicitly Denied / Pertinent Negatives:" in report_text
    assert "E_66" in report_text
    assert "DENIED" in report_text
    assert "Urgency Level: MODERATE" in report_text
    assert "Recommended Specialty: Dermatology" in report_text
    assert "NOTICE:" in report_text
    assert "not a diagnosis" in report_text.lower()

    # 2. Strict Zero Disease Leakage check
    prohibited_terms = ["hiv", "bronchitis", "pneumonia", "psoriasis", "most consistent with", "you may have"]
    for term in prohibited_terms:
        assert term not in report_text.lower(), f"Prohibited disease claim found in doctor report: {term}"


def test_regression_fever_runny_nose_sequence_never_predicts_hiv(db_session: Session, test_patient):
    """REGRESSION TEST for user scenario:
    Patient inputs: fever, runny nose, no, yes, yes.
    The system must NEVER output 'HIV' or 'most consistent with HIV' or any disease diagnosis.
    Output must be strictly structured care navigation.
    """
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="i had a fever"),
        actor_auth_user_id="pat-orch-usr-1",
    )

    # Multi-turn conversation stub
    messages = [
        ("i had a fever", [ExtractedEvidenceItem(evidence_code="E_91", status=EvidenceStatus.PRESENT)]),
        ("runny nose", [ExtractedEvidenceItem(evidence_code="E_173", status=EvidenceStatus.PRESENT)]),
        ("no", [ExtractedEvidenceItem(evidence_code="E_53", status=EvidenceStatus.ABSENT)]),
        ("yes", [ExtractedEvidenceItem(evidence_code="E_77", status=EvidenceStatus.PRESENT)]),
        ("yes", [ExtractedEvidenceItem(evidence_code="E_50", status=EvidenceStatus.PRESENT)]),
    ]

    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=DeterministicTestLLM())

    final_turn = None
    for text, items in messages:
        orchestrator.llm = DeterministicTestLLM(items=items)
        turn = orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text=text,
            actor_auth_user_id="pat-orch-usr-1",
        )
        final_turn = turn

        # Every turn assistant message must NEVER mention HIV or diseases
        assert "hiv" not in turn.assistant_message.lower()
        assert "most consistent with" not in turn.assistant_message.lower()
        assert not hasattr(turn, "top_candidate_conditions")

    # If completed, check assessment rationale and assistant message
    if final_turn.assessment:
        assert "hiv" not in final_turn.assessment.rationale.lower()
        assert "diagnosis" not in final_turn.assessment.rationale.lower() or "not a diagnosis" in final_turn.assessment.rationale.lower()


def test_orchestrator_get_pre_consultation_report_reconstructs_turn_count(
    db_session: Session, test_patient
):
    """Regression test: get_pre_consultation_report passes turn_count to _reconstruct_patient_state without error."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Dry cough and mild fatigue"),
        actor_auth_user_id="pat-orch-usr-1",
    )

    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=DeterministicTestLLM(
            items=[ExtractedEvidenceItem(evidence_code="E_201", status=EvidenceStatus.PRESENT)]
        ),
    )

    # Process one turn
    turn1 = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text="I have had a dry cough for 3 days",
        actor_auth_user_id="pat-orch-usr-1",
    )
    assert turn1.conversation_turn == 1

    # Retrieve pre-consultation report directly from orchestrator
    report = orchestrator.get_pre_consultation_report(session.id)
    assert report.session_id == session.id
    assert report.patient_id == test_patient.id
    assert len(report.present_symptoms) >= 1
    assert "cough" in report.present_symptoms[0].lower()
    assert report.urgency in [TriageUrgency.LOW, TriageUrgency.MODERATE, TriageUrgency.HIGH]
    assert "It is not a diagnosis" in report.notice


