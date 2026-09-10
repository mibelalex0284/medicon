from datetime import date, datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.doctor import Doctor
from app.ranking.constants import (
    RANKING_WEIGHTS,
    WEIGHT_AVAILABILITY,
    WEIGHT_EXPERIENCE,
    WEIGHT_LANGUAGE_MATCH,
    WEIGHT_PATIENT_PREFERENCE,
    WEIGHT_PREDICTED_WAIT,
    WEIGHT_RATING_RELIABILITY,
    WEIGHT_SPECIALTY_MATCH,
)
from app.ranking.explanations import build_explanation
from app.ranking.interfaces import DoctorRankingProvider, WaitEstimationProvider
from app.ranking.normalization import (
    normalize_availability,
    normalize_experience,
    normalize_language,
    normalize_preference,
    normalize_rating_reliability,
    normalize_specialty,
    normalize_wait,
)
from app.schemas.doctor import DoctorResponse
from app.schemas.doctor_recommendation import (
    DoctorRecommendationItem,
    DoctorRecommendationRequest,
    RecommendationFactorBreakdown,
)
from app.services.appointment_service import appointment_service


class DeterministicDoctorRankingProvider(DoctorRankingProvider):
    """Deterministic, explainable doctor ranking provider.
    
    Computes normalized factor scores, aggregates them using centralized weights,
    applies strict deterministic tie-breaking, and produces structured explanations.
    No LLM is utilized.
    """

    def rank_doctors(
        self,
        db: Session,
        eligible_doctors: List[Doctor],
        target_specialty_id: str,
        request: DoctorRecommendationRequest,
        wait_provider: WaitEstimationProvider,
    ) -> List[DoctorRecommendationItem]:
        if not eligible_doctors:
            return []

        target_date = request.appointment_date or datetime.now(timezone.utc).date()
        scored_items = []

        for doc in eligible_doctors:
            # 1. Specialty factor (doctor is already eligible)
            doc_spec = next(
                (ds for ds in doc.specialties if ds.specialty_id == target_specialty_id),
                None,
            )
            is_primary = bool(doc_spec.is_primary) if doc_spec else False
            specialty_name = (
                doc_spec.specialty.name
                if (doc_spec and doc_spec.specialty)
                else "Requested Specialty"
            )
            spec_score = normalize_specialty(is_primary)

            # 2. Availability factor (concrete slots via appointment service)
            try:
                avail_resp = appointment_service.get_doctor_availability(
                    db, doc.id, target_date
                )
                open_slots = [s for s in avail_resp.slots if s.is_available]
                slot_count = len(open_slots)
                has_slots = slot_count > 0
            except Exception:
                has_slots = False
                slot_count = 0

            avail_score = normalize_availability(has_slots, slot_count)

            # 3. Predicted wait factor (Stage 3 baseline queue estimation)
            estimated_wait = wait_provider.get_estimated_wait_minutes(
                db, doc.id, target_date
            )
            wait_score = normalize_wait(estimated_wait)

            # 4. Experience factor
            exp_score = normalize_experience(doc.years_of_experience)

            # 5. Rating reliability factor (Bayesian shrinkage)
            rating_score = normalize_rating_reliability(
                doc.average_rating, doc.rating_count
            )

            # 6. Patient preference factor
            pref_score = normalize_preference(
                doc.id,
                request.preferred_doctor_id,
                doc.consultation_mode,
                request.consultation_mode,
            )
            pref_match = bool(pref_score >= 0.90)

            # 7. Language match factor
            lang_score = normalize_language(
                doc.supported_languages, request.preferred_language
            )
            lang_match = bool(lang_score >= 0.90)

            # Composite weighted score [0.0, 1.0]
            composite_score = (
                WEIGHT_SPECIALTY_MATCH * spec_score
                + WEIGHT_AVAILABILITY * avail_score
                + WEIGHT_PREDICTED_WAIT * wait_score
                + WEIGHT_EXPERIENCE * exp_score
                + WEIGHT_RATING_RELIABILITY * rating_score
                + WEIGHT_PATIENT_PREFERENCE * pref_score
                + WEIGHT_LANGUAGE_MATCH * lang_score
            )
            composite_score = min(1.0, max(0.0, round(composite_score, 4)))

            # Assemble factor breakdown
            breakdown = RecommendationFactorBreakdown(
                specialty_match=True,
                specialty_is_primary=is_primary,
                specialty_score=spec_score,
                has_available_slots=has_slots,
                available_slot_count=slot_count,
                availability_score=avail_score,
                estimated_wait_minutes=estimated_wait,
                wait_score=wait_score,
                years_of_experience=doc.years_of_experience,
                experience_score=exp_score,
                average_rating=doc.average_rating,
                rating_count=doc.rating_count,
                rating_reliability_score=rating_score,
                preference_match=pref_match,
                preference_score=pref_score,
                language_match=lang_match,
                language_score=lang_score,
                raw_weights=RANKING_WEIGHTS,
            )

            # Generate auditable matched factors and explanation
            matched_factors, explanation = build_explanation(
                breakdown, specialty_name, request.preferred_language
            )

            scored_items.append(
                {
                    "doctor": doc,
                    "score": composite_score,
                    "avail_score": avail_score,
                    "estimated_wait": estimated_wait,
                    "rating_score": rating_score,
                    "doctor_id": doc.id,
                    "consultation_mode": doc.consultation_mode,
                    "matched_factors": matched_factors,
                    "explanation": explanation,
                    "breakdown": breakdown,
                }
            )

        # Strict deterministic tie-breaking hierarchy:
        # 1. Higher composite score
        # 2. Higher availability score
        # 3. Lower estimated wait minutes (-estimated_wait)
        # 4. Higher rating reliability score
        # 5. Stable doctor ID string comparison
        scored_items.sort(
            key=lambda x: (
                x["score"],
                x["avail_score"],
                -x["estimated_wait"],
                x["rating_score"],
                x["doctor_id"],
            ),
            reverse=True,
        )

        results: List[DoctorRecommendationItem] = []
        for idx, item in enumerate(scored_items[: request.limit], start=1):
            doc_schema = DoctorResponse.model_validate(item["doctor"])
            results.append(
                DoctorRecommendationItem(
                    doctor_id=item["doctor_id"],
                    rank=idx,
                    score=item["score"],
                    estimated_wait_minutes=item["estimated_wait"],
                    consultation_mode=item["consultation_mode"],
                    matched_factors=item["matched_factors"],
                    explanation=item["explanation"],
                    doctor=doc_schema,
                    factor_breakdown=item["breakdown"],
                )
            )

        return results


deterministic_ranking_provider = DeterministicDoctorRankingProvider()
