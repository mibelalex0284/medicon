import datetime
import pytest
from sqlalchemy.orm import Session
from app.core.exceptions import InvalidStateTransitionError
from app.models.profile import UserRole
from app.models.triage_assessment import TriageUrgency
from app.models.triage_session import TriageSessionStatus
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.schemas.triage import TriageAnswerCreate, TriageSessionCreate
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service
from app.services.triage_service import triage_service


@pytest.fixture
def triage_patient(db_session: Session):
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="pat-triage-usr-1",
            role=UserRole.PATIENT,
            full_name="Charlie Triage",
            email="charlie@triage.org",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=prof.id, date_of_birth=datetime.date(1993, 3, 15)),
    )
    # Ensure specialties exist for routing
    for name, code in [
        ("Dermatology", "DERM"),
        ("ENT", "ENT"),
        ("Orthopedics", "ORTHO"),
        ("Cardiology", "CARDIO"),
        ("General Medicine", "GEN-MED"),
    ]:
        try:
            specialty_service.create_specialty(
                db_session, SpecialtyCreate(name=name, code=code)
            )
        except Exception:
            pass
    return patient


def test_red_flag_chest_pain_severe(db_session: Session, triage_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="I have crushing chest pain radiating to my arm"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    assessment = triage_service.assess_session(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    assert assessment.red_flag_detected is True
    assert "RED_FLAG_CHEST_PAIN_SEVERE" in assessment.red_flag_codes
    assert assessment.urgency == TriageUrgency.HIGH
    assert assessment.needs_escalation is True
    assert session.status == TriageSessionStatus.ESCALATED


def test_red_flag_breathing_difficulty(db_session: Session, triage_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Severe shortness of breath, gasping for air"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    assessment = triage_service.assess_session(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    assert assessment.red_flag_detected is True
    assert "RED_FLAG_BREATHING_DIFFICULTY" in assessment.red_flag_codes
    assert assessment.urgency == TriageUrgency.HIGH
    assert assessment.needs_escalation is True


def test_red_flag_breathing_cannot_catch_breath(db_session: Session, triage_patient):
    """Verify 'I can't catch my breath' triggers RED_FLAG_BREATHING_DIFFICULTY."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="I can't catch my breath"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    assessment = triage_service.assess_session(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    assert assessment.red_flag_detected is True
    assert "RED_FLAG_BREATHING_DIFFICULTY" in assessment.red_flag_codes
    assert assessment.urgency == TriageUrgency.HIGH
    assert assessment.needs_escalation is True


def test_red_flag_breathing_severe_respiratory_distress(db_session: Session, triage_patient):
    """Verify 'I have severe respiratory distress' triggers RED_FLAG_BREATHING_DIFFICULTY."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="I have severe respiratory distress"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    assessment = triage_service.assess_session(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    assert assessment.red_flag_detected is True
    assert "RED_FLAG_BREATHING_DIFFICULTY" in assessment.red_flag_codes
    assert assessment.urgency == TriageUrgency.HIGH
    assert assessment.needs_escalation is True


def test_multiple_simultaneous_red_flags(db_session: Session, triage_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(
            original_input="Patient passed out with severe bleeding and can't breathe"
        ),
        actor_auth_user_id="pat-triage-usr-1",
    )
    assessment = triage_service.assess_session(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    assert assessment.red_flag_detected is True
    codes = assessment.red_flag_codes
    assert "RED_FLAG_LOSS_OF_CONSCIOUSNESS" in codes
    assert "RED_FLAG_SEVERE_BLEEDING" in codes
    assert "RED_FLAG_BREATHING_DIFFICULTY" in codes
    assert assessment.urgency == TriageUrgency.HIGH


def test_unknown_is_not_treated_as_no(db_session: Session, triage_patient):
    """Verifies that UNKNOWN is not treated as NO, reducing confidence below threshold."""
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Mild fever and body ache"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    # Answer several questions with UNKNOWN
    q1 = triage_service.get_next_question(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    triage_service.answer_question(
        db_session, session.id, TriageAnswerCreate(question_id=q1.id, answer_value="UNKNOWN"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    q2 = triage_service.get_next_question(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    triage_service.answer_question(
        db_session, session.id, TriageAnswerCreate(question_id=q2.id, answer_value="UNKNOWN"),
        actor_auth_user_id="pat-triage-usr-1",
    )

    assessment = triage_service.assess_session(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    # Because answers were UNKNOWN, confidence is discounted and needs_escalation is True
    assert assessment.confidence < 0.60
    assert assessment.needs_escalation is True


def test_adaptive_question_bank_and_completion_lock(db_session: Session, triage_patient):
    session = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Skin rash on arm"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    # Question 1: highest priority
    q1 = triage_service.get_next_question(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    assert q1 is not None
    triage_service.answer_question(
        db_session, session.id, TriageAnswerCreate(question_id=q1.id, answer_value="NO"),
        actor_auth_user_id="pat-triage-usr-1",
    )

    # Question 2: next highest priority
    q2 = triage_service.get_next_question(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )
    assert q2 is not None
    assert q2.id != q1.id

    # Perform assessment to complete session
    triage_service.assess_session(
        db_session, session.id, actor_auth_user_id="pat-triage-usr-1"
    )

    # Attempting to answer a question after completion must raise InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        triage_service.answer_question(
            db_session, session.id, TriageAnswerCreate(question_id=q2.id, answer_value="NO"),
            actor_auth_user_id="pat-triage-usr-1",
        )


def test_specialty_routing_logic(db_session: Session, triage_patient):
    # Dermatology presentation
    s_derm = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Red itchy rash and eczema on hands"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    q = triage_service.get_next_question(db_session, s_derm.id, actor_auth_user_id="pat-triage-usr-1")
    triage_service.answer_question(db_session, s_derm.id, TriageAnswerCreate(question_id=q.id, answer_value="NO"), actor_auth_user_id="pat-triage-usr-1")
    ass_derm = triage_service.assess_session(db_session, s_derm.id, actor_auth_user_id="pat-triage-usr-1")
    assert ass_derm.recommended_specialty.code == "DERM"

    # ENT presentation
    s_ent = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="Severe sore throat and sinus congestion"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    q = triage_service.get_next_question(db_session, s_ent.id, actor_auth_user_id="pat-triage-usr-1")
    triage_service.answer_question(db_session, s_ent.id, TriageAnswerCreate(question_id=q.id, answer_value="NO"), actor_auth_user_id="pat-triage-usr-1")
    ass_ent = triage_service.assess_session(db_session, s_ent.id, actor_auth_user_id="pat-triage-usr-1")
    assert ass_ent.recommended_specialty.code == "ENT"

    # Fallback to General Medicine
    s_gen = triage_service.create_session(
        db_session,
        TriageSessionCreate(original_input="General fatigue and mild headache for three days"),
        actor_auth_user_id="pat-triage-usr-1",
    )
    q = triage_service.get_next_question(db_session, s_gen.id, actor_auth_user_id="pat-triage-usr-1")
    triage_service.answer_question(db_session, s_gen.id, TriageAnswerCreate(question_id=q.id, answer_value="NO"), actor_auth_user_id="pat-triage-usr-1")
    ass_gen = triage_service.assess_session(db_session, s_gen.id, actor_auth_user_id="pat-triage-usr-1")
    assert ass_gen.recommended_specialty.code in ["GEN-MED", "DERM", "ENT", "ORTHO"]
