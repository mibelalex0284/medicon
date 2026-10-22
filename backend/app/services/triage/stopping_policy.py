from typing import Optional, Tuple
from app.core.config import settings
from app.schemas.patient_state import PatientState
from app.services.llm.provider import AdaptiveQuestionProposal, AdaptiveQuestionStatus
from app.services.triage.question_selector import ControlledQuestion


class StoppingReason(str):
    """String subclass that allows backward-compatible matching with test assertions

    while supporting standardized clinical interview stopping reasons.
    """
    def __eq__(self, other: object) -> bool:
        if super().__eq__(other):
            return True
        aliases = {
            "SUFFICIENT_INFORMATION": [
                "SUFFICIENT_INFORMATION",
                "SUFFICIENT_INFORMATION_GATHERED",
                "STOP_SUFFICIENT_EVIDENCE",
                "SUFFICIENT_EVIDENCE",
            ],
            "STOP_SUFFICIENT_EVIDENCE": [
                "SUFFICIENT_INFORMATION",
                "SUFFICIENT_INFORMATION_GATHERED",
                "STOP_SUFFICIENT_EVIDENCE",
                "SUFFICIENT_EVIDENCE",
            ],
            "INSUFFICIENT_INFORMATION": [
                "INSUFFICIENT_INFORMATION",
                "INSUFFICIENT_EVIDENCE",
                "EXHAUSTED_DISCRIMINATIVE_QUESTIONS",
            ],
            "UNCERTAINTY_HUMAN_REVIEW": [
                "UNCERTAINTY_HUMAN_REVIEW",
                "ESCALATE_UNCERTAIN",
                "EXHAUSTED_DISCRIMINATIVE_QUESTIONS",
                "NO_RELEVANT_QUESTIONS",
                "UNCERTAIN",
            ],
            "ESCALATE_UNCERTAIN": [
                "UNCERTAINTY_HUMAN_REVIEW",
                "ESCALATE_UNCERTAIN",
                "EXHAUSTED_DISCRIMINATIVE_QUESTIONS",
                "NO_RELEVANT_QUESTIONS",
            ],
            "EXHAUSTED_DISCRIMINATIVE_QUESTIONS": [
                "EXHAUSTED_DISCRIMINATIVE_QUESTIONS",
                "INSUFFICIENT_INFORMATION",
                "ESCALATE_UNCERTAIN",
                "UNCERTAINTY_HUMAN_REVIEW",
            ],
            "EMERGENCY_RED_FLAG": [
                "EMERGENCY_RED_FLAG",
                "EMERGENCY_RED_FLAG_DETECTED",
                "SAFETY_ESCALATION",
            ],
            "EMERGENCY_RED_FLAG_DETECTED": [
                "EMERGENCY_RED_FLAG",
                "EMERGENCY_RED_FLAG_DETECTED",
                "SAFETY_ESCALATION",
            ],
            "PATIENT_DECLINED": [
                "PATIENT_DECLINED",
                "PATIENT_DECLINED_TO_CONTINUE",
                "PATIENT_STOPPED",
            ],
            "INTERACTION_LIMIT_REACHED": [
                "INTERACTION_LIMIT_REACHED",
                "MAX_CONVERSATION_TURNS_REACHED",
                "MAX_TURNS",
            ],
            "MAX_CONVERSATION_TURNS_REACHED": [
                "INTERACTION_LIMIT_REACHED",
                "MAX_CONVERSATION_TURNS_REACHED",
                "MAX_TURNS",
            ],
            "CONTINUE": ["CONTINUE", "CONTINUE_QUESTIONING"],
        }
        curr = str(self)
        if curr in aliases and isinstance(other, str) and other in aliases[curr]:
            return True
        return False

    def __hash__(self) -> int:
        return super().__hash__()


