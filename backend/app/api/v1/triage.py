from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser, get_current_user, require_patient
from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.repositories.triage_repository import triage_repo
from app.schemas.triage import (
    PreConsultationReportResponse,
    TriageAnswerCreate,
    TriageAnswerResponse,
    TriageAssessmentResponse,
    TriageConversationalTurnResponse,
    TriageMessageCreate,
    TriageMessageResponse,
    TriageQuestionResponse,
    TriageSessionConfirm,
    TriageSessionCreate,
    TriageSessionResponse,
)
from app.services.triage.orchestrator import ConversationalTriageOrchestrator
from app.services.triage_service import triage_service

router = APIRouter(tags=["Triage"])


@router.post(
    "/sessions",
    response_model=TriageSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start Triage Session",
    description="Initiates a new outpatient care-navigation triage interaction.",
)
def create_triage_session(
    session_in: TriageSessionCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> TriageSessionResponse:
    session = triage_service.create_session(
        db, session_in, actor_auth_user_id=current_user.id
    )
    return session


@router.get(
    "/sessions/{session_id}",
    response_model=TriageSessionResponse,
    summary="Get Triage Session Details",
)
def get_triage_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> TriageSessionResponse:
    session = triage_service.get_session(db, session_id)
    triage_service._assert_patient_ownership(db, session, current_user.id)
    return session


@router.post(
    "/sessions/{session_id}/confirm",
    response_model=TriageSessionResponse,
    summary="Confirm Input Symptoms",
    description="Confirms or refines the patient's presenting symptom description.",
)
def confirm_triage_input(
    session_id: str,
    confirm_in: TriageSessionConfirm,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> TriageSessionResponse:
    return triage_service.confirm_input(
        db, session_id, confirm_in, actor_auth_user_id=current_user.id
    )


@router.get(
    "/sessions/{session_id}/next-question",
    response_model=Optional[TriageQuestionResponse],
    summary="Get Next Adaptive Question",
    description="Retrieves the next unanswered question from the clinical question bank.",
)
def get_next_triage_question(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> Optional[TriageQuestionResponse]:
    return triage_service.get_next_question(
        db, session_id, actor_auth_user_id=current_user.id
    )


@router.post(
    "/sessions/{session_id}/answers",
    response_model=TriageAnswerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Answer Triage Question",
    description="Submits an answer to a controlled question from the approved question bank.",
)
def answer_triage_question(
    session_id: str,
    answer_in: TriageAnswerCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> TriageAnswerResponse:
    return triage_service.answer_question(
        db, session_id, answer_in, actor_auth_user_id=current_user.id
    )


@router.post(
    "/sessions/{session_id}/assess",
    response_model=TriageAssessmentResponse,
    summary="Perform Triage Assessment",
    description="Executes deterministic red-flag screening, calculates urgency, evaluates uncertainty, and routes to appropriate clinical specialty.",
)
def assess_triage_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> TriageAssessmentResponse:
    assessment = triage_service.assess_session(
        db, session_id, actor_auth_user_id=current_user.id
    )
    # Generate navigation guidance string
    guidance = (
        "Emergency warning signs were detected. Seek urgent medical attention or proceed to the nearest emergency department immediately."
        if assessment.red_flag_detected
        else (
            "Some clinical presentation factors remain uncertain. In-person clinical evaluation is advised."
            if assessment.needs_escalation
            else "Standard outpatient presentation suitable for routine scheduling."
        )
    )
    return TriageAssessmentResponse(
        id=assessment.id,
        triage_session_id=assessment.triage_session_id,
        urgency=assessment.urgency,
        confidence=assessment.confidence,
        needs_escalation=assessment.needs_escalation,
        red_flag_detected=assessment.red_flag_detected,
        red_flag_codes=assessment.red_flag_codes,
        recommended_specialty_id=assessment.recommended_specialty_id,
        recommended_specialty_name=(
            assessment.recommended_specialty.name
            if assessment.recommended_specialty
            else "General Medicine"
        ),
        rationale=assessment.rationale,
        guidance=guidance,
        assessed_at=assessment.assessed_at,
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=TriageConversationalTurnResponse,
    status_code=status.HTTP_200_OK,
    summary="Process Conversational Triage Turn",
    description="Processes a patient natural-language message, extracts clinical evidence, screens red flags, and selects the next adaptive question.",
)
def process_triage_message(
    session_id: str,
    message_in: TriageMessageCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> TriageConversationalTurnResponse:
    orchestrator = ConversationalTriageOrchestrator(db=db)
    return orchestrator.process_patient_turn(
        session_id=session_id,
        patient_message_text=message_in.content,
        actor_auth_user_id=current_user.id,
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=List[TriageMessageResponse],
    summary="Get Triage Session Messages",
    description="Retrieves the chronological message history for a conversational triage session.",
)
def get_triage_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_patient),
) -> List[TriageMessageResponse]:
    session = triage_service.get_session(db, session_id)
    triage_service._assert_patient_ownership(db, session, current_user.id)
    return triage_repo.get_session_messages(db, session_id)


@router.get(
    "/sessions/{session_id}/report",
    response_model=PreConsultationReportResponse,
    summary="Get Pre-Consultation Intake Report",
    description="Retrieves the structured pre-consultation intake report for the physician or patient.",
)
def get_pre_consultation_report(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PreConsultationReportResponse:
    session = triage_service.get_session(db, session_id)
    if current_user.is_patient:
        triage_service._assert_patient_ownership(db, session, current_user.id)
    elif current_user.is_doctor or current_user.is_admin:
        patient = session.patient or patient_repo.get(db, session.patient_id)
        patient_hospital_id = (
            patient.profile.hospital_id
            if (patient and patient.profile)
            else None
        )
        user_hospital_id = current_user.hospital_id
        if (
            not patient_hospital_id
            or not user_hospital_id
            or str(patient_hospital_id) != str(user_hospital_id)
        ):
            raise ForbiddenError(
                message="Access forbidden: user and patient must belong to the same hospital",
                code="FORBIDDEN_REPORT_ACCESS",
            )
    else:
        raise ForbiddenError(
            message="Access forbidden to triage report",
            code="FORBIDDEN_REPORT_ACCESS",
        )
    orchestrator = ConversationalTriageOrchestrator(db=db)
    return orchestrator.get_pre_consultation_report(session_id)


