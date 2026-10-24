import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSession, TriageSessionStatus
from app.ranking.constants import (
    RANKING_WEIGHTS,
    RATING_GLOBAL_PRIOR,
    RATING_NEUTRAL_SCORE,
    RATING_SHRINKAGE_M,
)
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
from app.schemas.doctor_schedule import DoctorScheduleCreate
from app.schemas.doctor_specialty import DoctorSpecialtyCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.schemas.triage import TriageSessionCreate
from app.schemas.doctor_recommendation import DoctorRecommendationRequest
from app.services.doctor_recommendation_service import doctor_recommendation_service
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.services.triage_service import triage_service
from app.repositories.triage_repository import triage_repo
from app.models.triage_assessment import TriageAssessment


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def rec_setup_data(db_session: Session):
    """Creates test hospitals, specialties, patient, and diverse doctor profiles."""
    hosp_a = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Metro General Hospital", code="MGH-01")
    )
    hosp_b = hospital_service.create_hospital(
        db_session, HospitalCreate(name="St. Jude Clinic", code="SJC-02")
    )

    cardio = specialty_service.create_specialty(
        db_session, SpecialtyCreate(name="Cardiology", code="CARDIO")
    )
    derm = specialty_service.create_specialty(
        db_session, SpecialtyCreate(name="Dermatology", code="DERM")
    )

    # Patient in hosp_a
    p_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Alice Walker",
            email="alice@care.org",
            hospital_id=hosp_a.id,
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=p_prof.id,
            date_of_birth=datetime.date(1990, 5, 20),
        ),
    )

    # Other patient
    p_prof2 = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-999",
            role=UserRole.PATIENT,
            full_name="Bob Stranger",
            email="bob@care.org",
            hospital_id=hosp_a.id,
        ),
    )
    other_patient = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=p_prof2.id,
            date_of_birth=datetime.date(1985, 3, 15),
        ),
    )

    # Doctor 1: High reviews, primary cardio, experienced, in_person
    d1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-1",
            role=UserRole.DOCTOR,
            full_name="Dr. Sarah Connor",
            email="sarah@mgh.org",
            hospital_id=hosp_a.id,
        ),
    )
    doc1 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=d1_prof.id,
            hospital_id=hosp_a.id,
            license_number="LIC-CARDIO-001",
            years_of_experience=15,
            consultation_mode="both",
            average_rating=4.7,
            rating_count=100,
            languages="en,es",
            is_active=True,
        ),
    )
    doctor_service.assign_specialty(
        db_session,
        doc1.id,
        DoctorSpecialtyCreate(
            doctor_id=doc1.id, specialty_id=cardio.id, is_primary=True
        ),
    )

    # Doctor 2: Inflated rating (4.9 with only 2 reviews), secondary cardio, novice
    d2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-2",
            role=UserRole.DOCTOR,
            full_name="Dr. Kyle Reese",
            email="kyle@mgh.org",
            hospital_id=hosp_a.id,
        ),
    )
    doc2 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=d2_prof.id,
            hospital_id=hosp_a.id,
            license_number="LIC-CARDIO-002",
            years_of_experience=3,
            consultation_mode="teleconsultation",
            average_rating=4.9,
            rating_count=2,
            languages="en",
            is_active=True,
        ),
    )
    doctor_service.assign_specialty(
        db_session,
        doc2.id,
        DoctorSpecialtyCreate(
            doctor_id=doc2.id, specialty_id=cardio.id, is_primary=False
        ),
    )

    # Doctor 3: Hospital B (should be filtered out by tenant isolation)
    d3_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-3",
            role=UserRole.DOCTOR,
            full_name="Dr. Miles Dyson",
            email="miles@sjc.org",
            hospital_id=hosp_b.id,
        ),
    )
    doc3 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=d3_prof.id,
            hospital_id=hosp_b.id,
            license_number="LIC-CARDIO-003",
            years_of_experience=20,
            consultation_mode="both",
            average_rating=5.0,
            rating_count=50,
            languages="en",
            is_active=True,
        ),
    )
    doctor_service.assign_specialty(
        db_session,
        doc3.id,
        DoctorSpecialtyCreate(
            doctor_id=doc3.id, specialty_id=cardio.id, is_primary=True
        ),
    )

    # Doctor 4: Inactive doctor
    d4_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-4",
            role=UserRole.DOCTOR,
            full_name="Dr. John Inactive",
            email="inactive@mgh.org",
            hospital_id=hosp_a.id,
        ),
    )
    doc4 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=d4_prof.id,
            hospital_id=hosp_a.id,
            license_number="LIC-CARDIO-004",
            years_of_experience=10,
            consultation_mode="both",
            average_rating=4.5,
            rating_count=30,
            languages="en",
            is_active=False,
        ),
    )
    doctor_service.assign_specialty(
        db_session,
        doc4.id,
        DoctorSpecialtyCreate(
            doctor_id=doc4.id, specialty_id=cardio.id, is_primary=True
        ),
    )

    # Doctor 5: Dermatology specialist (wrong specialty for cardio queries)
    d5_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-5",
            role=UserRole.DOCTOR,
            full_name="Dr. Peter Skin",
            email="peter@mgh.org",
            hospital_id=hosp_a.id,
        ),
    )
    doc5 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=d5_prof.id,
            hospital_id=hosp_a.id,
            license_number="LIC-DERM-005",
            years_of_experience=12,
            consultation_mode="both",
            average_rating=4.8,
            rating_count=40,
            languages="en",
            is_active=True,
        ),
    )
    doctor_service.assign_specialty(
        db_session,
        doc5.id,
        DoctorSpecialtyCreate(
            doctor_id=doc5.id, specialty_id=derm.id, is_primary=True
        ),
    )

    return {
        "hosp_a": hosp_a,
        "hosp_b": hosp_b,
        "cardio": cardio,
        "derm": derm,
        "patient": patient,
        "other_patient": other_patient,
        "doc1": doc1,
        "doc2": doc2,
        "doc3": doc3,
        "doc4": doc4,
        "doc5": doc5,
    }


