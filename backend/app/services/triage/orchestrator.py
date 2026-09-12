import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
from app.schemas.patient_state import CandidateCondition, PatientState
from app.schemas.triage import (
    CandidateConditionSummary,
    SelectedQuestionSummary,
    TriageAssessmentResponse,
    TriageConversationalTurnResponse,
)
from app.services.llm import get_llm_provider
from app.services.llm.mock import MockLLMProvider
from app.services.llm.provider import EvidenceStatus, LLMProvider
from app.services.triage.evidence_provider import DDXPlusEvidenceProvider, ddxplus_provider
from app.services.triage.question_selector import (
    ControlledQuestion,
    InformationGainQuestionSelector,
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
    - LLM is strictly an NLP extraction and question phrasing layer.
    - Questions are strictly chosen from the DDXPlus controlled clinical ontology.
    - Full fallback to rule-based mock extractor if LLM is unavailable.
    """

    # Critical DDXPlus evidence codes that immediately trip red-flag escalation
    EMERGENCY_EVIDENCE_CODES = {
        "E_54_@_V_180": "RED_FLAG_CHEST_PAIN_SEVERE",
        "E_88": "RED_FLAG_BREATHING_DIFFICULTY",
        "E_201": "RED_FLAG_LOSS_OF_CONSCIOUSNESS",
    }

    def __init__(
        self,
        db: Session,
        llm_provider: Optional[LLMProvider] = None,
        evidence_provider: Optional[DDXPlusEvidenceProvider] = None,
        question_selector: Optional[InformationGainQuestionSelector] = None,
        stopping_policy: Optional[TriageStoppingPolicy] = None,
    ):
        self.db = db
        self.llm_provider = llm_provider or get_llm_provider()
        self.evidence_provider = evidence_provider or ddxplus_provider
        self.question_selector = question_selector or default_question_selector
        self.stopping_policy = stopping_policy or default_stopping_policy

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
        4. Structured LLM clinical evidence extraction (with safe fallback)
        5. DDXPlus ontology validation
        6. Deterministic Post-extraction safety gate
        7. Dynamic differential diagnosis update & Shannon entropy reduction
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

        # 2. Step 1 Hard Safety Gate: Deterministic Pre-Extraction Screening
        raw_red_flags = TriageService._screen_red_flags(
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

        # 3. Step 2: Structured Clinical Extraction via LLM (with Mock fallback)
        extracted = self._extract_evidence_safe(patient_message_text, state)

        # 4. Step 3: DDXPlus Ontology Validation
        validated_evidences: List[Dict[str, Any]] = []
        for item in extracted.items:
            valid, err_msg = self.evidence_provider.validate_evidence(
                item.evidence_code, item.value
            )
            if not valid:
                logger.info(f"Filtered invalid clinical evidence: {item.evidence_code} ({err_msg})")
                continue

            norm_code = item.evidence_code
            validated_evidences.append({
                "evidence_code": norm_code,
                "status": item.status.value,
                "value": item.value,
                "confidence": item.confidence,
            })

            if item.status == EvidenceStatus.PRESENT:
                state.mark_present(norm_code, item.value or True)
            elif item.status == EvidenceStatus.ABSENT:
                state.mark_absent(norm_code)
            elif item.status == EvidenceStatus.UNKNOWN:
                state.mark_unknown(norm_code)

        if extracted.duration:
            state.symptom_duration = extracted.duration
        if extracted.severity:
            state.symptom_severity = extracted.severity

        # 5. Step 4 Hard Safety Gate: Deterministic Post-Extraction Screening
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

        # 6. Step 5: Dynamic Differential Diagnosis & Entropy
        candidates, entropy = self.question_selector.compute_candidate_distribution(
            known_present=state.known_present_evidence,
            known_absent=state.known_absent_evidence,
        )
        state.candidate_conditions = candidates
        state.uncertainty_score = entropy

        # 7. Step 6: Select Adaptive Next Question
        next_question = self.question_selector.select_next_question(state)

        # 8. Step 7: Evaluate Stopping Policy
        should_stop, stop_reason, needs_esc = self.stopping_policy.should_stop(
            state, next_question
        )

        if should_stop or next_question is None:
            # Finalize session and route to appropriate specialty
            return self._finalize_session(
                session=session,
                state=state,
                patient_message_text=patient_message_text,
                turn_count=turn_count,
                stop_reason=stop_reason,
                needs_escalation=needs_esc,
                extracted_data=validated_evidences,
            )

        # 9. Step 8: Phrased Natural-Language Question via LLM
        phrased_question = self._phrase_question_safe(
            controlled_question=next_question.question_text,
            evidence_id=next_question.evidence_id,
        )

        # 10. Step 9: Atomic Database Persistence for Active Turn
        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="patient",
            content=patient_message_text,
            turn_index=turn_count,
            extracted_evidence=json.dumps(validated_evidences),
        )

        triage_repo.add_message(
            db=self.db,
            session_id=session.id,
            sender="assistant",
            content=phrased_question,
            turn_index=turn_count,
            extracted_evidence=json.dumps({
                "selected_evidence_id": next_question.evidence_id,
                "information_gain": next_question.expected_information_gain,
            }),
        )

        state.record_question_asked(next_question.evidence_id)

        return TriageConversationalTurnResponse(
            session_id=session.id,
            conversation_turn=turn_count,
            is_complete=False,
            stop_reason=None,
            patient_message=patient_message_text,
            assistant_message=phrased_question,
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
            top_candidate_conditions=[
                CandidateConditionSummary(
                    condition=c.condition,
                    probability=c.probability,
                    severity=c.severity,
                )
                for c in state.candidate_conditions[:5]
            ],
            uncertainty_score=state.uncertainty_score,
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
                    items = json.loads(msg.extracted_evidence)
                    if isinstance(items, list):
                        for item in items:
                            code = item.get("evidence_code")
                            st = item.get("status")
                            val = item.get("value", True)
                            if code and st == "PRESENT":
                                state.mark_present(code, val)
                            elif code and st == "ABSENT":
                                state.mark_absent(code)
                            elif code and st == "UNKNOWN":
                                state.mark_unknown(code)
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

    def _extract_evidence_safe(
        self, message_text: str, state: PatientState
    ) -> Any:
        try:
            return self.llm_provider.extract_patient_evidence(
                message=message_text,
                context={
                    "chief_complaint": state.chief_complaint,
                    "known_present": list(state.known_present_evidence.keys()),
                    "known_absent": state.known_absent_evidence,
                },
            )
        except Exception as exc:
            logger.warning(f"LLM evidence extraction failed, falling back to MockLLM: {exc}")
            mock = MockLLMProvider()
            return mock.extract_patient_evidence(message_text)

    def _phrase_question_safe(self, controlled_question: str, evidence_id: str) -> str:
        try:
            return self.llm_provider.phrase_question(
                controlled_question=controlled_question, evidence_id=evidence_id
            )
        except Exception as exc:
            logger.warning(f"LLM question phrasing failed, falling back to direct question: {exc}")
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
            top_candidate_conditions=[],
            uncertainty_score=state.uncertainty_score,
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

        # 1. Determine Urgency & Confidence
        top_cand = state.candidate_conditions[0] if state.candidate_conditions else None
        top_sev = top_cand.severity if top_cand else 1

        if top_sev >= 3:
            urgency = TriageUrgency.HIGH if top_sev == 4 else TriageUrgency.MODERATE
            confidence = round(1.0 - (state.uncertainty_score * 0.4), 2)
            rationale = (
                f"Candidate condition '{top_cand.condition if top_cand else 'Unknown'}' carries high clinical severity ({top_sev}). "
                "Expedited outpatient scheduling recommended."
            )
        elif state.uncertainty_score <= self.stopping_policy.min_entropy:
            urgency = TriageUrgency.LOW
            confidence = round(1.0 - (state.uncertainty_score * 0.3), 2)
            rationale = (
                f"Information gathered indicates standard outpatient acuity with primary presentation "
                f"aligned with '{top_cand.condition if top_cand else 'General medical concerns'}'. "
                "Routine outpatient scheduling appropriate."
            )
        else:
            urgency = TriageUrgency.MODERATE
            confidence = round(max(0.40, 1.0 - state.uncertainty_score), 2)
            rationale = (
                f"Assessment concluded ({stop_reason}). Clinical presentation shows moderate acuity. "
                "Standard in-person consultation advised."
            )

        if needs_escalation or confidence < TriageService.CONFIDENCE_THRESHOLD:
            session.status = TriageSessionStatus.ESCALATED
            guidance = (
                "Some clinical presentation factors remain uncertain. "
                "In-person medical evaluation is advised to ensure safe care navigation."
            )
        else:
            session.status = TriageSessionStatus.COMPLETED
            guidance = (
                "Based on your responses, routine care navigation is recommended. "
                "Please schedule an appointment with the appropriate clinical specialty."
            )

        session.completed_at = now

        # 2. Determine Specialty
        specialty = self._determine_specialty(state)

        # 3. Create Assessment
        assessment = TriageAssessment(
            triage_session_id=session.id,
            urgency=urgency,
            confidence=confidence,
            needs_escalation=needs_escalation,
            red_flag_detected=False,
            red_flag_codes=[],
            recommended_specialty_id=specialty.id if specialty else None,
            rationale=rationale,
            assessed_at=now,
        )
        self.db.add(assessment)
        self.db.add(session)

        # 4. Generate Completion Message
        spec_name = specialty.name if specialty else "General Medicine"
        top_name = top_cand.condition if top_cand else "your reported symptoms"
        assistant_summary_msg = (
            f"Thank you for answering our questions. Based on your symptoms and clinical details, "
            f"your presentation is most consistent with {top_name}. "
            f"We have navigated your care to {spec_name} with {urgency.value} urgency. "
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
            top_candidate_conditions=[
                CandidateConditionSummary(
                    condition=c.condition,
                    probability=c.probability,
                    severity=c.severity,
                )
                for c in state.candidate_conditions[:5]
            ],
            uncertainty_score=state.uncertainty_score,
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
        """Maps candidate conditions or presenting symptoms to a database Specialty."""
        top_cand = state.candidate_conditions[0] if state.candidate_conditions else None
        top_name = (top_cand.condition if top_cand else "").lower()
        complaint = state.chief_complaint.lower()

        # Dermatological
        if any(w in top_name or w in complaint for w in ["dermatitis", "eczema", "psoriasis", "rash", "urticaria", "skin"]):
            spec = specialty_repo.get_by_code(self.db, "DERM") or specialty_repo.get_by_name(self.db, "Dermatology")
            if spec:
                return spec

        # Cardiology / Pulmonology
        if any(w in top_name or w in complaint for w in ["angina", "pericarditis", "myocarditis", "cardio", "chest"]):
            spec = specialty_repo.get_by_code(self.db, "CARDIO") or specialty_repo.get_by_name(self.db, "Cardiology")
            if spec:
                return spec

        # Orthopedics
        if any(w in top_name or w in complaint for w in ["fracture", "sprain", "joint", "ortho", "bone", "arthritis"]):
            spec = specialty_repo.get_by_code(self.db, "ORTHO") or specialty_repo.get_by_name(self.db, "Orthopedics")
            if spec:
                return spec

        # ENT
        if any(w in top_name or w in complaint for w in ["sinusitis", "otitis", "pharyngitis", "throat", "ear", "nasal"]):
            spec = specialty_repo.get_by_code(self.db, "ENT") or specialty_repo.get_by_name(self.db, "ENT")
            if spec:
                return spec

        # Default to General Medicine
        return specialty_repo.get_by_code(self.db, "GEN") or specialty_repo.get_by_name(self.db, "General Medicine")
