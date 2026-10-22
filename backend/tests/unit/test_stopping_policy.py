import pytest
from app.schemas.patient_state import PatientState
from app.services.triage.question_selector import ControlledQuestion
from app.services.triage.stopping_policy import TriageStoppingPolicy


def test_stopping_policy_emergency_gate():
    """Verify emergency detected halts immediately with escalation."""
    policy = TriageStoppingPolicy()
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        emergency_detected=True,
    )

    should_stop, reason, needs_esc = policy.should_stop(state)
    assert should_stop is True
    assert reason == "EMERGENCY_RED_FLAG_DETECTED"
    assert needs_esc is True


def test_stopping_policy_sufficient_completeness():
    """Verify stopping when clinical intake completeness is achieved."""
    policy = TriageStoppingPolicy(min_completeness=0.70, min_turns=2)
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        conversation_turn=3,
        completeness_score=0.85,
    )

    should_stop, reason, needs_esc = policy.should_stop(state)
    assert should_stop is True
    assert reason == "STOP_SUFFICIENT_EVIDENCE"
    assert needs_esc is False


def test_stopping_policy_max_turns():
    """Verify max turns threshold triggers stopping and escalation if incomplete."""
    policy = TriageStoppingPolicy(max_turns=5, min_completeness=0.70)
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        conversation_turn=5,
        completeness_score=0.40,
    )

    should_stop, reason, needs_esc = policy.should_stop(state)
    assert should_stop is True
    assert reason == "MAX_CONVERSATION_TURNS_REACHED"
    assert needs_esc is True


def test_stopping_policy_exhausted_questions():
    """Verify stopping when no further relevant questions exist."""
    policy = TriageStoppingPolicy()
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        conversation_turn=2,
        completeness_score=0.50,
    )

    should_stop, reason, needs_esc = policy.should_stop(state, next_question=None)
    assert should_stop is True
    assert reason == "EXHAUSTED_DISCRIMINATIVE_QUESTIONS"


def test_stopping_policy_continue():
    """Verify continuation when turns remain and completeness threshold is not met."""
    policy = TriageStoppingPolicy(max_turns=7, min_completeness=0.70)
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        conversation_turn=2,
        completeness_score=0.30,
    )
    mock_q = ControlledQuestion(
        evidence_id="E_91",
        question_text="Do you have fever?",
        category="GENERAL",
    )

    should_stop, reason, _ = policy.should_stop(state, next_question=mock_q)
    assert should_stop is False
    assert reason == "CONTINUE_QUESTIONING"
