import datetime
import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.doctor import Doctor
from app.models.profile import UserRole
from app.models.triage_assessment import TriageAssessment, TriageUrgency
from app.models.triage_session import TriageSession, TriageSessionStatus
from app.ranking.constants import (
    RANKING_WEIGHTS,
    WEIGHT_AVAILABILITY,
    WEIGHT_EXPERIENCE,
    WEIGHT_PATIENT_PREFERENCE,
    WEIGHT_PREDICTED_WAIT,
    WEIGHT_SPECIALTY_MATCH,
)
from app.ranking.deterministic import deterministic_ranking_provider
from app.ranking.interfaces import WaitEstimationProvider
from app.ranking.normalization import (
    normalize_availability,
    normalize_experience,
    normalize_language,
    normalize_preference,
    normalize_rating_reliability,
    normalize_specialty,
    normalize_wait,
)
from app.schemas.doctor import DoctorCreate
from app.schemas.doctor_recommendation import DoctorRecommendationRequest
from app.schemas.doctor_specialty import DoctorSpecialtyCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.services.doctor_recommendation_service import doctor_recommendation_service
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.core.dependencies import AuthenticatedUser
from tests.unit.test_doctor_recommendation import rec_setup_data


# Reference 7-factor weights for comparison
OLD_7_FACTOR_WEIGHTS = {
    "specialty_match": 0.30,
    "availability": 0.20,
    "predicted_wait": 0.15,
    "experience": 0.10,
    "rating_reliability": 0.10,
    "patient_preference": 0.10,
    "language_match": 0.05,
}


def compute_old_7_factor_score(
    spec_score: float,
    avail_score: float,
    wait_score: float,
    exp_score: float,
    rating_score: float,
    pref_score: float,
    lang_score: float,
) -> float:
    """Computes the legacy 7-factor score for exact deterministic comparison."""
    score = (
        0.30 * spec_score
        + 0.20 * avail_score
        + 0.15 * wait_score
        + 0.10 * exp_score
        + 0.10 * rating_score
        + 0.10 * pref_score
        + 0.05 * lang_score
    )
    return round(score, 4)


def compute_new_5_factor_score(
    spec_score: float,
    avail_score: float,
    wait_score: float,
    exp_score: float,
    pref_score: float,
) -> float:
    """Computes the 5-factor score."""
    score = (
        WEIGHT_SPECIALTY_MATCH * spec_score
        + WEIGHT_AVAILABILITY * avail_score
        + WEIGHT_PREDICTED_WAIT * wait_score
        + WEIGHT_EXPERIENCE * exp_score
        + WEIGHT_PATIENT_PREFERENCE * pref_score
    )
    return round(score, 4)


# ============================================================================
# DETERMINISTIC TEST SCENARIOS A THROUGH I
# ============================================================================


def test_scenario_a_equally_eligible_different_wait_times():
    """Scenario A: Two equally eligible doctors with different waiting times.
    
    Verifies that wait time has a stronger operational impact in the 5-factor model
    (weight increased from 0.15 to 0.20), rewarding low-wait outpatient routing.
    """
    spec_score = 1.0
    avail_score = 1.0
    exp_score = 0.50
    pref_score = 0.50  # neutral

    # Doctor 1: 15 min wait -> score = 0.9167
    wait_score_1 = normalize_wait(15)
    # Doctor 2: 65 min wait -> score = 0.5000
    wait_score_2 = normalize_wait(65)

    old_score_1 = compute_old_7_factor_score(
        spec_score, avail_score, wait_score_1, exp_score, 0.80, pref_score, 0.50
    )
    old_score_2 = compute_old_7_factor_score(
        spec_score, avail_score, wait_score_2, exp_score, 0.80, pref_score, 0.50
    )

    new_score_1 = compute_new_5_factor_score(
        spec_score, avail_score, wait_score_1, exp_score, pref_score
    )
    new_score_2 = compute_new_5_factor_score(
        spec_score, avail_score, wait_score_2, exp_score, pref_score
    )

    # Both models rank Doctor 1 first
    assert new_score_1 > new_score_2
    assert old_score_1 > old_score_2

    # In 5-factor model, the score delta is strictly larger due to 0.20 wait weight vs 0.15
    delta_old = round(old_score_1 - old_score_2, 4)
    delta_new = round(new_score_1 - new_score_2, 4)
    assert delta_new > delta_old
    assert delta_new == pytest.approx(0.20 * (wait_score_1 - wait_score_2), abs=1e-4)


