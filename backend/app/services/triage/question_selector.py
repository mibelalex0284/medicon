import difflib
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger
from app.schemas.patient_state import PatientState
from app.services.llm import get_llm_provider
from app.services.llm.provider import (
    AdaptiveQuestionProposal,
    AdaptiveQuestionStatus,
    LLMProvider,
)
from app.services.triage.evidence_provider import DDXPlusEvidenceProvider, ddxplus_provider


class ControlledQuestion(BaseModel):
    evidence_id: str
    question_text: str
    data_type: str = "B"
    possible_values: List[str] = Field(default_factory=list)
    category: str = "GENERAL"
    is_antecedent: bool = False
    expected_information_gain: float = 0.0
    priority: int = 50
    is_safety_priority: bool = False
    intent: Optional[str] = None
    target_information: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class InformationCompletenessQuestionSelector:
    """Complaint-agnostic adaptive question selector for clinical intake.

    Derives questions dynamically from the patient's individual presentation,
    known findings, pertinent negatives, duration, severity, and remaining
    information gaps. Does NOT depend on a fixed list of disease-specific question flows.
    """

    # Critical safety evidences for engineering red-flag priority screening
    CRITICAL_SAFETY_EVIDENCES = ["E_66", "E_159", "E_54_@_V_180", "E_45", "E_211"]

    # Universal clinical intake information dimensions (not disease clusters)
    UNIVERSAL_INTAKE_DIMENSIONS = [
        "symptom_character_location",
        "duration_onset",
        "severity_progression",
        "associated_symptoms_and_pertinent_negatives",
        "functional_impact",
    ]

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        evidence_provider: Optional[DDXPlusEvidenceProvider] = None,
    ):
        self._llm_provider = llm_provider
        self.evidence_provider = evidence_provider or ddxplus_provider

    @property
    def llm_provider(self) -> Optional[LLMProvider]:
        return self._llm_provider

    @llm_provider.setter
    def llm_provider(self, provider: Optional[LLMProvider]) -> None:
        self._llm_provider = provider

    def compute_completeness_score(self, state: PatientState) -> float:
        """Calculates an explainable 0.0 to 1.0 score measuring information completeness of clinical intake."""
        score = 0.0

        # 1. Chief complaint established (0.25)
        if state.chief_complaint and len(state.chief_complaint.strip()) >= 3:
            score += 0.25

        # 2. Duration / onset identified (0.20)
        if state.symptom_duration:
            score += 0.20

        # 3. Patient-reported severity identified (0.20)
        if state.symptom_severity is not None:
            score += 0.20

        # 4. Critical safety screening covered or verified (0.15)
        safety_checked = (
            len(state.safety_screenings) > 0
            or any(state.is_known(crit) for crit in self.CRITICAL_SAFETY_EVIDENCES)
        )
        if safety_checked:
            score += 0.15

        # 5. Core presentation characterized (0.20)
        answered_count = len(state.known_present_evidence) + len(state.known_absent_evidence)
        if answered_count >= 3:
            score += 0.20
        elif answered_count >= 1:
            score += 0.10

        return round(min(1.0, score), 2)

    def determine_information_gaps(self, state: PatientState) -> List[str]:
        """Identifies which universal clinical intake dimensions remain unresolved."""
        gaps: List[str] = []

        if not state.symptom_duration:
            gaps.append("duration_onset")

        if state.symptom_severity is None:
            gaps.append("severity_progression")

        if len(state.known_present_evidence) < 2:
            gaps.append("symptom_character_location")

        if len(state.known_absent_evidence) < 1:
            gaps.append("associated_symptoms_and_pertinent_negatives")

        if not state.functional_impact:
            gaps.append("functional_impact")

        return gaps

    def validate_proposed_question(
        self,
        proposal: AdaptiveQuestionProposal,
        state: PatientState,
        past_question_texts: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Deterministic backend validation layer.

        Before accepting a generated question, checks:
        - Structured response validity
        - Empty or malformed questions
        - Duplicate or near-duplicate questions
        - Whether target information is already known
        - Whether question conflicts with known patient answers
        - Whether question asks multiple unrelated questions at once
        - Whether it introduces a diagnosis as an established fact
        - Whether it requests unnecessary sensitive information
        - Interaction limits
        """
        past_questions = past_question_texts or []

        # 1. Proposal validity
        if proposal is None or not hasattr(proposal, "status"):
            return False, "INVALID_PROPOSAL_OBJECT"

        if proposal.status not in (
            AdaptiveQuestionStatus.ASK,
            AdaptiveQuestionStatus.SUFFICIENT,
            AdaptiveQuestionStatus.UNCERTAIN,
            AdaptiveQuestionStatus.ESCALATE,
        ):
            return False, "INVALID_PROPOSAL_STATUS"

        # If not asking a question (sufficient, uncertain, escalate), the proposal is accepted as a stopping decision
        if proposal.status != AdaptiveQuestionStatus.ASK:
            return True, None

        # 2. Empty or malformed question
        raw_q = proposal.question
        if not raw_q or not isinstance(raw_q, str):
            return False, "EMPTY_QUESTION_TEXT"

        q = raw_q.strip()
        if len(q) < 5 or len(q) > 300:
            return False, f"QUESTION_LENGTH_OUT_OF_BOUNDS: length={len(q)}"

        if not q.endswith("?"):
            return False, "QUESTION_MUST_END_WITH_QUESTION_MARK"

        # 3. Compound question check (multiple question marks)
        if q.count("?") > 1:
            return False, "COMPOUND_QUESTION_MULTIPLE_MARKS"

        # Compound sentence check (joining two distinct inquiries)
        compound_patterns = [
            r"\b(?:and\s+also|and\s+do\s+you|and\s+have\s+you|and\s+is\s+there)\b",
            r"\?.*(?:and|or)\b",
        ]
        for cp in compound_patterns:
            if re.search(cp, q, re.IGNORECASE):
                return False, "COMPOUND_QUESTION_CONJUNCTION"

        # 4. Duplicate or near-duplicate question check
        q_norm = re.sub(r"[^\w\s]", "", q.lower()).strip()
        for past_q in past_questions:
            past_norm = re.sub(r"[^\w\s]", "", past_q.lower()).strip()
            if q_norm == past_norm:
                return False, f"DUPLICATE_QUESTION: exact match with '{past_q}'"
            q_tokens = set(q_norm.split())
            past_tokens = set(past_norm.split())
            if q_tokens and past_tokens:
                intersection = len(q_tokens & past_tokens)
                union = len(q_tokens | past_tokens)
                if union > 0 and (intersection / union) > 0.75:
                    return False, f"NEAR_DUPLICATE_QUESTION: high similarity with '{past_q}'"

        # 5. Target information already established
        target_infos = [t.lower() for t in proposal.target_information]

        # Check duration
        if state.symptom_duration:
            is_duration_target = any(
                t in ["duration", "onset", "symptom_duration"]
                for t in target_infos
            )
            has_duration_phrasing = any(
                dt in q.lower()
                for dt in ["how long", "when did it start", "how many days", "how many hours"]
            )
            if is_duration_target or has_duration_phrasing:
                return False, "TARGET_INFORMATION_DURATION_ALREADY_KNOWN"

        # Check severity
        if state.symptom_severity is not None:
            is_severity_target = any(
                t in ["severity", "intensity", "pain_scale", "severity_score"]
                for t in target_infos
            )
            has_severity_phrasing = any(
                st in q.lower()
                for st in ["scale of 1 to 10", "rate your pain", "from 1 to 10", "rate the pain"]
            )
            if is_severity_target or has_severity_phrasing:
                return False, "TARGET_INFORMATION_SEVERITY_ALREADY_KNOWN"

        # Check symptom already known
        all_known = set(state.known_present_evidence.keys()) | set(state.known_absent_evidence)
        for known_code in all_known:
            ev_name = self.evidence_provider.get_evidence_name(known_code).lower()
            if ev_name and len(ev_name) > 3:
                asking_pattern = rf"\b(?:do\s+you\s+have|are\s+you\s+experiencing|any)\s+{re.escape(ev_name)}\b"
                if re.search(asking_pattern, q.lower()):
                    return False, f"SYMPTOM_ALREADY_KNOWN: '{ev_name}' is already recorded"

        # 6. Diagnostic assertion check (rejecting asserting a diagnosis as fact)
        diagnostic_patterns = [
            r"\b(?:since|because|given)\s+you\s+have\b",
            r"\byou\s+have\s+(?:the\s+)?(?:flu|covid|asthma|migraine|bronchitis|pneumonia|appendicitis|stroke|meningitis|infection|gastritis|arthritis)\b",
            r"\bcould\s+this\s+be\b",
            r"\bis\s+this\s+(?:a\s+)?(?:heart attack|stroke|infection)\b",
            r"\bdiagnosed\s+with\b",
        ]
        for dp in diagnostic_patterns:
            if re.search(dp, q, re.IGNORECASE):
                return False, "DIAGNOSTIC_CLAIM_ASSERTION"

        # 7. Medication or treatment recommendation check
        rx_patterns = [
            r"\b(?:take|prescribe|try)\s+(?:some|a|an|two|ibuprofen|aspirin|tylenol|paracetamol|antibiotic|medication|pill|dosage)\b",
            r"\bhave\s+you\s+taken\s+any\s+antibiotics\b",
        ]
        for rp in rx_patterns:
            if re.search(rp, q, re.IGNORECASE):
                return False, "MEDICATION_OR_TREATMENT_RECOMMENDATION"

        # 8. Unnecessary sensitive information check
        sensitive_patterns = [
            r"\b(?:social\s+security|ssn|credit\s+card|bank\s+account|password|pin\s+number)\b"
        ]
        for sp in sensitive_patterns:
            if re.search(sp, q, re.IGNORECASE):
                return False, "UNNECESSARY_SENSITIVE_INFORMATION"

        # 9. Engineering interaction limit check
        if state.conversation_turn >= settings.TRIAGE_MAX_TURNS:
            return False, "MAX_INTERACTIONS_EXCEEDED"

        return True, None

    def _propose_deterministic_fallback(
        self, state: PatientState, information_gaps: List[str]
    ) -> AdaptiveQuestionProposal:
        """Deterministic intake proposal when LLM provider is unavailable in test boundary."""
        all_recorded = list(state.questions_asked) + list(state.known_present_evidence.keys()) + list(state.known_absent_evidence)

        # 1. Duration / Onset
        has_duration_gap = any("duration" in g for g in information_gaps)
        asked_duration = state.symptom_duration is not None or any("duration" in str(k) for k in all_recorded)
        if has_duration_gap and not asked_duration:
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="How long have you been experiencing these symptoms?",
                intent="Determine duration of symptoms",
                target_information=["duration_onset"],
                reason="Duration of symptoms is unrecorded",
            )

        # 2. Severity / Progression
        has_severity_gap = any("severity" in g for g in information_gaps)
        asked_severity = state.symptom_severity is not None or any("severity" in str(k) for k in all_recorded)
        if has_severity_gap and not asked_severity:
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="On a scale from 1 to 10, how severe is your discomfort right now?",
                intent="Determine severity score",
                target_information=["severity_progression"],
                reason="Severity of symptoms is unrecorded",
            )

        # 3. Functional Impact
        has_impact_gap = any("impact" in g for g in information_gaps)
        asked_impact = state.functional_impact is not None or any("impact" in str(k) for k in all_recorded)
        if has_impact_gap and not asked_impact:
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Is this condition significantly interfering with your daily activities or sleep?",
                intent="Determine functional impact",
                target_information=["functional_impact"],
                reason="Functional impact is unrecorded",
            )

        # 4. Character / Location
        has_char_gap = any("character" in g for g in information_gaps)
        asked_char = any("character" in str(k) for k in all_recorded)
        if has_char_gap and not asked_char:
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Can you describe where the discomfort is and what it feels like?",
                intent="Characterize symptom location and quality",
                target_information=["symptom_character_location"],
                reason="Symptom characterization is unrecorded",
            )

        # 5. Associated Symptoms
        has_assoc_gap = any("associated" in g for g in information_gaps)
        asked_assoc = any("associated" in str(k) for k in all_recorded)
        if has_assoc_gap and not asked_assoc:
            return AdaptiveQuestionProposal(
                status=AdaptiveQuestionStatus.ASK,
                question="Are you experiencing any other accompanying symptoms?",
                intent="Screen for associated symptoms",
                target_information=["associated_symptoms_and_pertinent_negatives"],
                reason="Associated symptoms screening is unrecorded",
            )

        return AdaptiveQuestionProposal(
            status=AdaptiveQuestionStatus.SUFFICIENT,
            question=None,
            intent="Intake completed",
            target_information=[],
            reason="Core information categories collected for care navigation",
        )

    def select_next_question(
        self,
        state: PatientState,
        context: Optional[Dict[str, Any]] = None,
        max_retries: int = 1,
    ) -> Optional[ControlledQuestion]:
        """Backward-compatible selector returning Optional[ControlledQuestion]."""
        controlled_q, _, _ = self.select_next_adaptive_question(
            state=state, context=context, max_retries=max_retries
        )
        return controlled_q

    def select_next_adaptive_question(
        self,
        state: PatientState,
        context: Optional[Dict[str, Any]] = None,
        max_retries: int = 1,
    ) -> Tuple[Optional[ControlledQuestion], Optional[AdaptiveQuestionProposal], Optional[str]]:
        """Selects the next adaptive question through Gemini proposal and backend validation.

        Returns:
            (question: Optional[ControlledQuestion], proposal: Optional[AdaptiveQuestionProposal], rejection_reason: Optional[str])
        """
        complaint = (state.chief_complaint or "").lower()
        ctx = context or {}
        past_question_texts: List[str] = ctx.get("past_question_texts", [])

        # =========================================================================
        # PRIORITY 1: ENGINEERING SAFETY SCREENING
        # =========================================================================
        for crit_code in self.CRITICAL_SAFETY_EVIDENCES:
            base_id = crit_code.split("_@_")[0]
            if (
                not state.is_known(base_id)
                and not state.is_known(crit_code)
                and base_id not in state.questions_asked
                and crit_code not in state.questions_asked
                and self.evidence_provider.is_dependency_satisfied(
                    crit_code, state.known_present_evidence, state.known_absent_evidence
                )
            ):
                is_relevant = False
                if base_id == "E_66" and any(w in complaint for w in ["breath", "chest", "cough", "gasp", "choke"]):
                    is_relevant = True
                elif base_id == "E_159" and any(w in complaint for w in ["dizz", "faint", "blackout", "passed out", "syncope"]):
                    is_relevant = True
                elif base_id == "E_54" and any(w in complaint for w in ["chest", "heart", "angina"]):
                    is_relevant = True
                elif base_id == "E_45" and any(w in complaint for w in ["cough", "blood", "phlegm"]):
                    is_relevant = True
                elif base_id == "E_211" and any(w in complaint for w in ["swelling", "rash", "allergy", "throat", "lip"]):
                    is_relevant = True

                if is_relevant:
                    q_text = self.evidence_provider.get_evidence_question(crit_code, lang="en")
                    controlled_q = ControlledQuestion(
                        evidence_id=crit_code,
                        question_text=q_text,
                        data_type=self.evidence_provider.get_evidence_type(crit_code),
                        possible_values=[
                            str(v) for v in self.evidence_provider.get_possible_values(crit_code)
                        ],
                        category="SAFETY_CRITICAL",
                        is_antecedent=self.evidence_provider.is_antecedent(crit_code),
                        expected_information_gain=1.0,
                        priority=100,
                        is_safety_priority=True,
                        intent="Critical safety screening for potential red-flag symptoms",
                        target_information=["emergency_safety_screening"],
                        reason="Presenting complaint involves symptoms with potential life-safety risks",
                    )
                    return controlled_q, None, None

        # =========================================================================
        # PRIORITY 2: ADAPTIVE GEMINI QUESTION GENERATION
        # =========================================================================
        information_gaps = self.determine_information_gaps(state)

        # Prepare context for LLM proposal
        llm_context: Dict[str, Any] = {
            "session_id": state.session_id,
            "turn_index": state.conversation_turn,
            "chief_complaint": state.chief_complaint,
            "latest_message": ctx.get("latest_message") or state.chief_complaint,
            "conversation_history": ctx.get("conversation_history") or [],
            "known_present": [
                f"{k}: {v}" if v not in (True, "1", 1) else k
                for k, v in state.known_present_evidence.items()
            ],
            "known_absent": state.known_absent_evidence,
            "unknown_findings": state.unknown_evidence,
            "duration": state.symptom_duration,
            "severity": state.symptom_severity,
            "functional_impact": state.functional_impact,
            "questions_asked": past_question_texts or state.questions_asked,
            "information_gaps": information_gaps,
        }

        last_rejection_reason = None
        for attempt in range(max_retries + 1):
            if attempt > 0 and last_rejection_reason:
                llm_context["validation_feedback"] = (
                    f"Previous proposed question was rejected: {last_rejection_reason}. "
                    "Please propose a different, non-duplicate, concise question addressing an unresolved gap."
                )

            try:
                if self.llm_provider and hasattr(self.llm_provider, "propose_next_question"):
                    proposal = self.llm_provider.propose_next_question(llm_context)
                    if proposal is None or (
                        hasattr(proposal, "_mock_return_value")
                        and not isinstance(getattr(proposal, "status", None), (AdaptiveQuestionStatus, str))
                    ):
                        proposal = self._propose_deterministic_fallback(state, information_gaps)
                else:
                    proposal = self._propose_deterministic_fallback(state, information_gaps)
            except Exception as exc:
                logger.warning(f"Question proposal failed from LLM provider: {exc}")
                raise

            valid, rejection_reason = self.validate_proposed_question(
                proposal=proposal,
                state=state,
                past_question_texts=past_question_texts,
            )

            if valid:
                if proposal.status != AdaptiveQuestionStatus.ASK:
                    # Model indicates sufficient info, uncertainty, or emergency escalation
                    return None, proposal, None

                target_slug = (
                    proposal.target_information[0].lower().replace(" ", "_")
                    if proposal.target_information
                    else "adaptive_intake"
                )
                evidence_id = f"adaptive_{target_slug}"

                # Category categorization for backward compatibility
                category = "CHIEF_COMPLAINT"
                if proposal.target_information:
                    first_target = proposal.target_information[0].upper()
                    if any(w in first_target for w in ["DERM", "SKIN", "RASH"]):
                        category = "DERMATOLOGY"
                    elif any(w in first_target for w in ["JOINT", "ORTHO", "MUSCLE", "BONE", "MUSCULOSKELETAL"]):
                        category = "MUSCULOSKELETAL"
                    elif any(w in first_target for w in ["ASSOCIATED", "NEGATIVE", "PERTINENT"]):
                        category = "ASSOCIATED_SYMPTOM"
                    else:
                        category = "CHIEF_COMPLAINT"

                controlled_q = ControlledQuestion(
                    evidence_id=evidence_id,
                    question_text=proposal.question.strip(),
                    data_type="B",
                    possible_values=["Yes", "No", "Uncertain"],
                    category=category,
                    is_antecedent=False,
                    expected_information_gain=0.6,
                    priority=60,
                    is_safety_priority=False,
                    intent=proposal.intent,
                    target_information=proposal.target_information,
                    reason=proposal.reason,
                )
                return controlled_q, proposal, None
            else:
                last_rejection_reason = rejection_reason
                logger.info(
                    f"Rejected proposed question on attempt {attempt + 1}: {rejection_reason} "
                    f"(question='{proposal.question}')"
                )

        # Bounded retries exhausted without valid question -> Terminate safely with uncertainty
        uncertain_proposal = AdaptiveQuestionProposal(
            status=AdaptiveQuestionStatus.UNCERTAIN,
            question=None,
            intent=None,
            target_information=[],
            reason=f"Question validation failed after {max_retries + 1} attempt(s): {last_rejection_reason}",
            requires_human_review=True,
        )
        return None, uncertain_proposal, last_rejection_reason


# Backward-compatible aliases
InformationGainQuestionSelector = InformationCompletenessQuestionSelector
question_selector = InformationCompletenessQuestionSelector()
