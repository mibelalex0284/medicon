import datetime
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import TriageLLMUnavailableError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.patient_state import PatientState
from app.schemas.profile import ProfileCreate
from app.schemas.triage import TriageSessionCreate
from app.repositories.triage_repository import triage_repo
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.llm.provider import (
    AdaptiveQuestionProposal,
    AdaptiveQuestionStatus,
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage.question_selector import (
    ControlledQuestion,
    InformationCompletenessQuestionSelector,
)
from app.services.triage.stopping_policy import StoppingReason, TriageStoppingPolicy
from app.services.triage_service import triage_service


class FakeScriptedLLMProvider:
    """Deterministic, offline fake LLM provider for unit and regression testing."""

    def __init__(
        self,
        extractions: Optional[List[ExtractedEvidenceResult]] = None,
        proposals: Optional[List[AdaptiveQuestionProposal]] = None,
        raise_on_propose: Optional[Exception] = None,
        raise_on_extract: Optional[Exception] = None,
    ):
        self.extractions = list(extractions or [])
        self.proposals = list(proposals or [])
        self.raise_on_propose = raise_on_propose
        self.raise_on_extract = raise_on_extract
        self.extraction_calls: List[Dict[str, Any]] = []
        self.proposal_calls: List[Dict[str, Any]] = []

    def extract_patient_evidence(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> ExtractedEvidenceResult:
        self.extraction_calls.append({"message": message, "context": context})
        if self.raise_on_extract:
            raise self.raise_on_extract
        if self.extractions:
            return self.extractions.pop(0)
        return ExtractedEvidenceResult(
            chief_complaint=message,
            duration=None,
            severity=None,
            items=[],
        )

    def propose_next_question(
        self, context: Dict[str, Any]
    ) -> AdaptiveQuestionProposal:
        self.proposal_calls.append(context)
        if self.raise_on_propose:
            raise self.raise_on_propose
        if self.proposals:
            return self.proposals.pop(0)
        return AdaptiveQuestionProposal(
            status=AdaptiveQuestionStatus.ASK,
            question="How long have you been experiencing this symptom?",
            intent="Collect duration and onset",
            target_information=["duration_onset"],
            reason="Duration is not yet established",
        )

    def phrase_question(
        self, controlled_question: str, evidence_id: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        return controlled_question

    def summarize_conversation(self, messages: List[Dict[str, str]]) -> str:
        return "Deterministic test summary."

    def close(self) -> None:
        pass


@pytest.fixture
def triage_patient(db_session: Session):
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-triage-usr-1",
            role=UserRole.PATIENT,
            full_name="Adaptive Test Patient",
            email="adaptive.patient@test.org",
        ),
    )
    return patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=prof.id, date_of_birth=datetime.date(1995, 5, 20)),
    )


@pytest.fixture
def make_session(db_session: Session, triage_patient):
    def _create(complaint: str):
        return triage_service.create_session(
            db_session,
            TriageSessionCreate(original_input=complaint),
            actor_auth_user_id="pat-triage-usr-1",
        )
    return _create


# =========================================================================
# Scenario 1 to 10: Diverse Complaint Scenarios (Complaint-Agnostic)
# =========================================================================