def test_scenario_b_excellent_ratings_versus_longer_wait():
    """Scenario B: A doctor with excellent ratings but a longer wait.
    
    Demonstrates that removing Bayesian rating reliability stops review counts from
    overriding operational clinic queue load, preventing bottlenecking.
    """
    spec_score = 1.0
    avail_score = 0.84  # 3 slots
    exp_score = 0.40   # 12 years

    # Doctor B1: High rating (4.9 with 100 reviews), but long wait (75 min wait -> 0.4167)
    rating_score_b1 = normalize_rating_reliability(4.9, 100)  # ~0.9636
    wait_score_b1 = normalize_wait(75)                        # 0.4167

    # Doctor B2: Moderate/unrated reviews, but low wait (10 min wait -> 0.9583)
    rating_score_b2 = normalize_rating_reliability(3.5, 5)    # ~0.7667
    wait_score_b2 = normalize_wait(10)                        # 0.9583

    # Legacy 7-factor calculation
    old_score_b1 = compute_old_7_factor_score(
        spec_score, avail_score, wait_score_b1, exp_score, rating_score_b1, 0.50, 0.50
    )
    old_score_b2 = compute_old_7_factor_score(
        spec_score, avail_score, wait_score_b2, exp_score, rating_score_b2, 0.50, 0.50
    )

    # 5-factor calculation (ratings excluded)
    new_score_b1 = compute_new_5_factor_score(
        spec_score, avail_score, wait_score_b1, exp_score, 0.50
    )
    new_score_b2 = compute_new_5_factor_score(
        spec_score, avail_score, wait_score_b2, exp_score, 0.50
    )

    # In 5-factor model, Doctor B2 (short wait) has a definitive advantage over B1
    assert new_score_b2 > new_score_b1
    # Check that rating score has ZERO weight in the 5-factor weights
    assert "rating_reliability" not in RANKING_WEIGHTS


def test_scenario_c_extensive_experience_versus_limited_availability():
    """Scenario C: A doctor with extensive relevant experience but limited availability.
    
    Shows that availability (weight 0.25) takes precedence over experience (weight 0.10)
    for outpatient scheduling navigability.
    """
    spec_score = 1.0
    wait_score = 0.75  # 35 min
    pref_score = 0.50  # neutral

    # Doctor C1: 25 years clinical practice, but 0 available slots (avail = 0.10)
    exp_c1 = normalize_experience(25)     # 0.8333
    avail_c1 = normalize_availability(False, 0)  # 0.10

    # Doctor C2: 3 years clinical practice, but 5 open slots (avail = 1.00)
    exp_c2 = normalize_experience(3)      # 0.1000
    avail_c2 = normalize_availability(True, 5)   # 1.00

    new_score_c1 = compute_new_5_factor_score(spec_score, avail_c1, wait_score, exp_c1, pref_score)
    new_score_c2 = compute_new_5_factor_score(spec_score, avail_c2, wait_score, exp_c2, pref_score)

    # Doctor C2 ranks higher because availability contributes 0.25 vs experience 0.10
    assert new_score_c2 > new_score_c1
    avail_contrib_diff = 0.25 * (avail_c2 - avail_c1)
    exp_contrib_diff = 0.10 * (exp_c1 - exp_c2)
    assert avail_contrib_diff > exp_contrib_diff


def test_scenario_d_doctor_matches_explicit_preference():
    """Scenario D: A doctor who matches the patient's explicit preference."""
    spec_score = 1.0
    avail_score = 0.84
    wait_score = 0.75
    exp_score = 0.50

    # Doctor D1 matches patient's preferred doctor choice
    pref_score_d1 = normalize_preference(
        doctor_id="doc-d1", preferred_doctor_id="doc-d1"
    )  # 1.0
    # Doctor D2 does not match
    pref_score_d2 = normalize_preference(
        doctor_id="doc-d2", preferred_doctor_id="doc-d1"
    )  # 0.2

    new_score_d1 = compute_new_5_factor_score(spec_score, avail_score, wait_score, exp_score, pref_score_d1)
    new_score_d2 = compute_new_5_factor_score(spec_score, avail_score, wait_score, exp_score, pref_score_d2)

    assert pref_score_d1 == 1.0
    assert pref_score_d2 == 0.2
    assert new_score_d1 > new_score_d2
    assert round(new_score_d1 - new_score_d2, 4) == pytest.approx(0.10 * (1.0 - 0.2), abs=1e-4)


def test_scenario_e_mandatory_specialty_filter_cannot_be_bypassed(db_session: Session, rec_setup_data):
    """Scenario E: A doctor who lacks a mandatory specialty requirement.
    
    Verifies that high scores in other factors (experience, availability, etc.) CANNOT
    compensate for failing hard specialty eligibility filtering.
    """
    data = rec_setup_data
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    # Request cardiology recommendations
    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    rec_ids = [r.doctor_id for r in resp.recommendations]

    # Dermatology doctor (doc5) has 12 yrs exp, high availability, but lacks cardiology
    assert data["doc5"].id not in rec_ids
    assert resp.total_eligible_doctors == 2