# ============================================================================
# UNIT TESTS: WEIGHTS & NORMALIZATION
# ============================================================================


def test_ranking_weights_sum_to_one():
    total_weight = sum(RANKING_WEIGHTS.values())
    assert total_weight == pytest.approx(1.0, abs=1e-6)
    assert len(RANKING_WEIGHTS) == 5
    assert RANKING_WEIGHTS["specialty_match"] == 0.35
    assert RANKING_WEIGHTS["availability"] == 0.25
    assert RANKING_WEIGHTS["predicted_wait"] == 0.20
    assert RANKING_WEIGHTS["experience"] == 0.10
    assert RANKING_WEIGHTS["patient_preference"] == 0.10
    assert "rating_reliability" not in RANKING_WEIGHTS
    assert "language_match" not in RANKING_WEIGHTS


def test_experience_normalization():
    assert normalize_experience(0) == 0.0
    assert normalize_experience(15) == 0.50
    assert normalize_experience(30) == 1.00
    assert normalize_experience(45) == 1.00  # Capped at 1.0


def test_wait_time_normalization():
    assert normalize_wait(5) == 1.0  # Minimal wait yields max score
    assert normalize_wait(35) == 0.75
    assert normalize_wait(65) == 0.50
    assert normalize_wait(125) == 0.0
    assert normalize_wait(180) == 0.0  # High wait bounded to 0.0


def test_specialty_normalization():
    assert normalize_specialty(is_primary=True) == 1.0
    assert normalize_specialty(is_primary=False) == 0.7


def test_preference_normalization():
    # Preferred doctor match
    assert normalize_preference("doc-1", preferred_doctor_id="doc-1") == 1.0
    assert normalize_preference("doc-1", preferred_doctor_id="doc-2") == 0.2
    # Preferred mode match
    assert normalize_preference("doc-1", preferred_mode="in_person", doctor_mode="both") == 1.0
    assert normalize_preference("doc-1", preferred_mode="in_person", doctor_mode="teleconsultation") == 0.5
    # No preference specified (neutral)
    assert normalize_preference("doc-1") == 0.5
    # Explicit language preference matching
    assert normalize_preference("doc-1", preferred_language="es", doctor_languages=["en", "es"]) == 1.0
    assert normalize_preference("doc-1", preferred_language="es", doctor_languages=["en"]) == 0.2
    assert normalize_preference("doc-1", preferred_language="es", doctor_languages=[]) == 0.2  # Missing language not assumed
    assert normalize_preference("doc-1", preferred_language=None, doctor_languages=["en"]) == 0.5  # Neutral if not requested


def test_language_normalization():
    assert normalize_language(["en", "es"], "es") == 1.0
    assert normalize_language(["en", "es"], "fr") == 0.0
    # No language requested yields neutral score
    assert normalize_language(["en", "es"], None) == 0.5
    assert normalize_language(["en", "es"], "") == 0.5