def test_scenario_01_headache(db_session: Session, make_session):
    """Scenario 1: Headache complaint adapts dynamically without fixed clusters."""
    session = make_session("I have had a throbbing headache for 2 days.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="throbbing headache",
                duration="2 days",
                severity=6,
                items=[ExtractedEvidenceItem(evidence_code="E_91", status=EvidenceStatus.ABSENT)],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Is your headache accompanied by visual changes or sensitivity to light?",
                intent="Identify associated neurological features",
                target_information=["associated_symptoms_and_pertinent_negatives"],
                reason="Characterize headache associated symptoms",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "My headache is throbbing on the left side.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "visual changes" in turn.assistant_message
    assert turn.selected_question is not None
    assert "associated" in turn.selected_question.category.lower()
    # No diagnosis stated
    assert "migraine" not in turn.assistant_message.lower()


def test_scenario_02_abdominal_discomfort(db_session: Session, make_session):
    """Scenario 2: Abdominal discomfort."""
    session = make_session("I have stomach cramps and discomfort.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="stomach cramps",
                duration=None,
                severity=4,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="How long have you had this stomach discomfort?",
                intent="Identify symptom duration",
                target_information=["duration_onset"],
                reason="Onset/duration needed for intake handoff",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It started after lunch.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "How long" in turn.assistant_message


def test_scenario_03_skin_changes(db_session: Session, make_session):
    """Scenario 3: Skin changes."""
    session = make_session("I noticed a red patch on my forearm.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="red patch on forearm",
                duration="yesterday",
                severity=2,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Is the rash itchy, painful, or warm to the touch?",
                intent="Characterize skin presentation quality",
                target_information=["symptom_character_location"],
                reason="Skin characterization needed",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It appeared yesterday.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "itchy" in turn.assistant_message.lower()


def test_scenario_04_joint_pain(db_session: Session, make_session):
    """Scenario 4: Joint pain."""
    session = make_session("My knee has been stiff and painful.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="knee stiffness and pain",
                duration="1 week",
                severity=5,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Does the knee pain limit your ability to bear weight or walk?",
                intent="Assess functional mobility impact",
                target_information=["functional_impact"],
                reason="Determine functional impairment for orthopedics triage",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It hurts when bending.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "bear weight" in turn.assistant_message


def test_scenario_05_dizziness(db_session: Session, make_session):
    """Scenario 5: Dizziness."""
    session = make_session("I feel dizzy when I stand up quickly.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="postural dizziness",
                duration="3 days",
                severity=4,
                items=[ExtractedEvidenceItem(evidence_code="E_159", status=EvidenceStatus.ABSENT)],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Have you had any sensation of the room spinning around you?",
                intent="Differentiate vertigo from lightheadedness",
                target_information=["symptom_character_location"],
                reason="Determine dizziness type",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It happens mainly in the morning.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "room spinning" in turn.assistant_message


def test_scenario_06_sleep_difficulties(db_session: Session, make_session):
    """Scenario 6: Sleep difficulties (outside legacy fixed clusters)."""
    session = make_session("I have been unable to sleep properly for two weeks.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="insomnia",
                duration="two weeks",
                severity=5,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Do you have difficulty falling asleep, or do you wake up frequently during the night?",
                intent="Characterize sleep pattern disturbance",
                target_information=["symptom_character_location"],
                reason="Characterize insomnia type",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "I wake up at 3 AM every night.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "falling asleep" in turn.assistant_message


def test_scenario_07_emotional_distress(db_session: Session, make_session):
    """Scenario 7: Emotional distress / mental health."""
    session = make_session("I have been feeling very overwhelmed and anxious.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="anxiety and overwhelm",
                duration="1 month",
                severity=6,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Is your anxiety affecting your ability to focus on daily tasks or work?",
                intent="Assess functional daily impact",
                target_information=["functional_impact"],
                reason="Assess daily life impact",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It has been difficult at work.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "daily tasks" in turn.assistant_message


def test_scenario_08_urinary_symptoms(db_session: Session, make_session):
    """Scenario 8: Urinary symptoms (outside legacy clusters)."""
    session = make_session("I have painful and frequent urination.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="dysuria and frequency",
                duration="2 days",
                severity=5,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Have you noticed any blood in your urine or lower back pain?",
                intent="Screen for upper urinary tract indicators",
                target_information=["associated_symptoms_and_pertinent_negatives"],
                reason="Check pertinent negatives for dysuria",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It burns when I urinate.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "blood in your urine" in turn.assistant_message


def test_scenario_09_dental_pain(db_session: Session, make_session):
    """Scenario 9: Dental pain (outside legacy clusters)."""
    session = make_session("Severe toothache on my lower right jaw.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="lower jaw toothache",
                duration="3 days",
                severity=7,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Is there any visible swelling around your jaw, cheek, or gums?",
                intent="Check for acute swelling or infection spread",
                target_information=["symptom_character_location"],
                reason="Screen dental swelling",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "The tooth is very sensitive to cold.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "swelling" in turn.assistant_message


def test_scenario_10_vague_complaint(db_session: Session, make_session):
    """Scenario 10: Vague complaint ('I feel strange')."""
    session = make_session("I just feel strange and not like myself.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="feels strange and unwell",
                duration=None,
                severity=None,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Can you tell me more about what feels strange, such as fatigue, dizziness, or bodily discomfort?",
                intent="Clarify vague symptom presentation",
                target_information=["symptom_character_location"],
                reason="Chief complaint characterization needed",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "I can't put my finger on it.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "tell me more" in turn.assistant_message.lower()


# =========================================================================
# Scenario 11 to 22: Structural, Edge, Validation, and Safety Tests
# =========================================================================

def test_scenario_11_multiple_complaints_in_one_message(db_session: Session, make_session):
    """Scenario 11: Multiple complaints presented at once."""
    session = make_session("I have back pain, an earache, and feel mildly nauseous.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="back pain and earache",
                duration="4 days",
                severity=5,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Which of these symptoms is currently causing you the most discomfort?",
                intent="Prioritize primary complaint",
                target_information=["symptom_character_location"],
                reason="Focus on primary chief complaint",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "My ear hurts the most.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "most discomfort" in turn.assistant_message


def test_scenario_12_unclear_patient_description(db_session: Session, make_session):
    """Scenario 12: Patient who cannot describe the complaint clearly."""
    session = make_session("Something is wrong.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="unclear discomfort",
                duration=None,
                severity=None,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Are you experiencing any physical pain or discomfort in a specific part of your body?",
                intent="Anchor presentation to an anatomical region",
                target_information=["symptom_character_location"],
                reason="Anchor vague complaint",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "I don't know how to explain it.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "physical pain" in turn.assistant_message


def test_scenario_13_patient_correction(db_session: Session, make_session):
    """Scenario 13: Patient corrects a previous answer."""
    session = make_session("I have fever and cough.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="cough without fever",
                duration="3 days",
                severity=3,
                items=[
                    ExtractedEvidenceItem(evidence_code="E_91", status=EvidenceStatus.ABSENT),
                    ExtractedEvidenceItem(evidence_code="E_88", status=EvidenceStatus.PRESENT),
                ],
                corrections=["Patient corrected fever from present to absent"],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Is your cough dry, or are you coughing up mucus?",
                intent="Characterize cough quality",
                target_information=["symptom_character_location"],
                reason="Cough characterization",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(
        session.id,
        "Actually I made a mistake earlier, I do NOT have a fever, just a dry cough.",
        "pat-triage-usr-1",
    )

    state = orchestrator._reconstruct_patient_state(session, triage_repo.get_session_messages(db_session, session.id), 1)
    assert "E_91" in state.known_absent_evidence
    assert "E_91" not in state.known_present_evidence
    assert len(state.corrections) > 0


def test_scenario_14_contradictory_answers(db_session: Session, make_session):
    """Scenario 14: Contradictory answers handled safely without crashing."""
    session = make_session("Leg pain")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="leg pain",
                duration="5 days",
                severity=4,
                items=[
                    ExtractedEvidenceItem(evidence_code="E_130", status=EvidenceStatus.PRESENT),
                    ExtractedEvidenceItem(evidence_code="E_130", status=EvidenceStatus.ABSENT),
                ],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Is the leg pain constant, or does it come and go?",
                intent="Clarify temporal pattern",
                target_information=["severity_progression"],
                reason="Clarify temporal pattern",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It hurts but it doesn't hurt.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert turn.assistant_message.endswith("?")


def test_scenario_15_unanswered_question(db_session: Session, make_session):
    """Scenario 15: Patient does not answer the asked question."""
    session = make_session("Headache")
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(session_id=session.id, patient_id=session.patient_id, chief_complaint="Headache")
    state.record_unanswered_question("How long have you had this headache?")

    assert "How long have you had this headache?" in state.unanswered_questions


def test_scenario_16_duplicate_question_rejected(db_session: Session):
    """Scenario 16: Repeated / duplicate generated question is rejected by backend validation."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(session_id="s1", patient_id="p1", chief_complaint="Back pain")

    past = ["How long have you had this back pain?"]
    proposal = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.ASK,
        question="How long have you had this back pain?",
        intent="Collect duration",
        target_information=["duration_onset"],
    )

    valid, reason = selector.validate_proposed_question(proposal, state, past_question_texts=past)
    assert valid is False
    assert "DUPLICATE_QUESTION" in reason


def test_scenario_17_invalid_structured_output_rejected(db_session: Session):
    """Scenario 17: Invalid Gemini structured output fails validation."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(session_id="s1", patient_id="p1", chief_complaint="Fever")

    # Empty question text
    bad_proposal = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.ASK,
        question="",
        intent="test",
        target_information=[],
    )
    valid, reason = selector.validate_proposed_question(bad_proposal, state)
    assert valid is False
    assert "EMPTY_QUESTION_TEXT" in reason

    # Compound question (multiple question marks)
    compound_proposal = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.ASK,
        question="Do you have a fever? And are you coughing?",
        intent="test",
        target_information=[],
    )
    valid, reason = selector.validate_proposed_question(compound_proposal, state)
    assert valid is False
    assert "COMPOUND_QUESTION" in reason


def test_scenario_18_gemini_provider_failure_fails_closed(db_session: Session, make_session):
    """Scenario 18: Gemini provider failure / timeout raises explicit 503 fail-closed exception."""
    session = make_session("Chest discomfort")
    failing_provider = FakeScriptedLLMProvider(
        raise_on_extract=TriageLLMUnavailableError(
            message="Conversational triage is temporarily unavailable.",
            code="TRIAGE_LLM_SERVICE_UNAVAILABLE",
        )
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=failing_provider)

    with pytest.raises(TriageLLMUnavailableError) as exc_info:
        orchestrator.process_patient_turn(session.id, "I have chest discomfort.", "pat-triage-usr-1")
    assert "temporarily unavailable" in str(exc_info.value)


def test_scenario_19_uncertain_response_human_review(db_session: Session, make_session):
    """Scenario 19: An uncertain response concludes with UNCERTAINTY_HUMAN_REVIEW outcome."""
    session = make_session("Vague tingling sensations")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="tingling sensations",
                duration=None,
                severity=None,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.UNCERTAIN,
                question=None,
                intent=None,
                target_information=[],
                reason="Clinical presentation is ambiguous and requires direct physician review.",
                requires_human_review=True,
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "I feel strange tingles everywhere.", "pat-triage-usr-1")

    assert turn.is_complete is True
    assert turn.stop_reason in ("UNCERTAINTY_HUMAN_REVIEW", "ESCALATE_UNCERTAIN")
    assert turn.assessment is not None
    assert turn.assessment.needs_escalation is True


def test_scenario_20_safety_concern_interrupts_questioning(db_session: Session, make_session):
    """Scenario 20: Safety concern interrupts ordinary questioning immediately."""
    session = make_session("Mild headache")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[],
        proposals=[],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "Suddenly I can't breathe and my chest hurts!", "pat-triage-usr-1")

    assert turn.is_complete is True
    assert turn.stop_reason == "EMERGENCY_RED_FLAG"
    assert turn.assessment.urgency == TriageUrgency.HIGH
    assert turn.assessment.red_flag_detected is True
    assert len(fake_provider.proposal_calls) == 0


def test_scenario_21_interaction_limit_reached(db_session: Session, make_session):
    """Scenario 21: Reaching interaction limit concludes with explicit limit outcome."""
    session = make_session("Persistent mild cough")
    policy = TriageStoppingPolicy(max_turns=3)
    state = PatientState(
        session_id=session.id,
        patient_id=session.patient_id,
        conversation_turn=3,
        chief_complaint="Persistent mild cough",
    )
    should_stop, reason, needs_esc = policy.should_stop(state)

    assert should_stop is True
    assert reason == StoppingReason("INTERACTION_LIMIT_REACHED")


def test_scenario_22_unpredefined_complaint_category(db_session: Session, make_session):
    """Scenario 22: Complaint not in any predefined category (e.g. eye twitching / blepharospasm)."""
    session = make_session("My left eyelid has been fluttering and twitching uncontrollably.")
    fake_provider = FakeScriptedLLMProvider(
        extractions=[
            ExtractedEvidenceResult(
                chief_complaint="eyelid twitching",
                duration="4 days",
                severity=2,
                items=[],
            )
        ],
        proposals=[
            AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Have you been experiencing high stress, lack of sleep, or excessive caffeine intake recently?",
                intent="Identify common triggers for eyelid twitching",
                target_information=["associated_symptoms_and_pertinent_negatives"],
                reason="Trigger exploration for blepharospasm",
            )
        ],
    )
    orchestrator = ConversationalTriageOrchestrator(db=db_session, llm_provider=fake_provider)
    turn = orchestrator.process_patient_turn(session.id, "It twitches constantly when I look at screens.", "pat-triage-usr-1")

    assert turn.is_complete is False
    assert "stress" in turn.assistant_message.lower()
    assert "fever" not in turn.assistant_message.lower()
    assert "cough" not in turn.assistant_message.lower()


# =========================================================================
# Additional Specific Boundary and Verification Tests
# =========================================================================

def test_diagnostic_claim_in_question_rejected():
    """Verify that a proposed question asserting a diagnosis as fact is rejected."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(session_id="s1", patient_id="p1", chief_complaint="Headache")

    diagnostic_q = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.ASK,
        question="Since you have migraine, does it get worse in bright light?",
        intent="Check photophobia",
        target_information=["symptom_character_location"],
    )
    valid, reason = selector.validate_proposed_question(diagnostic_q, state)
    assert valid is False
    assert "DIAGNOSTIC_CLAIM_ASSERTION" in reason


def test_medication_recommendation_in_question_rejected():
    """Verify that a proposed question recommending medication is rejected."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(session_id="s1", patient_id="p1", chief_complaint="Joint pain")

    rx_q = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.ASK,
        question="Have you tried to take some ibuprofen for the swelling?",
        intent="Medication inquiry",
        target_information=["treatment"],
    )
    valid, reason = selector.validate_proposed_question(rx_q, state)
    assert valid is False
    assert "MEDICATION_OR_TREATMENT_RECOMMENDATION" in reason


def test_previously_established_duration_not_reasked():
    """Verify that question selector rejects questions re-asking known duration."""
    selector = InformationCompletenessQuestionSelector()
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        chief_complaint="Rash",
        symptom_duration="3 days",
    )

    duration_q = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.ASK,
        question="How long have you had this rash on your arm?",
        intent="Collect duration",
        target_information=["duration_onset"],
    )
    valid, reason = selector.validate_proposed_question(duration_q, state)
    assert valid is False
    assert "DURATION_ALREADY_KNOWN" in reason


def test_patient_declined_stopping_outcome():
    """Verify that when patient declines to continue, stopping policy sets PATIENT_DECLINED."""
    policy = TriageStoppingPolicy()
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        chief_complaint="Fatigue",
        declined_to_continue=True,
    )
    should_stop, reason, _ = policy.should_stop(state)
    assert should_stop is True
    assert reason == StoppingReason("PATIENT_DECLINED")


def test_sufficient_information_stopping_outcome():
    """Verify that sufficient information determination stops with SUFFICIENT_INFORMATION."""
    policy = TriageStoppingPolicy()
    state = PatientState(
        session_id="s1",
        patient_id="p1",
        conversation_turn=2,
        chief_complaint="Ankle pain",
        symptom_duration="2 days",
        symptom_severity=4,
    )
    state.mark_present("E_130", True)
    state.mark_absent("E_91")

    proposal = AdaptiveQuestionProposal(
        status=AdaptiveQuestionStatus.SUFFICIENT,
        question=None,
        intent=None,
        target_information=[],
        reason="Sufficient clinical characterization for orthopedics navigation.",
    )
    should_stop, reason, needs_esc = policy.should_stop(state, proposal=proposal)
    assert should_stop is True
    assert reason == StoppingReason("SUFFICIENT_INFORMATION")
    assert needs_esc is False