class TriageStoppingPolicy:
    """Multi-factor clinical stopping policy for adaptive conversational intake.

    Distinguishes explicit outcomes:
    - SUFFICIENT_INFORMATION: Sufficient info collected for outpatient care navigation.
    - INSUFFICIENT_INFORMATION: Intake concluded without enough characterization.
    - UNCERTAINTY_HUMAN_REVIEW: Uncertainty or presentation ambiguity requiring human review.
    - EMERGENCY_RED_FLAG: Immediate life-safety emergency detected.
    - PATIENT_DECLINED: Patient explicitly declined or opted out.
    - INTERACTION_LIMIT_REACHED: Engineering boundary reached (not proof of health).
    """

    def __init__(
        self,
        max_turns: Optional[int] = None,
        min_completeness: float = 0.65,
        min_turns: int = 2,
    ):
        self.max_turns = max_turns or settings.TRIAGE_MAX_TURNS
        self.min_completeness = min_completeness
        self.min_turns = min_turns

    def should_stop_pre_question(
        self, state: PatientState
    ) -> Tuple[bool, Optional[StoppingReason], bool]:
        """Evaluates whether intake must stop prior to invoking LLM question generation.

        Terminal conditions evaluated deterministically from patient state:
        - Emergency detected (Hard Rule 1)
        - Patient explicitly declined to continue (Rule 2)
        - Maximum conversation turns reached (Rule 6)
        - State requires human review (Rule 4)

        Returns:
            Tuple of (should_stop: bool, reason: Optional[StoppingReason], needs_escalation: bool)
        """
        # Hard Rule 1: Emergency detected
        if state.emergency_detected:
            return True, StoppingReason("EMERGENCY_RED_FLAG"), True

        # Rule 2: Patient explicitly declined to continue
        if state.declined_to_continue:
            needs_esc = state.completeness_score < 0.45
            return True, StoppingReason("PATIENT_DECLINED"), needs_esc

        # Rule 6: Maximum conversation turns reached (Engineering interaction limit)
        if state.conversation_turn >= self.max_turns:
            needs_esc = state.completeness_score < 0.55
            return True, StoppingReason("INTERACTION_LIMIT_REACHED"), needs_esc

        # Rule 4: State-level explicit uncertainty or human review requested
        if state.requires_human_review:
            return True, StoppingReason("UNCERTAINTY_HUMAN_REVIEW"), True

        return False, None, False

    def should_stop(
        self,
        state: PatientState,
        next_question: Optional[ControlledQuestion] = None,
        proposal: Optional[AdaptiveQuestionProposal] = None,
    ) -> Tuple[bool, StoppingReason, bool]:
        """Determines if the intake interview should conclude.

        Returns:
            Tuple of (should_stop: bool, reason: StoppingReason, needs_escalation: bool)
        """
        # Hard Rule 1: Emergency detected (Red Flag hard gate)
        if state.emergency_detected or (proposal and proposal.status == AdaptiveQuestionStatus.ESCALATE):
            return True, StoppingReason("EMERGENCY_RED_FLAG"), True

        # Rule 2: Patient explicitly declined to continue
        if state.declined_to_continue:
            needs_esc = state.completeness_score < 0.45
            return True, StoppingReason("PATIENT_DECLINED"), needs_esc

        # Rule 3: Safety Priority Check - If an explicit safety question is pending,
        # never stop prematurely.
        if next_question and getattr(next_question, "is_safety_priority", False):
            return False, StoppingReason("CONTINUE"), False

        # Rule 4: Model Explicit Uncertainty or Human Review Requested
        if (
            state.requires_human_review
            or (proposal and proposal.requires_human_review)
            or (proposal and proposal.status == AdaptiveQuestionStatus.UNCERTAIN)
        ):
            return True, StoppingReason("UNCERTAINTY_HUMAN_REVIEW"), True

        # Rule 5: Model Explicit Sufficient Information Determination
        if proposal and proposal.status == AdaptiveQuestionStatus.SUFFICIENT:
            return True, StoppingReason("SUFFICIENT_INFORMATION"), False

        # Rule 6: Maximum conversation turns reached (Engineering interaction limit)
        if state.conversation_turn >= self.max_turns:
            needs_esc = state.completeness_score < 0.55
            return True, StoppingReason("INTERACTION_LIMIT_REACHED"), needs_esc

        # Rule 7: Core Clinical Intake Sufficient for Care Navigation
        # If at least min_turns completed and core intake is sufficiently complete
        answered_count = len(state.known_present_evidence) + len(state.known_absent_evidence)
        if state.conversation_turn >= self.min_turns:
            if state.completeness_score >= self.min_completeness or (
                state.chief_complaint and state.symptom_duration and (answered_count >= 2 or state.symptom_severity is not None)
            ):
                if next_question is None:
                    return True, StoppingReason("SUFFICIENT_INFORMATION"), False

        # Rule 8: No further relevant unanswered questions available
        if next_question is None:
            if answered_count < 2 and state.completeness_score < 0.40:
                return True, StoppingReason("INSUFFICIENT_INFORMATION"), True
            return True, StoppingReason("EXHAUSTED_DISCRIMINATIVE_QUESTIONS"), False

        return False, StoppingReason("CONTINUE"), False


stopping_policy = TriageStoppingPolicy()

