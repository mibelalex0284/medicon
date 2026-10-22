from datetime import date, time
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.core.exceptions import ConflictError, InvalidStateTransitionError, NotFoundError
from app.models.profile import UserRole
from app.schemas.department import DepartmentCreate
from app.schemas.doctor import DoctorCreate
from app.schemas.doctor_schedule import DoctorScheduleBase, DoctorScheduleCreate
from app.schemas.doctor_specialty import DoctorSpecialtyCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.services.department_service import department_service
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service


def test_valid_profile_creation(db_session: Session):
    prof_in = ProfileCreate(
        auth_user_id="auth-test-1",
        role=UserRole.PATIENT,
        full_name="Alice Patient",
        email="alice@example.com",
    )
    profile = profile_service.create_profile(db_session, prof_in)
    assert profile.id is not None
    assert profile.auth_user_id == "auth-test-1"
    assert profile.role == UserRole.PATIENT


def test_invalid_profile_role_rejected():
    with pytest.raises(ValidationError):
        ProfileCreate(
            auth_user_id="auth-test-2",
            role="superhero",  # Invalid role
            full_name="Invalid Role User",
            email="invalid@example.com",
        )


def test_valid_hospital_and_duplicate_code_rejected(db_session: Session):
    hosp_in = HospitalCreate(
        name="Metro General Hospital",
        code="MGH-01",
        timezone="America/New_York",
    )
    hosp = hospital_service.create_hospital(db_session, hosp_in)
    assert hosp.id is not None
    assert hosp.code == "MGH-01"

    # Duplicate hospital code should raise ConflictError
    with pytest.raises(ConflictError) as exc_info:
        hospital_service.create_hospital(db_session, hosp_in)
    assert exc_info.value.code == "HOSPITAL_CODE_EXISTS"


def test_department_requires_valid_hospital(db_session: Session):
    dept_in = DepartmentCreate(
        hospital_id="non-existent-hosp-id",
        name="Cardiology Dept",
        code="CARD-01",
    )
    with pytest.raises(NotFoundError) as exc_info:
        department_service.create_department(db_session, dept_in)
    assert exc_info.value.code == "HOSPITAL_NOT_FOUND"


def test_valid_doctor_and_relationships(db_session: Session):
    # Setup Hospital, Profile, and Doctor
    hosp = hospital_service.create_hospital(
        db_session,
        HospitalCreate(name="City Hospital", code="CH-01"),
    )
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-doc-1",
            role=UserRole.DOCTOR,
            full_name="Dr. Gregory House",
            email="house@cityhospital.org",
            hospital_id=hosp.id,
        ),
    )
    doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=prof.id,
            hospital_id=hosp.id,
            license_number="MED-12345",
            years_of_experience=15,
            consultation_mode="both",
            average_rating=4.9,
            rating_count=120,
        ),
    )
    assert doc.id is not None
    assert doc.years_of_experience == 15
    assert doc.license_number == "MED-12345"


def test_duplicate_doctor_specialty_rejected(db_session: Session):
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="St. Jude", code="SJ-01")
    )
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-doc-spec",
            role=UserRole.DOCTOR,
            full_name="Dr. Specialty Test",
            email="spec@test.org",
            hospital_id=hosp.id,
        ),
    )
    doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=prof.id,
            hospital_id=hosp.id,
            license_number="LIC-SPEC-1",
        ),
    )
    spec = specialty_service.create_specialty(
        db_session,
        SpecialtyCreate(name="Neurology", code="NEURO-01"),
    )

    # First assignment succeeds
    doctor_service.assign_specialty(
        db_session,
        doc.id,
        DoctorSpecialtyCreate(
            doctor_id=doc.id,
            specialty_id=spec.id,
            is_primary=True,
        ),
    )

    # Second assignment of same specialty to doctor raises ConflictError
    with pytest.raises(ConflictError) as exc_info:
        doctor_service.assign_specialty(
            db_session,
            doc.id,
            DoctorSpecialtyCreate(
                doctor_id=doc.id,
                specialty_id=spec.id,
            ),
        )
    assert exc_info.value.code == "DOCTOR_SPECIALTY_EXISTS"


def test_invalid_doctor_schedule_time_range():
    # Schema validation: end_time <= start_time
    with pytest.raises(ValidationError):
        DoctorScheduleBase(
            doctor_id="doc-1",
            hospital_id="hosp-1",
            day_of_week=1,
            start_time=time(14, 0),
            end_time=time(12, 0),  # Earlier than start!
            slot_duration_minutes=15,
        )

    with pytest.raises(ValidationError):
        DoctorScheduleBase(
            doctor_id="doc-1",
            hospital_id="hosp-1",
            day_of_week=1,
            start_time=time(10, 0),
            end_time=time(10, 0),  # Equal to start!
            slot_duration_minutes=15,
        )


def test_negative_experience_or_ratings_rejected():
    with pytest.raises(ValidationError):
        DoctorCreate(
            profile_id="prof-1",
            hospital_id="hosp-1",
            license_number="LIC-NEG",
            years_of_experience=-5,  # Negative!
        )

    with pytest.raises(ValidationError):
        DoctorCreate(
            profile_id="prof-1",
            hospital_id="hosp-1",
            license_number="LIC-NEG-2",
            average_rating=6.5,  # Exceeds 5.0!
        )


def test_valid_patient_and_invalid_role_mapping(db_session: Session):
    # Patient profile
    patient_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-pat-valid",
            role=UserRole.PATIENT,
            full_name="Bob Patient",
            email="bob@example.com",
        ),
    )
    pat = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=patient_prof.id,
            date_of_birth=date(1990, 5, 20),
            preferred_language="es",
            emergency_contact="+1-555-0199",
        ),
    )
    assert pat.id is not None
    assert pat.preferred_language == "es"

    # Attempt to create patient from doctor profile must be rejected
    doctor_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="auth-doc-invalid-pat",
            role=UserRole.DOCTOR,
            full_name="Doctor Trying To Be Patient",
            email="doc_pat@example.com",
        ),
    )
    with pytest.raises(ConflictError) as exc_info:
        patient_service.create_patient(
            db_session,
            PatientCreate(
                profile_id=doctor_prof.id,
                date_of_birth=date(1985, 1, 1),
            ),
        )
    assert exc_info.value.code == "INVALID_PROFILE_ROLE"


def test_symptom_observation_requires_status():
    from app.schemas.patient_state import SymptomObservation, PatientState
    from app.services.llm.provider import EvidenceStatus

    # Constructing without status must fail with ValidationError
    with pytest.raises(ValidationError):
        SymptomObservation(code="E_50")

    # Constructing with explicit status and source_message_id succeeds
    obs = SymptomObservation(
        code="E_50",
        status=EvidenceStatus.PRESENT,
        source_message_id="msg-123",
    )
    assert obs.code == "E_50"
    assert obs.status == EvidenceStatus.PRESENT
    assert obs.source_message_id == "msg-123"

    # PatientState mark methods preserve source_message_id
    state = PatientState(session_id="s-1", patient_id="p-1")
    state.mark_present("E_50", source_message_id="msg-456")
    assert state.observations["E_50"].status == EvidenceStatus.PRESENT
    assert state.observations["E_50"].source_message_id == "msg-456"

    state.mark_absent("E_91", source_message_id="msg-789")
    assert state.observations["E_91"].status == EvidenceStatus.ABSENT
    assert state.observations["E_91"].source_message_id == "msg-789"

