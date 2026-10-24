from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.models.profile import Profile
from app.models.triage_assessment import TriageAssessment, TriageUrgency
from app.ranking.deterministic import (
    DeterministicDoctorRankingProvider,
    deterministic_ranking_provider,
)
from app.ranking.interfaces import DoctorRankingProvider, WaitEstimationProvider
from app.ranking.wait_provider import (
    BaselineWaitEstimationProvider,
    baseline_wait_provider,
)
from app.repositories.doctor_repository import doctor_repo
from app.repositories.hospital_repository import hospital_repo
from app.repositories.patient_repository import patient_repo
from app.repositories.specialty_repository import specialty_repo
from app.repositories.triage_repository import triage_repo
from app.schemas.doctor_recommendation import (
    DoctorRecommendationRequest,
    DoctorRecommendationResponse,
)
from app.services.appointment_service import appointment_service


class DoctorRecommendationService:
    """Service orchestrating two-stage explainable doctor recommendation and ranking."""

    def __init__(
        self,
        ranking_provider: Optional[DoctorRankingProvider] = None,
        wait_provider: Optional[WaitEstimationProvider] = None,
    ):
        self.ranking_provider = ranking_provider or deterministic_ranking_provider
        self.wait_provider = wait_provider or baseline_wait_provider

    def recommend_doctors(
        self,
        db: Session,
        request: DoctorRecommendationRequest,
        current_user: AuthenticatedUser,
    ) -> DoctorRecommendationResponse:
        # 1. Resolve & Validate Hospital Boundary (Tenant Isolation)
        # Resolution Order:
        # 1. An explicitly selected hospital associated with the current recommendation request.
        # 2. A valid hospital affiliation on the authenticated user's application profile.
        # 3. If neither exists, return structured error indicating hospital selection is required.
        hospital_id = request.hospital_id
        if not hospital_id:
            if current_user.hospital_id:
                hospital_id = current_user.hospital_id
            elif current_user.is_patient:
                profile = db.query(Profile).filter(Profile.auth_user_id == current_user.id).first()
                if profile and profile.hospital_id:
                    hospital_id = profile.hospital_id

        if not hospital_id:
            raise ConflictError(
                message="Hospital ID must be specified in request or associated with user account",
                code="MISSING_HOSPITAL_CONTEXT",
            )

        # Ensure hospital exists and is active
        hospital = hospital_repo.get(db, hospital_id)
        if not hospital or not hospital.is_active:
            raise NotFoundError(
                message=f"Hospital with id '{hospital_id}' not found or is currently inactive",
                code="HOSPITAL_NOT_FOUND",
            )

        # Cross-hospital boundary check: patient cannot request doctors from a different hospital
        # if their profile is explicitly affiliated with a registered hospital
        if current_user.is_patient:
            profile = db.query(Profile).filter(Profile.auth_user_id == current_user.id).first()
            if (
                profile
                and profile.hospital_id
                and profile.hospital_id != hospital_id
            ):
                raise ForbiddenError(
                    message="Access forbidden: cannot request recommendations outside your registered hospital",
                    code="FORBIDDEN_CROSS_HOSPITAL_ACCESS",
                )

        # 2. Triage Session Integration & Safety
        target_specialty_id = request.specialty_id
        is_emergency_escalation = False
        escalation_notice = None
        triage_urgency = None

        if request.triage_session_id:
            session = triage_repo.get_session(db, request.triage_session_id)
            if not session:
                raise NotFoundError(
                    message=f"Triage session with id '{request.triage_session_id}' not found",
                    code="TRIAGE_SESSION_NOT_FOUND",
                )

            # Security: verify ownership (session must belong to the authenticated patient)
            if current_user.is_patient:
                patient = patient_repo.get_by_auth_user_id(db, current_user.id)
                if not patient or session.patient_id != patient.id:
                    raise ForbiddenError(
                        message="Access forbidden: triage session does not belong to the authenticated patient",
                        code="FORBIDDEN_TRIAGE_SESSION_ACCESS",
                    )

            # Retrieve assessment
            assessment = session.assessment or db.query(TriageAssessment).filter(
                TriageAssessment.triage_session_id == session.id
            ).first()
            if not assessment:
                raise NotFoundError(
                    message=f"Triage assessment not found for session '{session.id}'",
                    code="TRIAGE_ASSESSMENT_NOT_FOUND",
                )

            # Authoritative specialty from triage assessment
            if assessment.recommended_specialty_id:
                target_specialty_id = assessment.recommended_specialty_id

            triage_urgency = assessment.urgency

            # Emergency determination is distinct from urgency classification.
            # True emergency is identified by red flags.
            if assessment.red_flag_detected:
                is_emergency_escalation = True
                escalation_notice = (
                    "EMERGENCY SAFETY NOTICE: Triage assessment indicated critical warning signs or "
                    "red-flag emergency symptoms. Immediate emergency medical care is advised. "
                    "Outpatient doctor selection is not a substitute for emergency evaluation."
                )
            elif assessment.urgency == TriageUrgency.HIGH:
                # High urgency without an emergency determination allows urgent consultation pathway.
                is_emergency_escalation = False
                escalation_notice = (
                    "HIGH CLINICAL URGENCY: Your reported symptoms indicate elevated clinical urgency. "
                    "Please schedule a prompt / urgent consultation with the recommended clinical specialty. "
                    "Safety notice: Absence of red-flag symptoms does not guarantee safety. If your condition "
                    "worsens suddenly, seek immediate emergency medical care."
                )

        # Specialty is mandatory for recommendation
        if not target_specialty_id:
            raise ConflictError(
                message="Either specialty_id or a valid triage_session_id with a recommended specialty must be provided",
                code="MISSING_SPECIALTY_REQUIREMENT",
            )

        specialty = specialty_repo.get(db, target_specialty_id)
        if not specialty:
            raise NotFoundError(
                message=f"Specialty with id '{target_specialty_id}' not found",
                code="SPECIALTY_NOT_FOUND",
            )

        # 3. Stage A: Hard Eligibility Filtering
        # Doctor must be active, belong to the target hospital, and hold the required specialty
        candidate_doctors = doctor_repo.filter_doctors(
            db,
            hospital_id=hospital_id,
            specialty_id=target_specialty_id,
            is_active=True,
        )

        # Enforce clinical specialty consistency: a doctor whose primary clinical focus is
        # in another specialty (e.g. primary Dermatology) must not be matched or presented
        # as a specialist for an unrelated required specialty (e.g. General Medicine).
        filtered_candidates = []
        for doc in candidate_doctors:
            doc_specs = doc.specialties or []
            target_ds = next((ds for ds in doc_specs if ds.specialty_id == target_specialty_id), None)
            if not target_ds:
                continue
            primary_ds = next((ds for ds in doc_specs if ds.is_primary), None)
            if primary_ds and primary_ds.specialty_id != target_specialty_id:
                # Doctor's primary focus is in another domain; exclude from this specialty
                continue
            filtered_candidates.append(doc)
        candidate_doctors = filtered_candidates

        # Filter by consultation mode if requested
        if request.consultation_mode:
            req_mode = request.consultation_mode.strip().lower()
            if req_mode in ["in_person", "teleconsultation"]:
                candidate_doctors = [
                    d
                    for d in candidate_doctors
                    if d.consultation_mode == "both" or d.consultation_mode == req_mode
                ]

        # Filter by availability if explicitly required
        if request.require_availability:
            target_date = request.appointment_date or datetime.now(timezone.utc).date()
            available_candidates = []
            for doc in candidate_doctors:
                try:
                    avail = appointment_service.get_doctor_availability(
                        db, doc.id, target_date
                    )
                    open_slots = [s for s in avail.slots if s.is_available]
                    if len(open_slots) > 0:
                        available_candidates.append(doc)
                except Exception:
                    pass
            candidate_doctors = available_candidates

        # Handle zero eligible doctors explicitly
        if not candidate_doctors:
            return DoctorRecommendationResponse(
                recommendations=[],
                status="NO_ELIGIBLE_DOCTORS",
                message="No eligible doctors were found matching the required specialty and consultation constraints.",
                applied_specialty_id=target_specialty_id,
                applied_specialty_name=specialty.name,
                applied_hospital_id=hospital_id,
                total_eligible_doctors=0,
                is_emergency_escalation=is_emergency_escalation,
                escalation_notice=escalation_notice,
                urgency=triage_urgency,
            )

        # 4. Stage B: Explainable Scoring & Ranking
        ranked_recommendations = self.ranking_provider.rank_doctors(
            db=db,
            eligible_doctors=candidate_doctors,
            target_specialty_id=target_specialty_id,
            request=request,
            wait_provider=self.wait_provider,
        )

        status_code = "EMERGENCY_ESCALATION" if is_emergency_escalation else "SUCCESS"
        message = (
            f"Successfully matched and ranked {len(ranked_recommendations)} doctor(s) for {specialty.name}."
            if not is_emergency_escalation
            else "Emergency notice active. Recommendations provided for urgent consultation if appropriate."
        )

        return DoctorRecommendationResponse(
            recommendations=ranked_recommendations,
            status=status_code,
            message=message,
            applied_specialty_id=target_specialty_id,
            applied_specialty_name=specialty.name,
            applied_hospital_id=hospital_id,
            total_eligible_doctors=len(candidate_doctors),
            is_emergency_escalation=is_emergency_escalation,
            escalation_notice=escalation_notice,
            urgency=triage_urgency,
        )


doctor_recommendation_service = DoctorRecommendationService()
