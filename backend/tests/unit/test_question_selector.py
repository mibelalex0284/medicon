import pytest
from app.schemas.patient_state import PatientState
from app.services.triage.question_selector import (
    ControlledQuestion,
    InformationCompletenessQuestionSelector,
)


def test_select_next_question_returns_valid_question():
    """Verify next question selection returns a valid ControlledQuestion."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(
        session_id="test_sess",
        patient_id="test_pat",
        chief_complaint="persistent cough and fever",
    )
    state.mark_present("E_91", True)

    question = selector.select_next_question(state)

    assert question is not None
    assert isinstance(question, ControlledQuestion)
    assert len(question.evidence_id) > 0
    assert len(question.question_text) > 0
    assert question.evidence_id != "E_91"


def test_safety_question_priority():
    """Verify safety-critical screening questions are prioritized first."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(
        session_id="test_sess",
        patient_id="test_pat",
        chief_complaint="I feel dizzy and unwell",
    )

    question = selector.select_next_question(state)
    assert question is not None
    # Top priority safety screening question (e.g. E_66 dyspnea, E_159 syncope, or severe chest pain)
    assert question.category == "SAFETY_CRITICAL" or question.priority >= 90
    assert question.evidence_id in {"E_66", "E_159", "E_54_@_V_180", "E_45", "E_211"}


def test_chief_complaint_cluster_prioritization():
    """Verify presentation clusters are prioritized based on chief complaint keywords."""
    selector = InformationCompletenessQuestionSelector()

    # Dermatological complaint
    state_derm = PatientState(
        session_id="test_sess_derm",
        patient_id="test_pat",
        chief_complaint="severe itchy skin rash on arms",
    )
    # Mark safety questions asked so it moves to complaint exploration
    for code in ["E_66", "E_159", "E_54_@_V_180", "E_45", "E_211"]:
        state_derm.record_question_asked(code)

    q_derm = selector.select_next_question(state_derm)
    assert q_derm is not None
    assert q_derm.category in ("DERMATOLOGY", "CHIEF_COMPLAINT", "ASSOCIATED_SYMPTOM")

    # Joint / Ortho complaint
    state_ortho = PatientState(
        session_id="test_sess_ortho",
        patient_id="test_pat",
        chief_complaint="knee joint pain and swelling",
    )
    for code in ["E_66", "E_159", "E_54_@_V_180", "E_45", "E_211"]:
        state_ortho.record_question_asked(code)

    q_ortho = selector.select_next_question(state_ortho)
    assert q_ortho is not None
    assert q_ortho.category in ("MUSCULOSKELETAL", "CHIEF_COMPLAINT", "ASSOCIATED_SYMPTOM")


def test_no_repeat_questions():
    """Verify already asked or answered questions are never asked again."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(
        session_id="test_sess",
        patient_id="test_pat",
        chief_complaint="chest pressure",
    )

    q1 = selector.select_next_question(state)
    assert q1 is not None

    state.record_question_asked(q1.evidence_id)

    q2 = selector.select_next_question(state)
    assert q2 is not None
    assert q2.evidence_id != q1.evidence_id

    # Marking present also prevents re-asking
    state.mark_present(q2.evidence_id, True)
    q3 = selector.select_next_question(state)
    assert q3 is not None
    assert q3.evidence_id not in (q1.evidence_id, q2.evidence_id)


def test_dependency_enforcement():
    """Verify child questions are not asked if parent symptom is absent."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(
        session_id="test_sess",
        patient_id="test_pat",
        chief_complaint="cough and cold",
    )

    child_map = selector.evidence_provider._child_evidences
    if child_map:
        parent_code = next(iter(child_map.keys()))
        children = list(child_map[parent_code])
        if children:
            child = children[0]
            # Explicitly mark parent absent
            state.mark_absent(parent_code)
            # The selector should never select this child
            for _ in range(5):
                q = selector.select_next_question(state)
                if not q:
                    break
                assert q.evidence_id != child
                state.record_question_asked(q.evidence_id)


def test_completeness_score_calculation():
    """Verify completeness score increases as patient reports data."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(
        session_id="test_sess",
        patient_id="test_pat",
        chief_complaint="severe headache",
    )
    score0 = selector.compute_completeness_score(state)

    state.symptom_duration = "3 days"
    score1 = selector.compute_completeness_score(state)
    assert score1 > score0

    state.patient_reported_severity = 7
    score2 = selector.compute_completeness_score(state)
    assert score2 > score1

    state.mark_present("E_91", True)
    state.mark_absent("E_66")
    score3 = selector.compute_completeness_score(state)
    assert score3 > score2
    assert 0.0 <= score3 <= 1.0