def test_rating_reliability_bayesian_shrinkage():
    # 4.9 from 2 reviews:
    # adjusted = (2 / 12) * 4.9 + (10 / 12) * 4.0 = 0.8167 + 3.3333 = 4.15 -> score = 0.8300
    score_few_reviews = normalize_rating_reliability(average_rating=4.9, rating_count=2)

    # 4.7 from 100 reviews:
    # adjusted = (100 / 110) * 4.7 + (10 / 110) * 4.0 = 4.2727 + 0.3636 = 4.6364 -> score = 0.9273
    score_many_reviews = normalize_rating_reliability(average_rating=4.7, rating_count=100)

    # Crucial test: 4.7 with 100 reviews MUST score higher than 4.9 with 2 reviews!
    assert score_many_reviews > score_few_reviews

    # Unrated doctor (0 reviews) receives neutral score (0.80) rather than being penalized to 0.0
    assert normalize_rating_reliability(average_rating=0.0, rating_count=0) == RATING_NEUTRAL_SCORE


# ============================================================================
# SERVICE TESTS: ELIGIBILITY & RANKING
# ============================================================================


def test_hard_eligibility_filtering(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)

    assert resp.status == "SUCCESS"
    assert resp.total_eligible_doctors == 2  # Only doc1 and doc2 in hosp_a with cardio
    rec_ids = [r.doctor_id for r in resp.recommendations]

    # Inactive doc4 must NOT be included
    assert data["doc4"].id not in rec_ids

    # Hospital B doc3 must NOT be included
    assert data["doc3"].id not in rec_ids

    # Dermatology doc5 must NOT be included
    assert data["doc5"].id not in rec_ids

    # Eligible doc1 and doc2 must be included
    assert data["doc1"].id in rec_ids
    assert data["doc2"].id in rec_ids


