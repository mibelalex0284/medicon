from typing import List, Optional
from app.ranking.constants import (
    LANGUAGE_SCORE_MATCH,
    LANGUAGE_SCORE_MISMATCH,
    LANGUAGE_SCORE_NEUTRAL,
    MAX_REFERENCE_EXPERIENCE_YEARS,
    MAX_REFERENCE_WAIT_MINUTES,
    MIN_OPERATIONAL_WAIT_MINUTES,
    PREFERENCE_SCORE_MATCH,
    PREFERENCE_SCORE_MISMATCH,
    PREFERENCE_SCORE_NEUTRAL,
    RATING_GLOBAL_PRIOR,
    RATING_MAX_SCALE,
    RATING_NEUTRAL_SCORE,
    RATING_SHRINKAGE_M,
    SPECIALTY_SCORE_PRIMARY,
    SPECIALTY_SCORE_SECONDARY,
)


def normalize_specialty(is_primary: bool) -> float:
    """Normalizes specialty relevance score.
    
    Doctor must already be eligible (holding the specialty).
    Primary specialty appointment is weighted higher than secondary focus.
    """
    return SPECIALTY_SCORE_PRIMARY if is_primary else SPECIALTY_SCORE_SECONDARY


def normalize_experience(years_of_experience: int) -> float:
    """Normalizes doctor years of experience to a bounded [0.0, 1.0] scale.
    
    Operational matching factor only; does not imply clinical superiority.
    """
    years = max(0, years_of_experience)
    return min(1.0, round(years / MAX_REFERENCE_EXPERIENCE_YEARS, 4))


def normalize_rating_reliability(average_rating: float, rating_count: int) -> float:
    """Computes Bayesian-adjusted rating score with shrinkage toward a global prior.
    
    Formula:
        adjusted_rating = (n / (n + m)) * rating + (m / (n + m)) * global_prior
        
    Guarantees:
    - High ratings with very few reviews (e.g. 4.9 from 2 reviews) shrink toward prior (4.15).
    - Established ratings with large sample size (e.g. 4.7 from 100 reviews) remain strong (4.63).
    - Unrated doctors (0 reviews) receive neutral prior score (0.80) rather than being penalized to zero.
    """
    if rating_count <= 0 or average_rating <= 0.0:
        return RATING_NEUTRAL_SCORE

    n = float(rating_count)
    m = float(RATING_SHRINKAGE_M)
    r = min(5.0, max(0.0, float(average_rating)))

    adjusted_rating = (n / (n + m)) * r + (m / (n + m)) * RATING_GLOBAL_PRIOR
    return min(1.0, max(0.0, round(adjusted_rating / RATING_MAX_SCALE, 4)))


def normalize_wait(expected_wait_minutes: int) -> float:
    """Normalizes expected operational waiting time to [0.0, 1.0] where shorter wait yields higher score.
    
    - 5 minutes wait -> 1.0
    - 35 minutes wait -> 0.75
    - 65 minutes wait -> 0.50
    - 125+ minutes wait -> 0.0
    """
    wait = max(MIN_OPERATIONAL_WAIT_MINUTES, expected_wait_minutes)
    excess_wait = wait - MIN_OPERATIONAL_WAIT_MINUTES
    raw_score = 1.0 - (excess_wait / float(MAX_REFERENCE_WAIT_MINUTES))
    return min(1.0, max(0.0, round(raw_score, 4)))


def normalize_availability(has_slots: bool, available_slot_count: int) -> float:
    """Normalizes appointment slot availability into a [0.0, 1.0] scale."""
    if not has_slots or available_slot_count <= 0:
        return 0.1  # Schedule exists, but current slots fully booked

    if available_slot_count >= 5:
        return 1.0

    raw = 0.60 + (available_slot_count * 0.08)
    return min(1.0, max(0.0, round(raw, 4)))


def normalize_preference(
    doctor_id: str,
    preferred_doctor_id: Optional[str],
    doctor_mode: str,
    preferred_mode: Optional[str],
) -> float:
    """Normalizes explicit patient preferences.
    
    NOTE: Only explicitly provided operational preferences are evaluated.
    Preferences are NEVER inferred from patient demographic or protected attributes.
    """
    if preferred_doctor_id:
        return PREFERENCE_SCORE_MATCH if doctor_id == preferred_doctor_id else PREFERENCE_SCORE_MISMATCH

    if preferred_mode:
        norm_pref = preferred_mode.strip().lower()
        norm_doc = doctor_mode.strip().lower()
        if norm_doc == norm_pref or norm_doc == "both":
            return PREFERENCE_SCORE_MATCH
        return PREFERENCE_SCORE_NEUTRAL

    # Neutral score when no preference was specified
    return PREFERENCE_SCORE_NEUTRAL


def normalize_language(
    doctor_languages: List[str], preferred_language: Optional[str]
) -> float:
    """Normalizes language match based only on explicit language data."""
    if not preferred_language or not preferred_language.strip():
        return LANGUAGE_SCORE_NEUTRAL

    target = preferred_language.strip().lower()
    doc_langs = [l.strip().lower() for l in doctor_languages if l.strip()]

    return LANGUAGE_SCORE_MATCH if target in doc_langs else LANGUAGE_SCORE_MISMATCH
