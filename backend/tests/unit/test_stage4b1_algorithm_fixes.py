import datetime
import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStateTransitionError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.patient_state import PatientState
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.schemas.triage import TriageSessionCreate
from app.services.llm.provider import LLMProvider
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.services.triage.evidence_provider import ddxplus_provider
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage.question_selector import question_selector, ControlledQuestion
from app.services.triage.stopping_policy import stopping_policy, TriageStoppingPolicy
from app.services.triage_service import triage_service


# ==============================================================================
# 1. DDXPLUS PARENT/CHILD DEPENDENCY ENFORCEMENT
# ==============================================================================

def test_dependency_parent_present_child_eligible():
    """Verify child evidence is eligible when its parent evidence is PRESENT."""
    child_id = None
    parent_id = None
    for evid, p_id in ddxplus_provider._parent_evidences.items():
        if p_id in ddxplus_provider._evidences:
            child_id = evid
            parent_id = p_id
            break

    assert child_id is not None and parent_id is not None
    known_present = {parent_id: True}
    known_absent = []
    assert ddxplus_provider.is_dependency_satisfied(child_id, known_present, known_absent) is True


def test_dependency_parent_absent_child_rejected():
    """Verify child evidence is rejected when its parent evidence is ABSENT."""
    child_id = None
    parent_id = None
    for evid, p_id in ddxplus_provider._parent_evidences.items():
        if p_id in ddxplus_provider._evidences:
            child_id = evid
            parent_id = p_id
            break

    assert child_id is not None and parent_id is not None
    known_present = {}
    known_absent = [parent_id]
    assert ddxplus_provider.is_dependency_satisfied(child_id, known_present, known_absent) is False


def test_dependency_parent_unknown_child_rejected():
    """Verify child evidence is not eligible when its parent has not yet been asked."""
    child_id = None
    parent_id = None
    for evid, p_id in ddxplus_provider._parent_evidences.items():
        if p_id in ddxplus_provider._evidences:
            child_id = evid
            parent_id = p_id
            break

    assert child_id is not None and parent_id is not None
    known_present = {}
    known_absent = []
    assert ddxplus_provider.is_dependency_satisfied(child_id, known_present, known_absent) is False


# ==============================================================================
# 2. CATEGORICAL / COMPOSITE EVIDENCE PRESERVATION
# ==============================================================================

def test_categorical_multichoice_evidence_preservation():
    """Verify state preserves categorical value choices accurately."""
    state = PatientState(session_id="sim_test", patient_id="p1")
    m_ev = "E_54_@_V_180"
    val = "V_180"
    state.mark_present(m_ev, val)

    assert "E_54_@_V_180" in state.known_present_evidence
    assert state.known_present_evidence["E_54_@_V_180"] == "V_180"
    assert state.is_known("E_54") is True


# ==============================================================================
# 3. INTERVIEW COMPLETENESS STOPPING POLICY
# ==============================================================================

def test_stopping_policy_sufficient_completeness():
    """Verify stopping when clinical intake reaches sufficient completeness."""
    policy = TriageStoppingPolicy(min_completeness=0.70, min_turns=2)
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        conversation_turn=3,
        completeness_score=0.80,
    )
    should_stop, reason, needs_esc = policy.should_stop(state)
    assert should_stop is True
    assert reason == "STOP_SUFFICIENT_EVIDENCE"
    assert needs_esc is False


def test_stopping_policy_continue_on_incomplete():
    """Verify continuation when interview is incomplete and questions remain."""
    policy = TriageStoppingPolicy(max_turns=6, min_completeness=0.70)
    state = PatientState(
        session_id="s2",
        patient_id="p1",
        conversation_turn=2,
        completeness_score=0.30,
    )
    q = ControlledQuestion(
        evidence_id="E_91",
        question_text="Do you have fever?",
    )
    should_stop, reason, _ = policy.should_stop(state, next_question=q)
    assert should_stop is False
    assert reason == "CONTINUE_QUESTIONING"