def test_consultation_mode_filtering(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    # Request strictly 'in_person'
    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
        consultation_mode="in_person",
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    rec_ids = [r.doctor_id for r in resp.recommendations]

    # doc1 is 'both' -> eligible for in_person
    assert data["doc1"].id in rec_ids
    # doc2 is 'teleconsultation' only -> excluded from in_person
    assert data["doc2"].id not in rec_ids


def test_primary_specialty_and_reliability_ranking_order(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    assert len(resp.recommendations) == 2

    top_rec = resp.recommendations[0]
    second_rec = resp.recommendations[1]

    # Dr. Sarah Connor (doc1) has primary cardio + 15 yrs experience + 100 reviews
    # Dr. Kyle Reese (doc2) has secondary cardio + 3 yrs experience + 2 reviews
    assert top_rec.doctor_id == data["doc1"].id
    assert top_rec.rank == 1
    assert top_rec.score > second_rec.score
    assert second_rec.doctor_id == data["doc2"].id


def test_deterministic_tie_breaking(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
    )

    # Multiple calls must return identical order and scores
    resp1 = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    resp2 = doctor_recommendation_service.recommend_doctors(db_session, req, user)

    order1 = [(r.rank, r.doctor_id, r.score) for r in resp1.recommendations]
    order2 = [(r.rank, r.doctor_id, r.score) for r in resp2.recommendations]

    assert order1 == order2


def test_structured_explanation_integrity(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
        preferred_language="es",
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    top_rec = resp.recommendations[0]

    # Verify structured factors
    assert "specialty_primary" in top_rec.matched_factors
    assert "patient_preference" in top_rec.matched_factors
    assert "language_match" in top_rec.matched_factors
    assert "reliable_rating" not in top_rec.matched_factors

    # Verify explanation string contains truth and NO superlatives
    exp = top_rec.explanation.lower()
    assert "recommended because" in exp
    assert "cardiology" in exp
    assert "best doctor" not in exp
    assert "medically superior" not in exp
    assert "most qualified" not in exp


def test_no_eligible_doctors_response(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    # Create a specialty with no doctors in hospital A (e.g. Neurology)
    neuro = specialty_service.create_specialty(
        db_session, SpecialtyCreate(name="Neurology", code="NEURO")
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=neuro.id,
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    assert resp.status == "NO_ELIGIBLE_DOCTORS"
    assert resp.total_eligible_doctors == 0
    assert len(resp.recommendations) == 0
    assert "No eligible doctors" in resp.message


# ============================================================================
# TRIAGE SESSION INTEGRATION & SECURITY TESTS
# ============================================================================


def test_triage_session_integration_success(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser
    from app.models.triage_session import TriageSession

    # 1. Create a completed triage session for patient
    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Chest tightness, shortness of breath, palpitations",
        confirmed_input="Chest tightness, shortness of breath, palpitations",
        language="en",
        status=TriageSessionStatus.COMPLETED,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    # Manually attach assessment with recommended specialty
    assessment = TriageAssessment(
        triage_session_id=session.id,
        urgency=TriageUrgency.MODERATE,
        confidence=0.85,
        needs_escalation=False,
        red_flag_detected=False,
        recommended_specialty_id=data["cardio"].id,
        rationale="Cardiovascular symptom presentation",
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
    assert resp.status == "SUCCESS"
    assert resp.applied_specialty_id == data["cardio"].id
    assert len(resp.recommendations) > 0


def test_cross_patient_triage_session_access_rejected(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser
    from app.models.triage_session import TriageSession

    # Session belongs to 'patient'
    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Skin irritation and redness",
        confirmed_input="Skin irritation and redness",
        language="en",
        status=TriageSessionStatus.COMPLETED,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assessment = TriageAssessment(
        triage_session_id=session.id,
        urgency=TriageUrgency.LOW,
        confidence=0.90,
        needs_escalation=False,
        red_flag_detected=False,
        recommended_specialty_id=data["derm"].id,
        rationale="Dermatology presentation",
    )
    db_session.add(assessment)
    db_session.commit()

    # Other patient tries to query using this session
    other_user = AuthenticatedUser(
        id=data["other_patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        triage_session_id=session.id,
    )

    with pytest.raises(ForbiddenError) as exc_info:
        doctor_recommendation_service.recommend_doctors(db_session, req, other_user)

    assert "does not belong" in str(exc_info.value.message)


def test_emergency_escalation_preserved(db_session: Session, rec_setup_data):
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser
    from app.models.triage_session import TriageSession

    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Crushing chest pain radiating to arm",
        confirmed_input="Crushing chest pain radiating to arm",
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
        rationale="Severe red flag cardiac emergency",
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
    # Urgency must NOT be downgraded
    assert resp.status == "EMERGENCY_ESCALATION"
    assert resp.is_emergency_escalation is True
    assert resp.escalation_notice is not None
    assert "EMERGENCY SAFETY NOTICE" in resp.escalation_notice


# ============================================================================
# API INTEGRATION TESTS (TestClient)
# ============================================================================


def test_api_recommend_endpoint_success(client: TestClient, rec_setup_data, patient_headers):
    data = rec_setup_data

    payload = {
        "hospital_id": data["hosp_a"].id,
        "specialty_id": data["cardio"].id,
        "consultation_mode": "both",
    }

    res = client.post("/api/v1/doctors/recommend", json=payload, headers=patient_headers)
    assert res.status_code == 200
    data_out = res.json()
    assert data_out["status"] == "SUCCESS"
    assert len(data_out["recommendations"]) >= 1
    assert data_out["recommendations"][0]["score"] > 0.0


def test_api_recommend_unauthenticated_rejected(client: TestClient, rec_setup_data):
    payload = {
        "hospital_id": rec_setup_data["hosp_a"].id,
        "specialty_id": rec_setup_data["cardio"].id,
    }
    res = client.post("/api/v1/doctors/recommend", json=payload)
    assert res.status_code == 401


# ============================================================================
# DETERMINISTIC COMPARISON SCENARIOS A THROUGH I (STEP 7)
# ============================================================================


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
    from app.ranking.constants import (
        WEIGHT_SPECIALTY_MATCH,
        WEIGHT_AVAILABILITY,
        WEIGHT_PREDICTED_WAIT,
        WEIGHT_EXPERIENCE,
        WEIGHT_PATIENT_PREFERENCE,
    )
    score = (
        WEIGHT_SPECIALTY_MATCH * spec_score
        + WEIGHT_AVAILABILITY * avail_score
        + WEIGHT_PREDICTED_WAIT * wait_score
        + WEIGHT_EXPERIENCE * exp_score
        + WEIGHT_PATIENT_PREFERENCE * pref_score
    )
    return round(score, 4)


def test_scenario_a_equally_eligible_different_wait_times():
    """Scenario A: Two equally eligible doctors with different waiting times."""
    spec_score = 1.0
    avail_score = 1.0
    exp_score = 0.50
    pref_score = 0.50

    wait_score_1 = normalize_wait(15)  # 15 min wait
    wait_score_2 = normalize_wait(65)  # 65 min wait

    old_score_1 = compute_old_7_factor_score(spec_score, avail_score, wait_score_1, exp_score, 0.80, pref_score, 0.50)
    old_score_2 = compute_old_7_factor_score(spec_score, avail_score, wait_score_2, exp_score, 0.80, pref_score, 0.50)

    new_score_1 = compute_new_5_factor_score(spec_score, avail_score, wait_score_1, exp_score, pref_score)
    new_score_2 = compute_new_5_factor_score(spec_score, avail_score, wait_score_2, exp_score, pref_score)

    assert new_score_1 > new_score_2
    assert old_score_1 > old_score_2
    # Score difference is strictly higher in 5-factor model (0.20 wait weight vs 0.15)
    assert round(new_score_1 - new_score_2, 4) > round(old_score_1 - old_score_2, 4)


def test_scenario_b_excellent_ratings_versus_longer_wait():
    """Scenario B: A doctor with excellent ratings but a longer wait."""
    spec_score = 1.0
    avail_score = 0.84
    exp_score = 0.40

    rating_b1 = normalize_rating_reliability(4.9, 100)
    wait_b1 = normalize_wait(75)

    rating_b2 = normalize_rating_reliability(3.5, 5)
    wait_b2 = normalize_wait(10)

    new_score_b1 = compute_new_5_factor_score(spec_score, avail_score, wait_b1, exp_score, 0.50)
    new_score_b2 = compute_new_5_factor_score(spec_score, avail_score, wait_b2, exp_score, 0.50)

    # Doctor B2 with shorter wait ranks higher in 5-factor model because ratings are excluded
    assert new_score_b2 > new_score_b1
    assert "rating_reliability" not in RANKING_WEIGHTS


def test_scenario_c_extensive_experience_versus_limited_availability():
    """Scenario C: A doctor with extensive relevant experience but limited availability."""
    spec_score = 1.0
    wait_score = 0.75
    pref_score = 0.50

    exp_c1 = normalize_experience(25)     # 25 yrs
    avail_c1 = normalize_availability(False, 0)  # 0 slots (0.10)

    exp_c2 = normalize_experience(3)      # 3 yrs
    avail_c2 = normalize_availability(True, 5)   # 5 slots (1.00)

    new_score_c1 = compute_new_5_factor_score(spec_score, avail_c1, wait_score, exp_c1, pref_score)
    new_score_c2 = compute_new_5_factor_score(spec_score, avail_c2, wait_score, exp_c2, pref_score)

    # Doctor C2 ranks higher because availability is 0.25 vs experience 0.10
    assert new_score_c2 > new_score_c1


def test_scenario_d_doctor_matches_explicit_preference():
    """Scenario D: A doctor who matches the patient's explicit preference."""
    pref_score_match = normalize_preference("doc-1", preferred_doctor_id="doc-1")
    pref_score_mismatch = normalize_preference("doc-2", preferred_doctor_id="doc-1")

    assert pref_score_match == 1.0
    assert pref_score_mismatch == 0.2

    score_match = compute_new_5_factor_score(1.0, 0.84, 0.75, 0.50, pref_score_match)
    score_mismatch = compute_new_5_factor_score(1.0, 0.84, 0.75, 0.50, pref_score_mismatch)

    assert score_match > score_mismatch


def test_scenario_e_mandatory_specialty_filter_cannot_be_bypassed(db_session: Session, rec_setup_data):
    """Scenario E: A doctor who lacks a mandatory specialty requirement."""
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
    )

    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    rec_ids = [r.doctor_id for r in resp.recommendations]

    assert data["doc5"].id not in rec_ids  # Derm doc excluded
    assert data["doc1"].id in rec_ids      # Cardio doc included


def test_scenario_f_doctor_unavailable_when_availability_required(db_session: Session, rec_setup_data):
    """Scenario F: A doctor who is unavailable for a requested appointment."""
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    future_date = datetime.date(2027, 1, 1)
    req_strict = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
        appointment_date=future_date,
        require_availability=True,
    )
    resp = doctor_recommendation_service.recommend_doctors(db_session, req_strict, user)
    assert resp.status == "NO_ELIGIBLE_DOCTORS"
    assert len(resp.recommendations) == 0


def test_scenario_g_patient_without_language_preference():
    """Scenario G: A patient who has not specified a language preference."""
    pref_score_1 = normalize_preference("doc-1", doctor_languages=["en", "es", "hi"], preferred_language=None)
    pref_score_2 = normalize_preference("doc-2", doctor_languages=["en"], preferred_language=None)

    assert pref_score_1 == 0.50
    assert pref_score_2 == 0.50

    score_1 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_score_1)
    score_2 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_score_2)

    assert score_1 == score_2


def test_scenario_h_patient_specifies_language_verified_and_missing_data():
    """Scenario H: A patient who specifies a language, with verified and missing doctor-language information."""
    pref_h1 = normalize_preference("doc-1", doctor_languages=["en", "es"], preferred_language="es")
    pref_h2 = normalize_preference("doc-2", doctor_languages=["en", "fr"], preferred_language="es")
    pref_h3 = normalize_preference("doc-3", doctor_languages=[], preferred_language="es")

    assert pref_h1 == 1.0
    assert pref_h2 == 0.2
    assert pref_h3 == 0.2

    score_h1 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_h1)
    score_h2 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_h2)
    score_h3 = compute_new_5_factor_score(1.0, 1.0, 0.75, 0.50, pref_h3)

    assert score_h1 > score_h2
    assert score_h1 > score_h3
    assert score_h2 == score_h3


def test_scenario_i_emergency_escalation_preserved(db_session: Session, rec_setup_data):
    """Scenario I: An emergency-escalated triage session."""
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Severe acute crushing chest pain",
        confirmed_input="Severe acute crushing chest pain",
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
        rationale="Cardiac red flag symptoms",
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
    assert resp.status == "EMERGENCY_ESCALATION"
    assert resp.is_emergency_escalation is True
    assert "EMERGENCY SAFETY NOTICE" in resp.escalation_notice


def test_high_urgency_without_emergency_allows_doctor_recommendation(db_session: Session, rec_setup_data):
    """Regression Test 1: HIGH urgency with NO emergency determination allows doctor recommendations and booking."""
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Bilateral leg pain for three days, sharp, severity 5/10, no swelling, affecting activities",
        confirmed_input="Bilateral leg pain for three days, sharp, severity 5/10, no swelling, affecting activities",
        language="en",
        status=TriageSessionStatus.COMPLETED,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    assessment = TriageAssessment(
        triage_session_id=session.id,
        urgency=TriageUrgency.HIGH,
        confidence=0.90,
        needs_escalation=False,
        red_flag_detected=False,
        recommended_specialty_id=data["cardio"].id,
        rationale="Elevated pain severity affecting daily activities without acute red flags",
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

    # Must NOT be classified as emergency escalation
    assert resp.is_emergency_escalation is False
    assert resp.status == "SUCCESS"
    assert resp.urgency == TriageUrgency.HIGH
    assert resp.total_eligible_doctors > 0
    assert len(resp.recommendations) > 0

    # Notice provides high urgency clinical guidance without blocking
    assert resp.escalation_notice is not None
    assert "HIGH CLINICAL URGENCY" in resp.escalation_notice
    assert "prompt / urgent consultation" in resp.escalation_notice
    # Safeguard: note that absence of red flags does not guarantee safety
    assert "Absence of red-flag symptoms does not guarantee safety" in resp.escalation_notice


def test_guidance_coherence_across_urgency_tiers(db_session: Session, rec_setup_data):
    """Regression Test 2: Clinical guidance is coherent with urgency classification and never contradicts it."""
    data = rec_setup_data

    # High Urgency (Non-emergency)
    high_assessment = TriageAssessment(
        triage_session_id="test-session-high",
        urgency=TriageUrgency.HIGH,
        confidence=0.85,
        needs_escalation=False,
        red_flag_detected=False,
    )
    assert "routine care navigation" not in high_assessment.guidance
    assert "prompt outpatient clinical evaluation" in high_assessment.guidance
    assert "does not guarantee safety" in high_assessment.guidance

    # Moderate Urgency
    mod_assessment = TriageAssessment(
        triage_session_id="test-session-mod",
        urgency=TriageUrgency.MODERATE,
        confidence=0.85,
        needs_escalation=False,
        red_flag_detected=False,
    )
    assert "timely outpatient clinical evaluation" in mod_assessment.guidance

    # Low Urgency
    low_assessment = TriageAssessment(
        triage_session_id="test-session-low",
        urgency=TriageUrgency.LOW,
        confidence=0.85,
        needs_escalation=False,
        red_flag_detected=False,
    )
    assert "routine care navigation" in low_assessment.guidance

    # True Emergency
    emerg_assessment = TriageAssessment(
        triage_session_id="test-session-emerg",
        urgency=TriageUrgency.HIGH,
        confidence=1.0,
        needs_escalation=True,
        red_flag_detected=True,
    )
    assert "Emergency warning signs" in emerg_assessment.guidance


def test_low_and_moderate_urgency_pathways(db_session: Session, rec_setup_data):
    """Regression Test 3: LOW and MODERATE urgency sessions return normal recommendations."""
    data = rec_setup_data
    from app.core.dependencies import AuthenticatedUser

    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=data["hosp_a"].id,
    )

    for urg in [TriageUrgency.LOW, TriageUrgency.MODERATE]:
        session = TriageSession(
            patient_id=data["patient"].id,
            original_input=f"Sample symptoms for {urg.value}",
            confirmed_input=f"Sample symptoms for {urg.value}",
            language="en",
            status=TriageSessionStatus.COMPLETED,
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assessment = TriageAssessment(
            triage_session_id=session.id,
            urgency=urg,
            confidence=0.90,
            needs_escalation=False,
            red_flag_detected=False,
            recommended_specialty_id=data["cardio"].id,
            rationale="Routine symptoms",
        )
        db_session.add(assessment)
        db_session.commit()

        req = DoctorRecommendationRequest(
            hospital_id=data["hosp_a"].id,
            triage_session_id=session.id,
        )

        resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
        assert resp.is_emergency_escalation is False
        assert resp.status == "SUCCESS"
        assert resp.urgency == urg
        assert resp.total_eligible_doctors > 0
        assert len(resp.recommendations) > 0


# ============================================================================
# PHASE 4 HOSPITAL CONTEXT & RESOLUTION REGRESSION TESTS
# ============================================================================


def test_recommendations_when_valid_hospital_id_supplied(db_session: Session, rec_setup_data):
    """When a valid hospital ID is supplied explicitly, recommendations are resolved for that facility."""
    from app.core.dependencies import AuthenticatedUser
    data = rec_setup_data
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=None,
    )
    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
    )
    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    assert resp.status == "SUCCESS"
    assert resp.applied_hospital_id == data["hosp_a"].id
    assert len(resp.recommendations) >= 1
    for item in resp.recommendations:
        assert item.doctor.hospital_id == data["hosp_a"].id


def test_recommendations_when_profile_provides_hospital_id(db_session: Session, rec_setup_data):
    """When request omits hospital_id, resolves to the hospital from user's application profile."""
    from app.core.dependencies import AuthenticatedUser
    data = rec_setup_data
    # Patient profile has hospital_id = hosp_a
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=None,  # Not in token
    )
    req = DoctorRecommendationRequest(
        hospital_id=None,
        specialty_id=data["cardio"].id,
    )
    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    assert resp.status == "SUCCESS"
    assert resp.applied_hospital_id == data["hosp_a"].id
    assert len(resp.recommendations) >= 1


def test_missing_hospital_context_raises_missing_hospital_context_error(db_session: Session, rec_setup_data):
    """When neither request nor profile has a hospital affiliation, raises ConflictError with MISSING_HOSPITAL_CONTEXT."""
    from app.core.dependencies import AuthenticatedUser
    from app.models.profile import Profile
    data = rec_setup_data

    # Unaffiliated patient with no hospital in profile
    unaffiliated_prof = Profile(
        auth_user_id="unaffiliated-pat-01",
        role=UserRole.PATIENT,
        full_name="Unaffiliated Patient",
        email="unaffiliated@care.org",
        hospital_id=None,
        is_active=True,
    )
    db_session.add(unaffiliated_prof)
    db_session.commit()

    user = AuthenticatedUser(
        id=unaffiliated_prof.auth_user_id,
        role="patient",
        hospital_id=None,
    )
    req = DoctorRecommendationRequest(
        hospital_id=None,
        specialty_id=data["cardio"].id,
    )

    with pytest.raises(ConflictError) as exc_info:
        doctor_recommendation_service.recommend_doctors(db_session, req, user)

    assert exc_info.value.code == "MISSING_HOSPITAL_CONTEXT"
    assert "hospital" in exc_info.value.message.lower()


def test_invalid_or_inactive_hospital_id_raises_not_found(db_session: Session, rec_setup_data):
    """Supplying a non-existent or inactive hospital ID raises NotFoundError."""
    from app.core.dependencies import AuthenticatedUser
    data = rec_setup_data
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=None,
    )
    req = DoctorRecommendationRequest(
        hospital_id="non-existent-facility-id",
        specialty_id=data["cardio"].id,
    )
    with pytest.raises(NotFoundError) as exc_info:
        doctor_recommendation_service.recommend_doctors(db_session, req, user)

    assert exc_info.value.code == "HOSPITAL_NOT_FOUND"


