from datetime import datetime, timezone
import re
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.core.exceptions import (
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.models.specialty import Specialty
from app.models.triage_answer import TriageAnswer
from app.models.triage_assessment import TriageAssessment, TriageUrgency
from app.models.triage_question import TriageQuestion
from app.models.triage_session import TriageSession, TriageSessionStatus
from app.repositories.patient_repository import patient_repo
from app.repositories.specialty_repository import specialty_repo
from app.repositories.triage_repository import triage_repo
from app.schemas.triage import (
    TriageAnswerCreate,
    TriageAssessmentResponse,
    TriageQuestionResponse,
    TriageSessionConfirm,
    TriageSessionCreate,
    TriageSessionResponse,
)


class TriageService:
    # Configurable confidence threshold for uncertainty escalation
    CONFIDENCE_THRESHOLD: float = 0.60

    # Deterministic red flag keyword patterns
    RED_FLAG_PATTERNS = {
        "RED_FLAG_CHEST_PAIN_SEVERE": [
            r"chest\s+pain",
            r"crushing\s+chest",
            r"heart\s+attack",
            r"pressure\s+in\s+chest",
        ],
        "RED_FLAG_BREATHING_DIFFICULTY": [
            r"can['’]?t\s+breathe",
            r"difficulty\s+breathing",
            r"shortness\s+of\s+breath",
            r"gasping",
            r"struggling\s+to\s+breathe",
            r"catch\s+(?:my\s+|one['’]?s\s+|their\s+)?breath",
            r"respiratory\s+distress",
        ],
        "RED_FLAG_LOSS_OF_CONSCIOUSNESS": [
            r"loss\s+of\s+consciousness",
            r"passed\s+out",
            r"fainted",
            r"blacked\s+out",
            r"unresponsive",
        ],
        "RED_FLAG_SEVERE_BLEEDING": [
            r"severe\s+bleeding",
            r"uncontrolled\s+bleeding",
            r"gushing\s+blood",
            r"coughing\s+up\s+blood",
        ],
        "RED_FLAG_SUDDEN_NEUROLOGICAL_DEFICIT": [
            r"facial\s+droop",
            r"slurred\s+speech",
            r"stroke",
            r"sudden\s+weakness\s+on\s+one\s+side",
            r"numbness\s+one\s+side",
        ],
        "RED_FLAG_ANAPHYLAXIS": [
            r"throat\s+swelling",
            r"lips\s+swelling",
            r"anaphylaxis",
            r"swollen\s+tongue",
        ],
    }

    # Mapping from red-flag questions to codes
    QUESTION_RED_FLAG_MAP = {
        "TQ_CHEST_PAIN_SEVERITY": "RED_FLAG_CHEST_PAIN_SEVERE",
        "TQ_BREATHING_DIFFICULTY": "RED_FLAG_BREATHING_DIFFICULTY",
        "TQ_CONSCIOUSNESS_FAINTING": "RED_FLAG_LOSS_OF_CONSCIOUSNESS",
        "TQ_BLEEDING_SEVERE": "RED_FLAG_SEVERE_BLEEDING",
        "TQ_NEURO_SUDDEN_DEFICIT": "RED_FLAG_SUDDEN_NEUROLOGICAL_DEFICIT",
        "TQ_ALLERGIC_ANAPHYLAXIS": "RED_FLAG_ANAPHYLAXIS",
    }

    @staticmethod
    def create_session(
        db: Session, obj_in: TriageSessionCreate, *, actor_auth_user_id: str
    ) -> TriageSession:
        patient = patient_repo.get_by_auth_user_id(db, actor_auth_user_id)
        if not patient:
            raise NotFoundError(
                message="Patient profile not found for authenticated user",
                code="PATIENT_NOT_FOUND",
            )

        triage_repo.ensure_default_questions(db)

        session = TriageSession(
            patient_id=patient.id,
            original_input=obj_in.original_input.strip(),
            confirmed_input=obj_in.original_input.strip(),
            language=obj_in.language,
            status=TriageSessionStatus.IN_PROGRESS,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def get_session(db: Session, session_id: str) -> TriageSession:
        session = triage_repo.get_session(db, session_id)
        if not session:
            raise NotFoundError(
                message=f"Triage session with id '{session_id}' not found",
                code="TRIAGE_SESSION_NOT_FOUND",
            )
        return session

    @staticmethod
    def confirm_input(
        db: Session, session_id: str, obj_in: TriageSessionConfirm, *, actor_auth_user_id: str
    ) -> TriageSession:
        session = TriageService.get_session(db, session_id)
        TriageService._assert_patient_ownership(db, session, actor_auth_user_id)

        if session.status != TriageSessionStatus.IN_PROGRESS:
            raise InvalidStateTransitionError(
                message="Cannot modify input for a completed or escalated session",
                code="SESSION_NOT_IN_PROGRESS",
            )

        session.confirmed_input = obj_in.confirmed_input.strip()
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def get_next_question(
        db: Session, session_id: str, *, actor_auth_user_id: str
    ) -> Optional[TriageQuestion]:
        session = TriageService.get_session(db, session_id)
        TriageService._assert_patient_ownership(db, session, actor_auth_user_id)

        if session.status != TriageSessionStatus.IN_PROGRESS:
            return None

        return triage_repo.get_next_question(db, session_id)

    @staticmethod
    def answer_question(
        db: Session, session_id: str, obj_in: TriageAnswerCreate, *, actor_auth_user_id: str
    ) -> TriageAnswer:
        session = TriageService.get_session(db, session_id)
        TriageService._assert_patient_ownership(db, session, actor_auth_user_id)

        if session.status != TriageSessionStatus.IN_PROGRESS:
            raise InvalidStateTransitionError(
                message="Cannot record answers for a completed or escalated session",
                code="SESSION_NOT_IN_PROGRESS",
            )

        # Validate question exists
        question = triage_repo.get_question_by_id(db, obj_in.question_id)
        if not question:
            raise NotFoundError(
                message=f"Question with id '{obj_in.question_id}' not found in question bank",
                code="QUESTION_NOT_FOUND",
            )

        return triage_repo.add_answer(
            db,
            session_id=session_id,
            question_id=obj_in.question_id,
            answer_value=obj_in.answer_value,
        )

    @staticmethod
    def assess_session(
        db: Session, session_id: str, *, actor_auth_user_id: str
    ) -> TriageAssessment:
        session = TriageService.get_session(db, session_id)
        TriageService._assert_patient_ownership(db, session, actor_auth_user_id)

        if session.assessment:
            return session.assessment

        now = datetime.now(timezone.utc)
        answers = triage_repo.get_session_answers(db, session_id)
        input_text = (session.confirmed_input or session.original_input).lower()

        # Step 1: Deterministic Red-Flag Screening
        red_flags_fired = TriageService._screen_red_flags(input_text, answers)

        if red_flags_fired:
            # Red flag detected: Immediately force HIGH urgency and escalation
            urgency = TriageUrgency.HIGH
            confidence = 1.0
            needs_escalation = True
            session.status = TriageSessionStatus.ESCALATED
            session.completed_at = now
            rationale = (
                f"Emergency red-flag indicators detected: [{', '.join(red_flags_fired)}]. "
                "Immediate medical escalation is required."
            )
            guidance = (
                "Emergency warning signs were detected. Seek urgent medical attention "
                "or proceed to the nearest emergency facility immediately."
            )
        else:
            # Step 2: Controlled Urgency & Uncertainty Calculation
            urgency, confidence, rationale = TriageService._calculate_urgency_and_confidence(
                input_text, answers
            )
            # Step 3: Uncertainty & Abstention check
            needs_escalation = confidence < TriageService.CONFIDENCE_THRESHOLD
            if needs_escalation:
                guidance = (
                    "Some clinical presentation factors remain uncertain. "
                    "In-person medical evaluation is advised to ensure safe care navigation."
                )
            else:
                guidance = (
                    "Based on your responses, routine care navigation is recommended. "
                    "Please schedule an appointment with the appropriate clinical specialty."
                )
            session.status = TriageSessionStatus.COMPLETED
            session.completed_at = now

        # Step 4: Specialty Routing
        recommended_specialty = TriageService._determine_specialty(db, input_text, answers)

        assessment = TriageAssessment(
            triage_session_id=session.id,
            urgency=urgency,
            confidence=round(confidence, 2),
            needs_escalation=needs_escalation,
            red_flag_detected=bool(red_flags_fired),
            recommended_specialty_id=recommended_specialty.id if recommended_specialty else None,
            rationale=rationale,
            assessed_at=now,
        )
        assessment.red_flag_codes = red_flags_fired

        db.add(assessment)
        db.add(session)
        db.commit()
        db.refresh(assessment)
        return assessment

    @classmethod
    def _screen_red_flags(
        cls, input_text: str, answers: List[TriageAnswer]
    ) -> List[str]:
        """Runs strictly deterministic rules on free text and structured question answers."""
        flags: List[str] = []

        # 1. Screen free text input against regex rules
        negations = ["no", "not", "without", "denies", "negative for", "free of"]
        for code, patterns in cls.RED_FLAG_PATTERNS.items():
            for pat in patterns:
                for match in re.finditer(pat, input_text):
                    prefix = input_text[max(0, match.start() - 25):match.start()].strip()
                    tokens = prefix.split()
                    if tokens and tokens[-1] in ["no", "not", "without", "denies"]:
                        continue  # Negated indicator, e.g. "no chest pain"
                    if code not in flags:
                        flags.append(code)
                    break

        # 2. Screen answers to controlled questions
        for ans in answers:
            if not ans.question:
                continue
            q_code = ans.question.code
            ans_val = ans.answer_value.strip().upper()

            # Affirmative answer to a red-flag question triggers the flag
            if ans_val == "YES" and q_code in cls.QUESTION_RED_FLAG_MAP:
                flag_code = cls.QUESTION_RED_FLAG_MAP[q_code]
                if flag_code not in flags:
                    flags.append(flag_code)

        return flags

    @classmethod
    def _calculate_urgency_and_confidence(
        cls, input_text: str, answers: List[TriageAnswer]
    ) -> Tuple[TriageUrgency, float, str]:
        """Calculates urgency score and confidence without generative LLM hallucination."""
        score = 0
        total_answers = len(answers)
        unknown_answers = sum(1 for a in answers if a.answer_value.strip().upper() == "UNKNOWN")

        # Keywords in input indicating moderate/high urgency
        if any(w in input_text for w in ["fever", "pain", "swelling", "vomiting", "dizziness"]):
            score += 2
        if any(w in input_text for w in ["severe", "intense", "worsening", "unbearable"]):
            score += 3

        # Add score from answers
        for ans in answers:
            val = ans.answer_value.strip().upper()
            if val == "YES":
                if ans.question and ans.question.category in ["CARDIO", "RESPIRATORY"]:
                    score += 3
                else:
                    score += 1

        # Determine Urgency
        if score >= 5:
            urgency = TriageUrgency.HIGH
            rationale = "Multiple prominent symptoms and risk factors present elevated clinical urgency."
        elif score >= 2:
            urgency = TriageUrgency.MODERATE
            rationale = "Presenting symptoms indicate moderate clinical urgency requiring timely outpatient evaluation."
        else:
            urgency = TriageUrgency.LOW
            rationale = "Symptoms indicate standard outpatient presentation suitable for routine scheduling."

        # Confidence: baseline 0.90, discounted if many questions are UNKNOWN or few answered
        if total_answers == 0:
            confidence = 0.50  # Low confidence when no controlled questions answered
        else:
            unknown_ratio = unknown_answers / total_answers
            confidence = max(0.30, 0.95 - (unknown_ratio * 0.50))

        return urgency, confidence, rationale

    @classmethod
    def _determine_specialty(
        cls, db: Session, input_text: str, answers: List[TriageAnswer]
    ) -> Optional[Specialty]:
        """Maps presentation to an existing Specialty entity. Falls back to General Medicine."""
        # 1. Check answers
        for ans in answers:
            if not ans.question:
                continue
            cat = ans.question.category
            if cat == "DERM" and ans.answer_value.strip().upper() == "YES":
                spec = specialty_repo.get_by_code(db, "DERM") or specialty_repo.get_by_name(db, "Dermatology")
                if spec:
                    return spec
            elif cat == "ENT" and ans.answer_value.strip().upper() == "YES":
                spec = specialty_repo.get_by_code(db, "ENT") or specialty_repo.get_by_name(db, "ENT")
                if spec:
                    return spec
            elif cat == "ORTHO" and ans.answer_value.strip().upper() == "YES":
                spec = specialty_repo.get_by_code(db, "ORTHO") or specialty_repo.get_by_name(db, "Orthopedics")
                if spec:
                    return spec

        # 2. Check input keywords
        if any(w in input_text for w in ["rash", "skin", "mole", "acne", "eczema"]):
            spec = specialty_repo.get_by_code(db, "DERM") or specialty_repo.get_by_name(db, "Dermatology")
            if spec:
                return spec
        if any(w in input_text for w in ["ear", "throat", "sinus", "nasal", "tonsil"]):
            spec = specialty_repo.get_by_code(db, "ENT") or specialty_repo.get_by_name(db, "ENT")
            if spec:
                return spec
        if any(w in input_text for w in ["bone", "joint", "knee", "back", "ankle", "sprain", "fracture"]):
            spec = specialty_repo.get_by_code(db, "ORTHO") or specialty_repo.get_by_name(db, "Orthopedics")
            if spec:
                return spec
        if any(w in input_text for w in ["heart", "cardio", "palpitations"]):
            spec = specialty_repo.get_by_code(db, "CARDIO") or specialty_repo.get_by_name(db, "Cardiology")
            if spec:
                return spec

        # 3. Fallback: General Medicine
        gen_med = (
            specialty_repo.get_by_code(db, "GEN-MED")
            or specialty_repo.get_by_name(db, "General Medicine")
            or db.query(Specialty).filter(Specialty.is_active.is_(True)).first()
        )
        return gen_med

    @staticmethod
    def _assert_patient_ownership(
        db: Session, session: TriageSession, actor_auth_user_id: str
    ) -> None:
        patient = patient_repo.get(db, session.patient_id)
        if not patient or patient.profile.auth_user_id != actor_auth_user_id:
            raise ForbiddenError(
                message="Access forbidden: you cannot access another patient's triage session",
                code="FORBIDDEN_TRIAGE_ACCESS",
            )


triage_service = TriageService()
