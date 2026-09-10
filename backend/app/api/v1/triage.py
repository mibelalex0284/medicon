from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser, require_patient
from app.db.session import get_db
from app.schemas.triage import (
    TriageAnswerCreate,
    TriageAnswerResponse,
    TriageAssessmentResponse,
    TriageQuestionResponse,
    TriageSessionConfirm,
    TriageSessionCreate,
    TriageSessionResponse,
)
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
