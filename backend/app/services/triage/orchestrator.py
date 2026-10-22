import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.models.specialty import Specialty
from app.models.triage_answer import TriageAnswer
from app.models.triage_assessment import TriageAssessment, TriageUrgency
from app.models.triage_message import TriageMessage
from app.models.triage_session import TriageSession, TriageSessionStatus
from app.repositories.patient_repository import patient_repo
from app.repositories.specialty_repository import specialty_repo
from app.repositories.triage_repository import triage_repo
from app.schemas.patient_state import PatientState, SymptomObservation
from app.schemas.triage import (
    PreConsultationReportResponse,
    SelectedQuestionSummary,
    TriageAssessmentResponse,
    TriageConversationalTurnResponse,
)
from app.services.llm import get_llm_provider
from app.services.llm.provider import (
    EvidenceStatus,
    ExtractedEvidenceItem,
    ExtractedEvidenceResult,
    LLMProvider,
)
from app.services.triage.evidence_provider import DDXPlusEvidenceProvider, ddxplus_provider
from app.services.triage.question_selector import (
    ControlledQuestion,
    InformationCompletenessQuestionSelector,
    question_selector as default_question_selector,
)
from app.services.triage.stopping_policy import (
    TriageStoppingPolicy,
    stopping_policy as default_stopping_policy,
)
from app.services.triage_service import TriageService

logger = logging.getLogger(__name__)


