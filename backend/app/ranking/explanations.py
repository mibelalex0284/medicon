from typing import List, Tuple
from app.schemas.doctor_recommendation import RecommendationFactorBreakdown


def build_explanation(
    breakdown: RecommendationFactorBreakdown,
    specialty_name: str,
    preferred_language: str = None,
) -> Tuple[List[str], str]:
    """Generates an auditable list of matched factors and deterministic operational explanation.
    
    IMPORTANT RULES:
    1. Deterministic generation from actual calculated factors.
    2. No LLMs used.
    3. No medical superiority claims or superlatives ('best doctor', 'most qualified', 'medically superior').
    """
    matched_factors: List[str] = []
    reasons: List[str] = []

    # 1. Specialty factor
    if breakdown.specialty_match:
        if breakdown.specialty_is_primary:
            matched_factors.append("specialty_primary")
            reasons.append(f"matches required specialty ({specialty_name}, primary focus)")
        else:
            matched_factors.append("specialty_secondary")
            reasons.append(f"matches required specialty ({specialty_name})")

    # 2. Availability factor
    if breakdown.has_available_slots and breakdown.available_slot_count > 0:
        matched_factors.append("available_slots")
        reasons.append(f"has near-term availability ({breakdown.available_slot_count} open slot(s))")

    # 3. Wait factor
    if breakdown.wait_score >= 0.60:
        matched_factors.append("shorter_wait")
        reasons.append(f"shorter estimated wait ({breakdown.estimated_wait_minutes} mins)")
    elif breakdown.wait_score >= 0.40:
        matched_factors.append("moderate_wait")
        reasons.append(f"estimated wait of {breakdown.estimated_wait_minutes} mins")

    # 4. Relevant experience factor
    if breakdown.years_of_experience >= 5:
        matched_factors.append("established_experience")
        reasons.append(f"{breakdown.years_of_experience} years clinical practice experience")

    # 5. Patient preference factor (including explicit language preference if requested)
    if breakdown.preference_match:
        matched_factors.append("patient_preference")
        if breakdown.language_match and preferred_language and preferred_language.strip():
            matched_factors.append("language_match")
            reasons.append(f"matches your explicit preferences (including language: {preferred_language})")
        else:
            reasons.append("matches your explicit consultation preference")

    if not reasons:
        explanation = f"Eligible operational match for {specialty_name} based on standard department routing."
    else:
        # Construct natural sentence
        if len(reasons) == 1:
            explanation = f"Recommended because the doctor {reasons[0]}."
        elif len(reasons) == 2:
            explanation = f"Recommended because the doctor {reasons[0]} and {reasons[1]}."
        else:
            explanation = f"Recommended because the doctor {', '.join(reasons[:-1])}, and {reasons[-1]}."

    return matched_factors, explanation
