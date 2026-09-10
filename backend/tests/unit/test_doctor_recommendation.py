import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
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
    assert RANKING_WEIGHTS["specialty_match"] == 0.30
    assert RANKING_WEIGHTS["availability"] == 0.20
    assert RANKING_WEIGHTS["predicted_wait"] == 0.15
    assert RANKING_WEIGHTS["experience"] == 0.10
    assert RANKING_WEIGHTS["rating_reliability"] == 0.10
    assert RANKING_WEIGHTS["patient_preference"] == 0.10
    assert RANKING_WEIGHTS["language_match"] == 0.05


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
    assert normalize_preference("doc-1", "doc-1", "both", None) == 1.0
    assert normalize_preference("doc-1", "doc-2", "both", None) == 0.2
    # Preferred mode match
    assert normalize_preference("doc-1", None, "both", "in_person") == 1.0
    assert normalize_preference("doc-1", None, "teleconsultation", "in_person") == 0.5
    # No preference specified (neutral)
    assert normalize_preference("doc-1", None, "both", None) == 0.5


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
    assert "language_match" in top_rec.matched_factors
    assert "reliable_rating" in top_rec.matched_factors

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