class ConversationalTriageOrchestrator:
    """Orchestrates adaptive multi-turn clinical triage interactions.

    Maintains safe hard gates:
    - Free-text & structured red-flag safety screening executes deterministically.
    - LLM (Gemini) is strictly an NLP extraction and question phrasing layer.
    - Questions are strictly chosen from the approved clinical evidence ontology.
    - Conversational triage fails safely with explicit 503 if Gemini is unavailable.
    - Does NOT predict, rank, or diagnose diseases. Focuses purely on structured clinical intake.
    """

    # Critical evidence codes that immediately trip red-flag escalation
    # VERIFIED against release_evidences.json:
    # E_66: "Are you experiencing shortness of breath or difficulty breathing in a significant way?"
    # E_159: "Did you lose consciousness?"
    # E_54_@_V_180: Severe / crushing chest pain characterization
    EMERGENCY_EVIDENCE_CODES = {
        "E_54_@_V_180": "RED_FLAG_CHEST_PAIN_SEVERE",
        "E_66": "RED_FLAG_BREATHING_DIFFICULTY",
        "E_159": "RED_FLAG_LOSS_OF_CONSCIOUSNESS",
        "E_45": "RED_FLAG_SEVERE_BLEEDING",
    }

    def __init__(
        self,
        db: Session,
        llm_provider: Optional[LLMProvider] = None,
        evidence_provider: Optional[DDXPlusEvidenceProvider] = None,
        question_selector: Optional[InformationCompletenessQuestionSelector] = None,
        stopping_policy: Optional[TriageStoppingPolicy] = None,
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.evidence_provider = evidence_provider or ddxplus_provider
        if question_selector is not None:
            self.question_selector = question_selector
        else:
            self.question_selector = InformationCompletenessQuestionSelector(
                llm_provider=self.llm_provider,
                evidence_provider=self.evidence_provider,
            )
        self.stopping_policy = stopping_policy or default_stopping_policy

    @property
    def llm(self) -> LLMProvider:
        return self.llm_provider

    @llm.setter
    def llm(self, provider: LLMProvider) -> None:
        self.llm_provider = provider
        if hasattr(self, "question_selector") and self.question_selector:
            self.question_selector.llm_provider = provider

    def process_patient_turn(
        self,
        session_id: str,
        patient_message_text: str,
        actor_auth_user_id: str,
    ) -> TriageConversationalTurnResponse:
        """Processes one conversational turn:
        1. Ownership & state validation
        2. Reconstructs in-memory PatientState from history
        3. Deterministic Pre-extraction red-flag screening
        4. Structured LLM clinical evidence extraction (with active question context)
        5. Ontology evidence validation & state updating
        6. Deterministic Post-extraction safety gate
        7. Information completeness evaluation
        8. Adaptive question selection & stopping evaluation
        9. LLM empathetic conversational question phrasing
        10. Atomic database persistence
        """
        session = TriageService.get_session(self.db, session_id)
        TriageService._assert_patient_ownership(self.db, session, actor_auth_user_id)

        if session.status != TriageSessionStatus.IN_PROGRESS:
            raise InvalidStateTransitionError(
                message="Cannot send messages to a completed or escalated session",
                code="SESSION_NOT_IN_PROGRESS",
            )

        # 1. Retrieve history and reconstruct PatientState
        history = triage_repo.get_session_messages(self.db, session_id)
        turn_count = sum(1 for m in history if m.sender == "patient") + 1

        state = self._reconstruct_patient_state(session, history, turn_count)

        # Identify active controlled question from last assistant message
        active_question_text = None
        active_evidence_id = None
        for msg in reversed(history):
            if msg.sender == "assistant" and msg.extracted_evidence:
                try:
                    asst_meta = json.loads(msg.extracted_evidence)
                    if isinstance(asst_meta, dict) and "selected_evidence_id" in asst_meta:
                        active_evidence_id = asst_meta["selected_evidence_id"]
                        active_question_text = msg.content
                        break
                except Exception:
                    pass

        # 2. Step 1 Hard Safety Gate: Deterministic Pre-Extraction Screening
        raw_red_flags, uncertain_red_flags = TriageService._screen_red_flags_detailed(
            input_text=patient_message_text.lower(), answers=[]
        )
        if raw_red_flags:
            state.emergency_detected = True
            state.safety_flags.extend(raw_red_flags)
            return self._handle_emergency_escalation(
                session=session,
                state=state,
                patient_message_text=patient_message_text,
                turn_count=turn_count,
                red_flags=raw_red_flags,
            )
        if uncertain_red_flags:
            # Preserve uncertainty without silent negative or affirmative assumption
            for u_flag in uncertain_red_flags:
                u_entry = f"UNCERTAIN_{u_flag}"
                if u_entry not in state.safety_flags:
                    state.safety_flags.append(u_entry)

        # 3. Step 2: Structured Clinical Extraction (with deterministic shortcut for unambiguous replies)
        extraction_context = {
            "chief_complaint": state.chief_complaint,
            "known_present": list(state.known_present_evidence.keys()),
            "known_absent": state.known_absent_evidence,
            "active_question_text": active_question_text,
            "active_evidence_id": active_evidence_id,
            "session_id": session.id,
            "turn_index": turn_count,
        }
        deterministic_result = self._try_deterministic_answer_extraction(
            patient_message_text=patient_message_text,
            context=extraction_context,
        )
        if deterministic_result is not None:
            extracted = deterministic_result
        else:
            extracted = self._extract_evidence(patient_message_text, extraction_context)

        # 4. Step 3: Ontology Evidence Validation
        validated_evidences: List[Dict[str, Any]] = []
        for item in extracted.items:
            valid, err_msg = self.evidence_provider.validate_evidence(
                item.evidence_code, item.value
            )
            if not valid:
                logger.info(f"Filtered invalid clinical evidence: {item.evidence_code} ({err_msg})")
                continue

            norm_code = item.evidence_code
            ev_meta = self.evidence_provider.get_evidence(norm_code)
            ev_name = ev_meta.get("name", "") if ev_meta else norm_code

            validated_evidences.append({
                "evidence_code": norm_code,
                "status": item.status.value,
                "value": item.value,
                "confidence": item.confidence,
            })

            if norm_code == "adaptive_functional_impact":
                if item.status == EvidenceStatus.PRESENT:
                    state.functional_impact = str(item.value) if item.value is not None else "Significant interference with daily activities or sleep"
                elif item.status == EvidenceStatus.ABSENT:
                    state.functional_impact = str(item.value) if item.value is not None else "No significant functional impact reported"

            if item.status == EvidenceStatus.PRESENT:
                state.mark_present(norm_code, item.value or True, name=ev_name)
            elif item.status == EvidenceStatus.ABSENT:
                state.mark_absent(norm_code, name=ev_name)
            elif item.status == EvidenceStatus.UNKNOWN:
                state.mark_unknown(norm_code, name=ev_name)

        if extracted.duration:
            state.symptom_duration = extracted.duration
        if extracted.severity:
            state.symptom_severity = extracted.severity
        if extracted.measurements:
            for m in extracted.measurements:
                state.measurements[m.name] = m.value
        if getattr(extracted, "declined_to_continue", False):
            state.declined_to_continue = True
        if getattr(extracted, "corrections", None):
            for corr in extracted.corrections:
                state.record_correction(corr)

        # 5. Step 4 Hard Safety Gate: Deterministic Post-Extraction Screening
        # Re-runs immediately upon any finding or patient correction
        post_flags = self._screen_post_extraction_flags(state)
        if post_flags:
            state.emergency_detected = True
            state.safety_flags.extend(post_flags)
            return self._handle_emergency_escalation(
                session=session,
                state=state,
                patient_message_text=patient_message_text,
                turn_count=turn_count,
                red_flags=post_flags,
                extracted_data=validated_evidences,
            )

        # 6. Step 5: Information Completeness Scoring
        state.completeness_score = self.question_selector.compute_completeness_score(state)

        # 6b. Step 5b: Pre-question Stopping Evaluation
        # Avoid unnecessary LLM question proposal if interaction terminal conditions are already reached
        pre_stop, pre_reason, pre_esc = self.stopping_policy.should_stop_pre_question(state)
        if pre_stop:
            return self._finalize_session(
                session=session,
                state=state,
                patient_message_text=patient_message_text,
                turn_count=turn_count,
                stop_reason=str(pre_reason),
                needs_escalation=pre_esc,
                extracted_data=validated_evidences,
            )

        # 7. Step 6: Select Adaptive Next Question
        past_question_texts = [
            msg.content for msg in history if msg.sender == "assistant"
        ]
        selector_context = {
            "latest_message": patient_message_text,
            "past_question_texts": past_question_texts,
            "conversation_history": [
                {"sender": m.sender, "content": m.content} for m in history
            ] + [{"sender": "patient", "content": patient_message_text}],
        }
        next_question, proposal, rejection_reason = self.question_selector.select_next_adaptive_question(
            state=state, context=selector_context
        )

        # 8. Step 7: Evaluate Stopping Policy
        should_stop, stop_reason, needs_esc = self.stopping_policy.should_stop(
            state=state, next_question=next_question, proposal=proposal
        )

        if should_stop or next_question is None:
            # Finalize session and route to appropriate specialty
            return self._finalize_session(
                session=session,
                state=state,
                patient_message_text=patient_message_text,
                turn_count=turn_count,
                stop_reason=str(stop_reason),
                needs_escalation=needs_esc,
                extracted_data=validated_evidences,
            )

        # 9. Step 8: Adaptive Clinical Question
        selected_question_text = next_question.question_text

        # 10. Step 9: Atomic Database Persistence for Active Turn
        persistence_payload = {
            "items": validated_evidences,
            "duration": state.symptom_duration,
            "severity": state.symptom_severity,
            "functional_impact": state.functional_impact,
            "corrections": state.corrections,
            "declined": state.declined_to_continue,
        }
        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="patient",
            content=patient_message_text,
            turn_index=turn_count,
            extracted_evidence=json.dumps(persistence_payload),
        )

        asst_metadata = {
            "selected_evidence_id": next_question.evidence_id,
            "intent": next_question.intent,
            "target_information": next_question.target_information,
            "reason": next_question.reason,
            "information_gain": next_question.expected_information_gain,
        }
        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="assistant",
            content=selected_question_text,
            turn_index=turn_count,
            extracted_evidence=json.dumps(asst_metadata),
        )

        state.record_question_asked(next_question.evidence_id)

        return TriageConversationalTurnResponse(
            session_id=session.id,
            conversation_turn=turn_count,
            is_complete=False,
            stop_reason=None,
            patient_message=patient_message_text,
            assistant_message=selected_question_text,
            extracted_evidences=validated_evidences,
            selected_question=SelectedQuestionSummary(
                evidence_id=next_question.evidence_id,
                question_text=next_question.question_text,
                data_type=next_question.data_type,
                possible_values=next_question.possible_values,
                category=next_question.category,
                is_antecedent=next_question.is_antecedent,
                expected_information_gain=next_question.expected_information_gain,
            ),
            completeness_score=state.completeness_score,
            uncertainty_score=round(1.0 - state.completeness_score, 2),
            safety_flags=state.safety_flags,
            assessment=None,
        )

    def _reconstruct_patient_state(
        self,
        session: TriageSession,
        history: List[TriageMessage],
        turn_count: int,
    ) -> PatientState:
        state = PatientState(
            session_id=session.id,
            patient_id=session.patient_id,
            conversation_turn=turn_count,
            chief_complaint=session.confirmed_input or session.original_input,
        )

        # Seed from confirmed original input if no messages yet
        for msg in history:
            if msg.sender == "patient" and msg.extracted_evidence:
                try:
                    payload = json.loads(msg.extracted_evidence)
                    items = payload
                    if isinstance(payload, dict):
                        items = payload.get("items", [])
                        if payload.get("duration"):
                            state.symptom_duration = payload.get("duration")
                        if payload.get("severity") is not None:
                            state.symptom_severity = payload.get("severity")
                        if payload.get("functional_impact"):
                            state.functional_impact = payload.get("functional_impact")
                        if payload.get("declined"):
                            state.declined_to_continue = True
                        if payload.get("corrections"):
                            for corr in payload.get("corrections"):
                                state.record_correction(corr)
                    elif isinstance(payload, list):
                        items = payload
                    if isinstance(items, list):
                        for item in items:
                            code = item.get("evidence_code")
                            st = item.get("status")
                            val = item.get("value", True)
                            msg_id_str = str(msg.id) if hasattr(msg, "id") and msg.id else None
                            if code == "adaptive_functional_impact":
                                if st == "PRESENT":
                                    state.functional_impact = str(val) if val is not None else "Significant interference with daily activities or sleep"
                                elif st == "ABSENT":
                                    state.functional_impact = str(val) if val is not None else "No significant functional impact reported"
                            if code and st == "PRESENT":
                                state.mark_present(code, val, source_message_id=msg_id_str)
                            elif code and st == "ABSENT":
                                state.mark_absent(code, source_message_id=msg_id_str)
                            elif code and st == "UNKNOWN":
                                state.mark_unknown(code, source_message_id=msg_id_str)
                except Exception as exc:
                    logger.warning(f"Failed to replay message evidence: {exc}")

            elif msg.sender == "assistant" and msg.extracted_evidence:
                try:
                    asst_meta = json.loads(msg.extracted_evidence)
                    if isinstance(asst_meta, dict) and "selected_evidence_id" in asst_meta:
                        state.record_question_asked(asst_meta["selected_evidence_id"])
                except Exception as exc:
                    logger.warning(f"Failed to replay assistant question: {exc}")

        return state

    def _try_deterministic_answer_extraction(
        self,
        patient_message_text: str,
        context: Optional[Dict[str, Any]],
    ) -> Optional[ExtractedEvidenceResult]:
        """Attempts deterministic extraction of unambiguous affirmative/negative replies to an active question.

        Bypasses Gemini API request ONLY when:
        1. An active controlled question exists.
        2. The question maps to exactly one known evidence identifier in the clinical ontology.
        3. The answer is an exact, unambiguous affirmative or negative.
        4. The answer contains no additional symptom, duration, severity, or narrative information.
        5. Emergency pre-screening has already cleared the text.
        """
        if not context:
            return None

        active_evidence_id = context.get("active_evidence_id")
        active_question_text = context.get("active_question_text")

        # Requirement 1: Active controlled question and evidence must exist
        if not active_evidence_id or not active_question_text:
            return None

        # Requirement 2: Question must map to exactly one known evidence identifier
        if not isinstance(active_evidence_id, str) or not active_evidence_id.strip():
            return None

        base_code = active_evidence_id.split("_@_")[0]
        ev_meta = self.evidence_provider.get_evidence(active_evidence_id) or self.evidence_provider.get_evidence(base_code)
        if not ev_meta:
            return None

        # Do not use shortcut if question text is compound or asks multiple questions
        if active_question_text.count("?") > 1:
            return None

        raw = patient_message_text.strip()
        cleaned = raw.lower().strip(".!?, \t\r\n")

        # Disallow digits (severity or duration like "8/10", "3 days")
        if any(char.isdigit() for char in raw):
            return None

        # Disallow connectors, correction markers, or symptom words indicating additional information
        disallowed_clause_markers = {
            "but", "and", "also", "except", "with", "however", "although", "plus",
            "besides", "because", "since", "felt", "feel", "feeling", "started",
            "pain", "severe", "fever", "cough", "vomit", "vomiting", "nausea",
            "dizzy", "dizziness", "rash", "bleeding", "ache", "swelling", "days", "hours",
            "trouble", "shortness", "headache", "chest", "actually", "earlier", "correction",
            "mistake", "wait", "instead", "changed", "mean",
        }
        words = re.findall(r"\b\w+\b", cleaned)
        if any(w in disallowed_clause_markers for w in words):
            return None

        # Exact unambiguous affirmatives
        EXACT_AFFIRMATIVES = {
            "yes", "yeah", "yep", "yup", "definitely", "sure", "correct",
            "true", "i do", "i have", "affirmative",
        }

        # Exact unambiguous negatives
        EXACT_NEGATIVES = {
            "no", "nope", "nah", "negative", "i don't", "i do not", "none",
            "not really", "never", "i don't have it", "i do not have it",
        }

        is_affirmative = cleaned in EXACT_AFFIRMATIVES
        is_negative = cleaned in EXACT_NEGATIVES

        # Must be strictly one or the other. Ambiguous answers like "not sure", "maybe", "idk" return None
        if not is_affirmative and not is_negative:
            return None

        # Validate semantic polarity support for the active evidence question
        if is_affirmative and not ev_meta.get("allow_affirmative", True):
            logger.info(
                f"Deterministic shortcut bypassed for evidence '{active_evidence_id}': "
                f"affirmative reply requires detailed LLM extraction."
            )
            return None

        if is_negative and not ev_meta.get("allow_negative", True):
            logger.info(
                f"Deterministic shortcut bypassed for evidence '{active_evidence_id}': "
                f"negative reply requires detailed LLM extraction."
            )
            return None

        if is_affirmative:
            target_status = EvidenceStatus.PRESENT
            target_value = ev_meta.get("affirmative_value", True)
        else:
            target_status = EvidenceStatus.ABSENT
            target_value = ev_meta.get("negative_value", False)

        logger.info(
            f"Deterministic extraction applied for evidence '{active_evidence_id}': "
            f"reply '{raw}' -> status={target_status.value} value={target_value} (Gemini bypassed)"
        )

        return ExtractedEvidenceResult(
            chief_complaint=context.get("chief_complaint") or "",
            duration=None,
            severity=None,
            measurements=[],
            items=[
                ExtractedEvidenceItem(
                    evidence_code=active_evidence_id,
                    status=target_status,
                    value=target_value,
                    confidence=1.0,
                )
            ],
        )

    def _extract_evidence(
        self, message_text: str, context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Invokes the runtime LLMProvider (Gemini) directly.

        Fails fast with TriageLLMUnavailableError (HTTP 503) if Gemini is unavailable.
        No MockLLM fallback is permitted.
        """
        return self.llm_provider.extract_patient_evidence(
            message=message_text,
            context=context,
        )

    def _phrase_question(
        self,
        controlled_question: str,
        evidence_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Returns the controlled clinical question directly from the ontology.

        Eliminates unnecessary external LLM request while strictly preserving
        clinically reviewed wording.
        """
        return controlled_question

    def _screen_post_extraction_flags(self, state: PatientState) -> List[str]:
        flags: List[str] = []
        for ev_code in state.known_present_evidence.keys():
            base_id = ev_code.split("_@_")[0]
            if ev_code in self.EMERGENCY_EVIDENCE_CODES:
                flags.append(self.EMERGENCY_EVIDENCE_CODES[ev_code])
            elif base_id in self.EMERGENCY_EVIDENCE_CODES:
                flags.append(self.EMERGENCY_EVIDENCE_CODES[base_id])
        return list(set(flags))

    def _handle_emergency_escalation(
        self,
        session: TriageSession,
        state: PatientState,
        patient_message_text: str,
        turn_count: int,
        red_flags: List[str],
        extracted_data: Optional[List[Dict[str, Any]]] = None,
    ) -> TriageConversationalTurnResponse:
        now = datetime.now(timezone.utc)
        session.status = TriageSessionStatus.ESCALATED
        session.completed_at = now

        rationale = (
            f"Emergency red-flag indicators detected: [{', '.join(red_flags)}]. "
            "Immediate medical escalation is required."
        )
        guidance = (
            "Emergency warning signs were detected. Seek urgent medical attention "
            "or proceed to the nearest emergency department immediately."
        )

        assessment = TriageAssessment(
            triage_session_id=session.id,
            urgency=TriageUrgency.HIGH,
            confidence=1.0,
            needs_escalation=True,
            red_flag_detected=True,
            red_flag_codes=red_flags,
            recommended_specialty_id=None,
            rationale=rationale,
            assessed_at=now,
        )
        self.db.add(assessment)
        self.db.add(session)

        # Assistant emergency message
        assistant_emergency_msg = (
            "⚠️ Immediate medical attention required: We detected symptoms indicating a potential medical emergency. "
            "Please call emergency services (e.g., 911) or proceed to the nearest emergency department immediately."
        )

        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="patient",
            content=patient_message_text,
            turn_index=turn_count,
            extracted_evidence=json.dumps(extracted_data or {"red_flags": red_flags}),
        )

        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="assistant",
            content=assistant_emergency_msg,
            turn_index=turn_count,
            extracted_evidence=json.dumps({"escalation_reason": "EMERGENCY_RED_FLAG"}),
        )

        self.db.commit()
        self.db.refresh(assessment)

        return TriageConversationalTurnResponse(
            session_id=session.id,
            conversation_turn=turn_count,
            is_complete=True,
            stop_reason="EMERGENCY_RED_FLAG",
            patient_message=patient_message_text,
            assistant_message=assistant_emergency_msg,
            extracted_evidences=extracted_data or [],
            selected_question=None,
            completeness_score=state.completeness_score,
            uncertainty_score=0.0,
            safety_flags=red_flags,
            assessment=TriageAssessmentResponse(
                id=assessment.id,
                triage_session_id=assessment.triage_session_id,
                urgency=assessment.urgency,
                confidence=assessment.confidence,
                needs_escalation=assessment.needs_escalation,
                red_flag_detected=assessment.red_flag_detected,
                red_flag_codes=assessment.red_flag_codes,
                recommended_specialty_id=None,
                recommended_specialty_name=None,
                rationale=assessment.rationale,
                guidance=guidance,
                assessed_at=assessment.assessed_at,
            ),
        )

    @staticmethod
    def _is_keyword_negated_in_text(text: str, keyword: str) -> bool:
        """Determines if a keyword is explicitly negated within its local clause.

        Prevents negated words (e.g. 'no severe pain', 'without vomiting') from
        inflating acuity scores.
        """
        if not text or not keyword:
            return False
        clauses = re.split(r"[.!?;,]|\bbut\b|\bhowever\b|\balthough\b|\bexcept\b", text.lower())
        for clause in clauses:
            if keyword in clause:
                tokens = clause.strip().split()
                neg_indices = [
                    i for i, t in enumerate(tokens)
                    if t in {"no", "not", "without", "never", "denies", "denied", "negative", "none", "don't", "dont", "didn't", "didnt"}
                ]
                kw_indices = [i for i, t in enumerate(tokens) if keyword in t]
                for kw_i in kw_indices:
                    for neg_i in neg_indices:
                        if 0 < (kw_i - neg_i) <= 5:
                            return True
        return False

    def _calculate_acuity_and_urgency(
        self, state: PatientState, stop_reason: str = ""
    ) -> Tuple[TriageUrgency, float, str]:
        """Calculates clinical urgency and confidence from patient presentation and reported severity.

        Does NOT predict diseases or use disease severity ratings.
        """
        # Deterministic emergency override
        if state.emergency_detected:
            return TriageUrgency.HIGH, 1.0, "Immediate emergency red-flag detected during clinical intake."

        score = 0
        input_text = (state.chief_complaint or "").lower()

        # 1. Non-negated symptom keywords in chief complaint
        symptom_kws = ["fever", "pain", "swelling", "vomiting", "dizziness"]
        active_symptom_kws = [
            w for w in symptom_kws
            if w in input_text and not self._is_keyword_negated_in_text(input_text, w)
        ]
        if active_symptom_kws:
            score += 2

        # 2. Non-negated severity keywords in chief complaint
        severity_kws = ["severe", "intense", "worsening", "unbearable", "acute"]
        active_sev_kws = [
            w for w in severity_kws
            if w in input_text and not self._is_keyword_negated_in_text(input_text, w)
        ]
        if active_sev_kws:
            score += 3

        # 3. Patient-reported numerical severity (1-10)
        reported_sev = (
            state.patient_reported_severity
            if state.patient_reported_severity is not None
            else state.symptom_severity
        )
        if reported_sev is not None:
            if reported_sev >= 8:
                score += 5
            elif reported_sev >= 5:
                score += 2

        # 4. Present symptoms count and category weights (deduplicated by base evidence ID)
        # Group by base code to prevent double-counting compound subcodes (e.g. E_54 and E_54_@_V_180)
        base_codes = {ev_code.split("_@_")[0] for ev_code in state.known_present_evidence.keys()}
        for base_code in base_codes:
            if any(base_code.startswith(prefix) for prefix in ["E_53", "E_124", "E_181"]):
                score += 3  # Cardio/respiratory symptom
            else:
                score += 1

        # 5. Determine Urgency tier (preserving documented system thresholds)
        if score >= 5:
            urgency = TriageUrgency.HIGH
            rationale_summary = "Reported symptom severity and acuity factors indicate elevated clinical urgency."
        elif score >= 2:
            urgency = TriageUrgency.MODERATE
            rationale_summary = "Presenting symptoms indicate moderate clinical urgency requiring timely outpatient evaluation."
        else:
            urgency = TriageUrgency.LOW
            rationale_summary = "Reported symptoms indicate standard outpatient presentation suitable for routine scheduling."

        # Confidence: directly reflects interview completeness score
        confidence = max(0.40, min(0.95, state.completeness_score))

        return urgency, round(confidence, 2), rationale_summary

    def _finalize_session(
        self,
        session: TriageSession,
        state: PatientState,
        patient_message_text: str,
        turn_count: int,
        stop_reason: str,
        needs_escalation: bool,
        extracted_data: List[Dict[str, Any]],
    ) -> TriageConversationalTurnResponse:
        now = datetime.now(timezone.utc)

        # 1. Determine Urgency & Confidence (Non-disease clinical acuity)
        urgency, confidence, rationale_summary = self._calculate_acuity_and_urgency(state, stop_reason)

        is_uncertain = (
            stop_reason in ("UNCERTAINTY_HUMAN_REVIEW", "ESCALATE_UNCERTAIN")
            or state.requires_human_review
            or needs_escalation
            or confidence < TriageService.CONFIDENCE_THRESHOLD
        )

        specialty = self._determine_specialty(state)
        spec_name = specialty.name if specialty else "General Medicine"

        if stop_reason == "EMERGENCY_RED_FLAG":
            session.status = TriageSessionStatus.ESCALATED
            needs_escalation = True
            guidance = (
                "Emergency warning signs were detected. Seek urgent medical attention "
                "or proceed to the nearest emergency department immediately."
            )
            assistant_summary_msg = (
                "⚠️ Immediate medical attention required: Potential emergency symptoms were detected. "
                "Please contact emergency services or proceed to the nearest emergency department immediately."
            )
        elif is_uncertain:
            session.status = TriageSessionStatus.ESCALATED
            needs_escalation = True
            guidance = (
                "Some clinical presentation factors remain uncertain or require closer evaluation. "
                "In-person medical review is advised to ensure safe care navigation."
            )
            assistant_summary_msg = (
                f"Thank you for sharing your symptoms. Because some aspects of your presentation require "
                f"closer medical evaluation, we have routed you to {spec_name} for direct clinical review. "
                f"{guidance}"
            )
        elif stop_reason == "PATIENT_DECLINED":
            session.status = TriageSessionStatus.COMPLETED
            guidance = (
                "You requested to conclude the intake questions. Routine outpatient care navigation has been provided."
            )
            assistant_summary_msg = (
                f"We have noted your request to conclude the questions. Based on the information gathered so far, "
                f"we have routed your care to {spec_name}. {guidance}"
            )
        elif stop_reason in ("INTERACTION_LIMIT_REACHED", "MAX_CONVERSATION_TURNS_REACHED"):
            session.status = TriageSessionStatus.COMPLETED
            guidance = (
                "The conversational intake boundary was reached. In-person clinical consultation is recommended."
            )
            assistant_summary_msg = (
                f"We have reached the conversation limit for this intake session. Based on your reported symptoms, "
                f"we have routed you to {spec_name} for direct physician consultation."
            )
        elif stop_reason in ("INSUFFICIENT_INFORMATION", "EXHAUSTED_DISCRIMINATIVE_QUESTIONS") and needs_escalation:
            session.status = TriageSessionStatus.ESCALATED
            guidance = (
                "Intake concluded with limited clinical information. Comprehensive in-person evaluation is recommended."
            )
            assistant_summary_msg = (
                f"Thank you for your responses. Because limited clinical detail was available, "
                f"we have routed you to {spec_name} for a full in-person evaluation."
            )
        else:
            session.status = TriageSessionStatus.COMPLETED
            if urgency == TriageUrgency.HIGH:
                guidance = (
                    "Based on your responses, prompt outpatient clinical evaluation is recommended. "
                    "Please schedule an urgent appointment with the appropriate clinical specialty. "
                    "Absence of red-flag symptoms does not guarantee safety; if your condition worsens, seek immediate emergency care."
                )
            elif urgency == TriageUrgency.MODERATE:
                guidance = (
                    "Based on your responses, timely outpatient clinical evaluation is recommended. "
                    "Please schedule an appointment with the appropriate clinical specialty."
                )
            else:
                guidance = (
                    "Based on your responses, routine care navigation is recommended. "
                    "Please schedule an appointment with the appropriate clinical specialty."
                )
            assistant_summary_msg = (
                f"Thank you for answering our clinical intake questions. Based on the symptoms and information "
                f"you provided, we have routed your care to {spec_name} with {urgency.value} urgency. "
                f"{guidance}"
            )

        session.completed_at = now

        # 3. Build Physician Pre-Consultation Intake Report
        full_report = self._build_pre_consultation_report(
            session=session,
            state=state,
            urgency=urgency,
            specialty_name=spec_name,
            guidance=guidance,
        )

        # 4. Create Assessment
        assessment = TriageAssessment(
            triage_session_id=session.id,
            urgency=urgency,
            confidence=confidence,
            needs_escalation=needs_escalation,
            red_flag_detected=False,
            red_flag_codes=[],
            recommended_specialty_id=specialty.id if specialty else None,
            rationale=full_report,
            assessed_at=now,
        )
        self.db.add(assessment)
        self.db.add(session)

        # 5. Generate Safe Patient-Facing Completion Message (Zero Disease Claims)
        assistant_summary_msg = (
            f"Thank you for answering our clinical intake questions. Based on the symptoms and information "
            f"you provided, we have routed your care to {spec_name} with {urgency.value} urgency. "
            f"{guidance}"
        )

        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="patient",
            content=patient_message_text,
            turn_index=turn_count,
            extracted_evidence=json.dumps(extracted_data),
        )

        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="assistant",
            content=assistant_summary_msg,
            turn_index=turn_count,
            extracted_evidence=json.dumps({
                "stop_reason": stop_reason,
                "urgency": urgency.value,
                "specialty": spec_name,
            }),
        )

        self.db.commit()
        self.db.refresh(assessment)

        return TriageConversationalTurnResponse(
            session_id=session.id,
            conversation_turn=turn_count,
            is_complete=True,
            stop_reason=stop_reason,
            patient_message=patient_message_text,
            assistant_message=assistant_summary_msg,
            extracted_evidences=extracted_data,
            selected_question=None,
            completeness_score=state.completeness_score,
            uncertainty_score=round(1.0 - state.completeness_score, 2),
            safety_flags=state.safety_flags,
            assessment=TriageAssessmentResponse(
                id=assessment.id,
                triage_session_id=assessment.triage_session_id,
                urgency=assessment.urgency,
                confidence=assessment.confidence,
                needs_escalation=assessment.needs_escalation,
                red_flag_detected=assessment.red_flag_detected,
                red_flag_codes=assessment.red_flag_codes,
                recommended_specialty_id=specialty.id if specialty else None,
                recommended_specialty_name=spec_name,
                rationale=assessment.rationale,
                guidance=guidance,
                assessed_at=assessment.assessed_at,
            ),
        )

    def _determine_specialty(self, state: PatientState) -> Optional[Specialty]:
        """Maps presenting symptoms and chief complaint directly to a database Specialty.

        Does NOT match disease names. Operates on anatomical and clinical presentation categories.
        """
        complaint = (state.chief_complaint or "").lower()
        present_codes = set(state.known_present_evidence.keys())

        def word_match(words: List[str]) -> bool:
            return any(bool(re.search(rf"\b{re.escape(w)}\b", complaint)) for w in words)

        # 1. Cardiology (Chest tightness, palpitations, heart)
        cardio_codes = {"E_53", "E_124"}
        cardio_words = ["heart", "cardio", "palpitation", "palpitations", "chest tightness"]
        if any(c in present_codes or c.split("_@_")[0] in present_codes for c in cardio_codes) or word_match(cardio_words):
            spec = specialty_repo.get_by_code(self.db, "CARDIO") or specialty_repo.get_by_name(self.db, "Cardiology")
            if spec:
                return spec

        # 2. Dermatological (Skin, rash, itching, hives, eczema)
        derm_codes = {"E_170", "E_171", "E_116", "E_211"}
        derm_words = ["rash", "skin", "itch", "itching", "mole", "acne", "eczema", "hive", "hives", "lesion", "peel", "blister", "bite"]
        if any(c in present_codes or c.split("_@_")[0] in present_codes for c in derm_codes) or word_match(derm_words):
            spec = specialty_repo.get_by_code(self.db, "DERM") or specialty_repo.get_by_name(self.db, "Dermatology")
            if spec:
                return spec

        # 3. Musculoskeletal / Orthopedics (Joints, bones, back, sprains)
        ortho_codes = {"E_155", "E_130", "E_131"}
        ortho_words = ["joint", "joints", "bone", "bones", "knee", "back", "ankle", "sprain", "fracture", "stiff", "stiffness", "neck", "shoulder", "hip", "ligament"]
        if any(c in present_codes or c.split("_@_")[0] in present_codes for c in ortho_codes) or word_match(ortho_words):
            spec = specialty_repo.get_by_code(self.db, "ORTHO") or specialty_repo.get_by_name(self.db, "Orthopedics")
            if spec:
                return spec

        # 4. ENT (Ear, nose, throat, sinus)
        ent_codes = {"E_173", "E_77"}
        ent_words = ["ear", "ears", "throat", "sinus", "nasal", "nose", "tonsil", "tonsils", "swallow", "hoarse", "hearing"]
        if any(c in present_codes or c.split("_@_")[0] in present_codes for c in ent_codes) or word_match(ent_words):
            spec = specialty_repo.get_by_code(self.db, "ENT") or specialty_repo.get_by_name(self.db, "ENT")
            if spec:
                return spec

        # 5. Default / Fallback to General Medicine
        return (
            specialty_repo.get_by_code(self.db, "GEN")
            or specialty_repo.get_by_code(self.db, "GEN-MED")
            or specialty_repo.get_by_name(self.db, "General Medicine")
            or self.db.query(Specialty).filter(Specialty.is_active.is_(True)).first()
        )

    def _build_pre_consultation_report(
        self,
        session: TriageSession,
        state: PatientState,
        urgency: TriageUrgency,
        specialty_name: str,
        guidance: str,
    ) -> str:
        """Constructs an objective, structured Pre-Consultation Intake Report for the physician.

        Contains NO disease predictions, NO differential diagnoses, and NO speculative pathology.
        Distinguishes PRESENT symptoms, ABSENT/DENIED negatives, duration, severity, and safety status.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            "=" * 60,
            "PRE-CONSULTATION INTAKE SUMMARY",
            "=" * 60,
            f"Session ID: {session.id}",
            f"Patient ID: {session.patient_id}",
            f"Date / Time: {now_str}",
            "",
            f"Chief Complaint:\n  {state.chief_complaint or 'Not specified'}",
            "",
            f"Duration:\n  {state.symptom_duration or 'Not reported'}",
            "",
            f"Patient-Reported Severity (1-10):\n  {state.patient_reported_severity if state.patient_reported_severity is not None else 'Not reported'}",
            "",
            "Present Symptoms (Affirmed by Patient):",
        ]

        if state.known_present_evidence:
            for code, val in state.known_present_evidence.items():
                ev_name = self.evidence_provider.get_evidence_name(code)
                val_str = f" (Value: {val})" if val not in (True, 1, "1") else ""
                lines.append(f"  • [{code}] {ev_name}{val_str}")
        else:
            lines.append("  (None specifically affirmed beyond chief complaint)")

        lines.extend([
            "",
            "Explicitly Denied / Pertinent Negatives:",
        ])
        if state.known_absent_evidence:
            for code in sorted(state.known_absent_evidence):
                ev_name = self.evidence_provider.get_evidence_name(code)
                lines.append(f"  • [{code}] {ev_name} (DENIED)")
        else:
            lines.append("  (None recorded)")

        lines.extend([
            "",
            "Safety Screening:",
        ])
        if state.safety_screenings:
            for flag, outcome in state.safety_screenings.items():
                lines.append(f"  • {flag}: {outcome}")
        else:
            lines.append("  • Red Flag Screening: Negative (No immediate life-threatening emergency identified during intake)")

        lines.extend([
            "",
            "Triage & Care Navigation:",
            f"  Urgency Level: {urgency.value}",
            f"  Recommended Specialty: {specialty_name}",
            f"  Intake Completeness: {int(state.completeness_score * 100)}%",
            f"  Clinical Guidance: {guidance}",
            "",
            "Conversation Summary:",
            f"  Patient presented with chief complaint '{state.chief_complaint or 'unspecified symptoms'}'. "
            f"Completed {state.conversation_turn} structured intake turns with {len(state.known_present_evidence)} affirmed symptoms "
            f"and {len(state.known_absent_evidence)} pertinent negatives documented.",
            "",
            "NOTICE:",
            "  This summary is based strictly on patient-reported intake information.",
            "  It is not a diagnosis. Final clinical assessment and diagnostic decisions",
            "  remain the responsibility of the treating physician.",
            "=" * 60,
        ])
        return "\n".join(lines)

    def get_pre_consultation_report(self, session_id: str) -> PreConsultationReportResponse:
        """Generates a structured PreConsultationReportResponse for an intake session."""
        session = triage_repo.get_session(self.db, session_id)
        if not session:
            raise NotFoundError(
                message=f"Triage session '{session_id}' not found",
                code="TRIAGE_SESSION_NOT_FOUND",
            )
        assessment = (
            self.db.query(TriageAssessment)
            .filter(TriageAssessment.triage_session_id == session.id)
            .first()
        )
        messages = triage_repo.get_session_messages(self.db, session.id)
        turn_count = sum(1 for m in messages if m.sender == "patient")
        state = self._reconstruct_patient_state(session, messages, turn_count)

        present_list = []
        for code, val in state.known_present_evidence.items():
            name = self.evidence_provider.get_evidence_name(code)
            val_str = f" ({val})" if val not in (True, 1, "1") else ""
            present_list.append(f"{name}{val_str}")

        absent_list = [
            f"{self.evidence_provider.get_evidence_name(code)} (Denied)"
            for code in sorted(state.known_absent_evidence)
        ]

        urgency = assessment.urgency if assessment else TriageUrgency.LOW
        spec_id = assessment.recommended_specialty_id if assessment else None
        spec_name = (
            assessment.recommended_specialty.name
            if (assessment and assessment.recommended_specialty)
            else "General Medicine"
        )
        assessed_at = assessment.assessed_at if assessment else None
        formatted_report = assessment.rationale if assessment else self._build_pre_consultation_report(
            session=session,
            state=state,
            urgency=urgency,
            specialty_name=spec_name,
            guidance="In-progress intake review.",
        )

        return PreConsultationReportResponse(
            session_id=session.id,
            patient_id=session.patient_id,
            assessed_at=assessed_at,
            urgency=urgency,
            recommended_specialty_id=spec_id,
            recommended_specialty_name=spec_name,
            chief_complaint=state.chief_complaint or "Unspecified complaint",
            symptom_duration=state.symptom_duration,
            patient_reported_severity=state.patient_reported_severity,
            present_symptoms=present_list,
            absent_symptoms=absent_list,
            unknown_symptoms=[],
            safety_screenings=state.safety_screenings or {"Emergency Red Flag Screening": "Negative"},
            conversation_summary=(
                f"Patient reported chief complaint: '{state.chief_complaint or 'unspecified'}'. "
                f"Collected {len(state.known_present_evidence)} symptoms and {len(state.known_absent_evidence)} pertinent negatives."
            ),
            formatted_report=formatted_report,
        )

