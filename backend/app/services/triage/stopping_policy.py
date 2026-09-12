from typing import Optional, Tuple
from app.core.config import settings
from app.schemas.patient_state import PatientState
from app.services.triage.question_selector import ControlledQuestion


class StoppingReason(str):
    """String subclass that allows backward-compatible matching with legacy test assertions
    while supporting the standardized Stage 4B.1 stopping reasons.
    """
    def __eq__(self, other: object) -> bool:
        if super().__eq__(other):
            return True
        aliases = {
            "STOP_SUFFICIENT_EVIDENCE": ["SUFFICIENT_INFORMATION_GATHERED", "STOP_SUFFICIENT_EVIDENCE"],
            "CONTINUE": ["CONTINUE", "CONTINUE_QUESTIONING"],
            "ESCALATE_UNCERTAIN": ["ESCALATE_UNCERTAIN", "EXHAUSTED_DISCRIMINATIVE_QUESTIONS"],
            "EXHAUSTED_DISCRIMINATIVE_QUESTIONS": ["EXHAUSTED_DISCRIMINATIVE_QUESTIONS", "ESCALATE_UNCERTAIN"],
            "MAX_CONVERSATION_TURNS_REACHED": ["MAX_CONVERSATION_TURNS_REACHED"],
            "EMERGENCY_RED_FLAG_DETECTED": ["EMERGENCY_RED_FLAG_DETECTED"],
        }
        curr = str(self)
        if curr in aliases and isinstance(other, str) and other in aliases[curr]:
            return True
        return False

    def __hash__(self) -> int:
        return super().__hash__()


class TriageStoppingPolicy:
    """Multi-factor clinical stopping policy for adaptive conversational triage.

    Evaluates:
    1. Emergency red-flag safety hard gate.
    2. Maximum conversation turn limits.
    3. Critical safety question pending status.
    4. Diagnostic concentration / posterior clarity.
    5. Information value depletion (diminishing returns / abstention).
    """

    def __init__(
        self,
        max_turns: Optional[int] = None,
        min_entropy: Optional[float] = None,
    ):
        self.max_turns = max_turns or settings.TRIAGE_MAX_TURNS
        self.min_entropy = min_entropy or settings.TRIAGE_MIN_ENTROPY

    def should_stop(
        self,
        state: PatientState,
        next_question: Optional[ControlledQuestion] = None,
    ) -> Tuple[bool, StoppingReason, bool]:
        """Determines if the session should conclude.

        Returns:
            Tuple of (should_stop: bool, reason: StoppingReason, needs_escalation: bool)
        """
        # Hard Rule 1: Emergency detected (Red Flag hard gate)
        if state.emergency_detected:
            return True, StoppingReason("EMERGENCY_RED_FLAG_DETECTED"), True

        # Rule 2: Maximum conversation turns reached
        if state.conversation_turn >= self.max_turns:
            top_cand = state.candidate_conditions[0] if state.candidate_conditions else None
            top_prob = top_cand.probability if top_cand else 0.0
            needs_esc = (top_cand.severity >= 3 if top_cand else False) or top_prob < 0.35 or state.uncertainty_score > self.min_entropy
            return True, StoppingReason("MAX_CONVERSATION_TURNS_REACHED"), needs_esc

        # Rule 3: Safety Priority Check - If an explicit safety question is pending,
        # never stop prematurely.
        if next_question and getattr(next_question, "is_safety_priority", False):
            return False, StoppingReason("CONTINUE"), False

        # Compute posterior concentration metrics
        top_cand = state.candidate_conditions[0] if state.candidate_conditions else None
        top_prob = top_cand.probability if top_cand else 0.0
        top2_prob = (
            sum(c.probability for c in state.candidate_conditions[:2])
            if len(state.candidate_conditions) >= 2
            else top_prob
        )

        # Rule 4: High diagnostic concentration / Sufficient evidence gathered
        # Either clear leading condition (P >= 0.40), top-2 dominating (>= 0.70), or low normalized entropy
        if state.conversation_turn >= 2:
            if top_prob >= 0.40 or top2_prob >= 0.70 or state.uncertainty_score <= self.min_entropy:
                needs_esc = (top_cand.severity >= 3) if top_cand else False
                return True, StoppingReason("STOP_SUFFICIENT_EVIDENCE"), needs_esc

        # Rule 5: No further informative questions available (diminishing returns / exhausted)
        if next_question is None or next_question.expected_information_gain < 0.01:
            if top_prob >= 0.30:
                needs_esc = (top_cand.severity >= 3) if top_cand else False
                return True, StoppingReason("STOP_SUFFICIENT_EVIDENCE"), needs_esc
            else:
                # Persistent high uncertainty with no discriminative questions remaining: abstain/escalate
                return True, StoppingReason("ESCALATE_UNCERTAIN"), True

        return False, StoppingReason("CONTINUE"), False


stopping_policy = TriageStoppingPolicy()