def test_unauthorized_cross_hospital_id_raises_forbidden(db_session: Session, rec_setup_data):
    """Patient with a registered hospital profile cannot request doctors from a different hospital facility."""
    from app.core.dependencies import AuthenticatedUser
    data = rec_setup_data
    # Patient is registered with hosp_a
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=None,
    )
    # Tries to request hosp_b
    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_b"].id,
        specialty_id=data["cardio"].id,
    )
    with pytest.raises(ForbiddenError) as exc_info:
        doctor_recommendation_service.recommend_doctors(db_session, req, user)

    assert exc_info.value.code == "FORBIDDEN_CROSS_HOSPITAL_ACCESS"


def test_patient_selecting_hospital_and_retrying_recommendations(db_session: Session, rec_setup_data):
    """An unaffiliated patient who initially lacks hospital context successfully selects a facility and gets recommendations."""
    from app.core.dependencies import AuthenticatedUser
    from app.models.profile import Profile
    data = rec_setup_data

    prof = Profile(
        auth_user_id="unaffiliated-retry-pat",
        role=UserRole.PATIENT,
        full_name="Retry Patient",
        email="retry@care.org",
        hospital_id=None,
        is_active=True,
    )
    db_session.add(prof)
    db_session.commit()

    user = AuthenticatedUser(
        id=prof.auth_user_id,
        role="patient",
        hospital_id=None,
    )

    # 1. Initial attempt without hospital fails with MISSING_HOSPITAL_CONTEXT
    req_initial = DoctorRecommendationRequest(
        hospital_id=None,
        specialty_id=data["cardio"].id,
    )
    with pytest.raises(ConflictError) as exc_info:
        doctor_recommendation_service.recommend_doctors(db_session, req_initial, user)
    assert exc_info.value.code == "MISSING_HOSPITAL_CONTEXT"

    # 2. Patient selects hosp_a and retries request
    req_retry = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        specialty_id=data["cardio"].id,
    )
    resp = doctor_recommendation_service.recommend_doctors(db_session, req_retry, user)
    assert resp.status == "SUCCESS"
    assert resp.applied_hospital_id == data["hosp_a"].id
    assert len(resp.recommendations) > 0