def test_stopping_policy_max_turns():
    """Verify stopping when max conversation turns are reached."""
    policy = TriageStoppingPolicy(max_turns=5, min_completeness=0.70)
    state = PatientState(
        session_id="s5",
        patient_id="p1",
        conversation_turn=5,
        completeness_score=0.40,
    )
    should_stop, reason, needs_esc = policy.should_stop(state)
    assert should_stop is True
    assert reason == "MAX_CONVERSATION_TURNS_REACHED"
    assert needs_esc is True


# ==============================================================================
# 4. SAFETY REGRESSION REQUIREMENT (6 HARD RED FLAGS)
# ==============================================================================

@pytest.fixture
def red_flag_patient(db_session: Session):
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-safety-usr-1",
            role=UserRole.PATIENT,
            full_name="Safety Test Patient",
            email="safety.patient@test.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=prof.id, date_of_birth=datetime.date(1990, 1, 1)),
    )
    for name, code in [
        ("General Medicine", "GEN-MED"),
        ("Cardiology", "CARDIO"),
        ("Emergency", "EMERG"),
    ]:
        try:
            specialty_service.create_specialty(
                db_session, SpecialtyCreate(name=name, code=code)
            )
        except Exception:
            pass
    return patient


@pytest.mark.parametrize(
    "red_flag_text,expected_code",
    [
        ("I am having severe crushing chest pain and pressure in my chest", "RED_FLAG_CHEST_PAIN_SEVERE"),
        ("I can't breathe and have difficulty breathing", "RED_FLAG_BREATHING_DIFFICULTY"),
        ("I can't catch my breath", "RED_FLAG_BREATHING_DIFFICULTY"),
        ("I have severe respiratory distress", "RED_FLAG_BREATHING_DIFFICULTY"),
        ("Patient experienced sudden loss of consciousness and fainted", "RED_FLAG_LOSS_OF_CONSCIOUSNESS"),
        ("There is severe bleeding and coughing up blood", "RED_FLAG_SEVERE_BLEEDING"),
        ("Sudden facial droop and slurred speech indicating stroke", "RED_FLAG_SUDDEN_NEUROLOGICAL_DEFICIT"),
        ("Severe throat swelling and anaphylaxis shock", "RED_FLAG_ANAPHYLAXIS"),
    ],
)
def test_hard_red_flags_trigger_immediate_escalation(
    db_session: Session, red_flag_patient, red_flag_text, expected_code
):
    """Verify all hard red flags trigger immediate HIGH urgency, escalation, and halt triage."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Not feeling well"),
        actor_auth_user_id="pat-safety-usr-1",
    )
    orchestrator = ConversationalTriageOrchestrator(
        db=db_session,
        llm_provider=MagicMock(spec=LLMProvider),
    )

    result = orchestrator.process_patient_turn(
        session_id=session.id,
        patient_message_text=red_flag_text,
        actor_auth_user_id="pat-safety-usr-1",
    )

    # 1. Immediate completion & escalation
    assert result.is_complete is True
    assert result.stop_reason == "EMERGENCY_RED_FLAG"
    assert result.assessment is not None
    assert result.assessment.urgency == TriageUrgency.HIGH
    assert result.assessment.red_flag_detected is True
    assert expected_code in result.safety_flags

    # 2. Emergency guidance provided, no ordinary adaptive question
    assert result.selected_question is None
    assert "emergency" in result.assistant_message.lower()

    # 3. Session transitioned to ESCALATED in DB
    db_session.refresh(session)
    assert session.status == TriageSessionStatus.ESCALATED

    # 4. Subsequent message must NOT continue normal triage
    with pytest.raises(InvalidStateTransitionError):
        orchestrator.process_patient_turn(
            session_id=session.id,
            patient_message_text="Actually I also have a mild headache",
            actor_auth_user_id="pat-safety-usr-1",
        )