def test_scenario_f_doctor_unavailable_when_availability_required(db_session: Session, rec_setup_data):
    """Scenario F: A doctor who is unavailable for a requested appointment."""
    data = rec_setup_data
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    # Date with no schedules configured
    future_date = datetime.date(2027, 1, 1)

    req_lenient = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
        appointment_date=future_date,
        require_availability=False,
    )
    resp_lenient = doctor_recommendation_service.recommend_doctors(db_session, req_lenient, user)
    # Lenient returns doctors with low availability score
    assert len(resp_lenient.recommendations) > 0

    req_strict = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
        appointment_date=future_date,
        require_availability=True,
    )
    resp_strict = doctor_recommendation_service.recommend_doctors(db_session, req_strict, user)
    # Strict excludes doctors without open slots at Stage A
    assert resp_strict.status == "NO_ELIGIBLE_DOCTORS"
    assert len(resp_strict.recommendations) == 0


def test_scenario_g_patient_without_language_preference():
    """Scenario G: A patient who has not specified a language preference.
    
    Verifies that language has NO independent effect on scores or rankings
    when the patient does not explicitly request a language.
    """
    # Doctor G1 speaks 3 languages
    langs_g1 = ["en", "es", "hi"]
    # Doctor G2 speaks 1 language
    langs_g2 = ["en"]

    pref_score_g1 = normalize_preference("doc-1", doctor_languages=langs_g1, preferred_language=None)
    pref_score_g2 = normalize_preference("doc-2", doctor_languages=langs_g2, preferred_language=None)

    # Both must receive exact identical neutral preference score
    assert pref_score_g1 == 0.50
    assert pref_score_g2 == 0.50

    score_g1 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_score_g1)
    score_g2 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_score_g2)

    # Identical scores: language creates zero differentiation
    assert score_g1 == score_g2


def test_scenario_h_patient_specifies_language_verified_and_missing_data():
    """Scenario H: A patient who specifies a language, with verified and missing doctor-language information.
    
    Verifies that:
    1. A doctor with verified matching language receives the explicit preference match.
    2. A doctor with missing language information is NOT assumed or invented to speak the language.
    3. A doctor with verified mismatch does not receive the match.
    """
    patient_preferred_lang = "es"

    # Doctor H1: verified Spanish
    pref_h1 = normalize_preference(
        "doc-h1", doctor_languages=["en", "es"], preferred_language=patient_preferred_lang
    )
    # Doctor H2: verified German only
    pref_h2 = normalize_preference(
        "doc-h2", doctor_languages=["en", "de"], preferred_language=patient_preferred_lang
    )
    # Doctor H3: missing/empty language information
    pref_h3 = normalize_preference(
        "doc-h3", doctor_languages=[], preferred_language=patient_preferred_lang
    )

    assert pref_h1 == 1.0  # Matched explicit preference
    assert pref_h2 == 0.2  # Mismatched
    assert pref_h3 == 0.2  # Missing language NOT assumed to match

    score_h1 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_h1)
    score_h2 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_h2)
    score_h3 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_h3)

    assert score_h1 > score_h2
    assert score_h1 > score_h3
    assert score_h2 == score_h3


def test_scenario_i_emergency_escalation_preserved(db_session: Session, rec_setup_data):
    """Scenario I: An emergency-escalated triage session.
    
    Verifies that the ranking system never downgrades an emergency or overrides triage escalation.
    """
    data = rec_setup_data
    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Sudden severe thunderclap headache, confusion",
        confirmed_input="Sudden severe thunderclap headache, confusion",
        language="en",
        status=TriageSessionStatus.ESCALATED,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assessment = TriageAssessment(
        triage_session_id=session.id,
        urgency=TriageUrgency.HIGH,
        confidence=1.0,
        needs_escalation=True,
        red_flag_detected=True,
        recommended_specialty_id=data["cardio"].id,
        rationale="Neurological/cardiovascular red-flag presentation",
    )
    db_session.add(assessment)
    db_session.commit()

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        triage_session_id=session.id,
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)

    # Emergency escalation must remain prominent and authoritative
    assert resp.status == "EMERGENCY_ESCALATION"
    assert resp.is_emergency_escalation is True
    assert "EMERGENCY SAFETY NOTICE" in resp.escalation_notice


# ============================================================================
# ARCHITECTURAL & SYSTEM VERIFICATION
# ============================================================================


def test_five_core_factors_and_exact_sum():
    """Verifies that the new model has exactly 5 factors and weights sum to 1.00."""
    assert len(RANKING_WEIGHTS) == 5
    assert sum(RANKING_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-6)

    expected = {
        "specialty_match": 0.35,
        "availability": 0.25,
        "predicted_wait": 0.20,
        "experience": 0.10,
        "patient_preference": 0.10,
    }
    assert RANKING_WEIGHTS == expected


def test_deterministic_scoring_reproducibility():
    """Verifies that identical inputs produce bitwise reproducible scores."""
    scores_1 = [compute_new_5_factor_score(1.0, 0.84, 0.75, 0.50, 0.50) for _ in range(10)]
    assert all(s == scores_1[0] for s in scores_1)