def test_preservation_of_triage_session_context(db_session: Session, rec_setup_data):
    """Triage assessment specialty and rationale are faithfully preserved across hospital selection."""
    from app.core.dependencies import AuthenticatedUser
    data = rec_setup_data
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=None,
    )

    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Chest tightness and irregular palpitation",
        confirmed_input="Chest tightness and irregular palpitation",
        language="en",
        status=TriageSessionStatus.COMPLETED,
    )
    db_session.add(session)
    db_session.commit()

    assessment = TriageAssessment(
        triage_session_id=session.id,
        urgency=TriageUrgency.MODERATE,
        confidence=0.92,
        needs_escalation=False,
        red_flag_detected=False,
        recommended_specialty_id=data["cardio"].id,
        rationale="Cardiovascular symptoms warrant specialized evaluation.",
    )
    db_session.add(assessment)
    db_session.commit()

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        triage_session_id=session.id,
    )
    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    assert resp.applied_specialty_id == data["cardio"].id
    assert resp.applied_specialty_name == "Cardiology"
    assert resp.urgency == TriageUrgency.MODERATE
    assert resp.is_emergency_escalation is False
    assert len(resp.recommendations) > 0


def test_red_flag_emergency_routing_behavior_preserved(db_session: Session, rec_setup_data):
    """Critical red-flag symptoms trigger EMERGENCY_ESCALATION notice with emergency guidance."""
    from app.core.dependencies import AuthenticatedUser
    data = rec_setup_data
    user = AuthenticatedUser(
        id=data["patient"].profile.auth_user_id,
        role="patient",
        hospital_id=None,
    )

    session = TriageSession(
        patient_id=data["patient"].id,
        original_input="Sudden crushing chest pain radiating to left arm",
        confirmed_input="Sudden crushing chest pain radiating to left arm",
        language="en",
        status=TriageSessionStatus.COMPLETED,
    )
    db_session.add(session)
    db_session.commit()

    assessment = TriageAssessment(
        triage_session_id=session.id,
        urgency=TriageUrgency.HIGH,
        confidence=0.98,
        needs_escalation=True,
        red_flag_detected=True,
        recommended_specialty_id=data["cardio"].id,
        rationale="Classic cardiac red-flag emergency symptoms.",
    )
    db_session.add(assessment)
    db_session.commit()

    req = DoctorRecommendationRequest(
        hospital_id=data["hosp_a"].id,
        triage_session_id=session.id,
    )
    resp = doctor_recommendation_service.recommend_doctors(db_session, req, user)
    assert resp.status == "EMERGENCY_ESCALATION"
    assert resp.is_emergency_escalation is True
    assert "emergency" in resp.escalation_notice.lower()



