import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.appointment import Appointment, AppointmentStatus
from app.models.profile import UserRole
from app.schemas.doctor import DoctorCreate
from app.schemas.doctor_specialty import DoctorSpecialtyCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service


def test_doctor_me_returns_authenticated_doctor_profile(
    client: TestClient,
    db_session: Session,
    doctor_headers: dict,
):
    """Verifies that GET /api/v1/doctors/me authoritatively returns the authenticated doctor's profile."""
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="St. Jude Medical", code="SJM-01")
    )
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Evelyn Shaw",
            email="evelyn.shaw@stjude.org",
            hospital_id=hosp.id,
        ),
    )
    doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=prof.id,
            hospital_id=hosp.id,
            license_number="LIC-SHAW-2026",
            years_of_experience=15,
            consultation_mode="both",
            average_rating=4.9,
            rating_count=42,
            languages="en,es",
        ),
    )
    spec = specialty_service.create_specialty(
        db_session,
        SpecialtyCreate(name="Cardiology", code="CARDIO"),
    )
    doctor_service.assign_specialty(
        db_session,
        doctor_id=doc.id,
        obj_in=DoctorSpecialtyCreate(doctor_id=doc.id, specialty_id=spec.id, is_primary=True),
    )

    res = client.get("/api/v1/doctors/me", headers=doctor_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == doc.id
    assert data["profile"]["full_name"] == "Dr. Evelyn Shaw"
    assert data["profile"]["email"] == "evelyn.shaw@stjude.org"
    assert data["license_number"] == "LIC-SHAW-2026"
    assert data["years_of_experience"] == 15
    assert data["languages"] == "en,es"
    assert len(data["specialties"]) == 1
    assert data["specialties"][0]["specialty"]["name"] == "Cardiology"


def test_different_authenticated_doctors_see_their_own_identities(
    client: TestClient,
    db_session: Session,
    doctor_headers: dict,
    other_hospital_doctor_headers: dict,
):
    """Verifies that distinct doctor tokens return distinct identities without cross-contamination."""
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Metro Central", code="MC-01")
    )

    # Doctor 1: auth_user_id "doctor-456"
    d1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Alice Adams",
            email="adams@metro.org",
            hospital_id=hosp.id,
        ),
    )
    d1 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=d1_prof.id,
            hospital_id=hosp.id,
            license_number="LIC-ADAMS-01",
        ),
    )

    # Doctor 2: auth_user_id "doctor-other"
    d2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-other",
            role=UserRole.DOCTOR,
            full_name="Dr. Bob Brown",
            email="brown@metro.org",
            hospital_id=hosp.id,
        ),
    )
    d2 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=d2_prof.id,
            hospital_id=hosp.id,
            license_number="LIC-BROWN-02",
        ),
    )

    # Doctor 1 requests /me
    res1 = client.get("/api/v1/doctors/me", headers=doctor_headers)
    assert res1.status_code == 200
    assert res1.json()["id"] == d1.id
    assert res1.json()["profile"]["full_name"] == "Dr. Alice Adams"

    # Doctor 2 requests /me
    res2 = client.get("/api/v1/doctors/me", headers=other_hospital_doctor_headers)
    assert res2.status_code == 200
    assert res2.json()["id"] == d2.id
    assert res2.json()["profile"]["full_name"] == "Dr. Bob Brown"


def test_patient_and_unauthorized_users_cannot_access_doctor_me(
    client: TestClient,
    auth_seeded_db,
    patient_headers: dict,
    admin_headers: dict,
):
    """Verifies role enforcement on GET /api/v1/doctors/me."""
    # 1. Unauthenticated request
    res_anon = client.get("/api/v1/doctors/me")
    assert res_anon.status_code in (401, 403)

    # 2. Patient role
    res_pat = client.get("/api/v1/doctors/me", headers=patient_headers)
    assert res_pat.status_code == 403

    # 3. Admin without a doctor profile
    res_adm = client.get("/api/v1/doctors/me", headers=admin_headers)
    assert res_adm.status_code == 403
    assert res_adm.json()["error"]["code"] == "DOCTOR_RECORD_NOT_FOUND"


def test_doctor_appointment_data_isolation(
    client: TestClient,
    db_session: Session,
    doctor_headers: dict,
    other_hospital_doctor_headers: dict,
):
    """Verifies that doctor appointment listings and single-lookup strictly enforce doctor boundary."""
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="General Care", code="GC-01")
    )
    d1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Doctor One",
            email="doc1@care.org",
            hospital_id=hosp.id,
        ),
    )
    doc1 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(profile_id=d1_prof.id, hospital_id=hosp.id, license_number="LIC-DOC1"),
    )

    d2_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-other",
            role=UserRole.DOCTOR,
            full_name="Dr. Doctor Two",
            email="doc2@care.org",
            hospital_id=hosp.id,
        ),
    )
    doc2 = doctor_service.create_doctor(
        db_session,
        DoctorCreate(profile_id=d2_prof.id, hospital_id=hosp.id, license_number="LIC-DOC2"),
    )

    pat_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Patient User",
            email="pat@care.org",
        ),
    )
    pat = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=pat_prof.id, date_of_birth=datetime.date(1990, 1, 1)),
    )

    # Create appointments for both doctors directly in DB
    appt_date = datetime.date(2027, 1, 15)
    appt1 = Appointment(
        patient_id=pat.id,
        doctor_id=doc1.id,
        hospital_id=hosp.id,
        appointment_date=appt_date,
        scheduled_start=datetime.time(9, 0),
        scheduled_end=datetime.time(9, 30),
        status=AppointmentStatus.BOOKED,
        reason="Checkup for Doc 1",
    )
    appt2 = Appointment(
        patient_id=pat.id,
        doctor_id=doc2.id,
        hospital_id=hosp.id,
        appointment_date=appt_date,
        scheduled_start=datetime.time(10, 0),
        scheduled_end=datetime.time(10, 30),
        status=AppointmentStatus.BOOKED,
        reason="Checkup for Doc 2",
    )
    db_session.add_all([appt1, appt2])
    db_session.commit()
    db_session.refresh(appt1)
    db_session.refresh(appt2)

    # Doctor 1 lists appointments: only sees appt1
    res1 = client.get("/api/v1/appointments", headers=doctor_headers)
    assert res1.status_code == 200
    ids_1 = [a["id"] for a in res1.json()]
    assert appt1.id in ids_1
    assert appt2.id not in ids_1

    # Doctor 2 lists appointments: only sees appt2
    res2 = client.get("/api/v1/appointments", headers=other_hospital_doctor_headers)
    assert res2.status_code == 200
    ids_2 = [a["id"] for a in res2.json()]
    assert appt2.id in ids_2
    assert appt1.id not in ids_2

    # Doctor 1 attempts to access Doctor 2's appointment -> Forbidden
    res_unauth = client.get(f"/api/v1/appointments/{appt2.id}", headers=doctor_headers)
    assert res_unauth.status_code == 403
    assert res_unauth.json()["error"]["code"] == "FORBIDDEN_DOCTOR_ACCESS"


def test_missing_optional_profile_fields_do_not_break_api(
    client: TestClient,
    db_session: Session,
    doctor_headers: dict,
):
    """Verifies that doctor profiles with missing optional fields serialize cleanly."""
    hosp = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Minimalist Clinic", code="MIN-01")
    )
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doctor-456",
            role=UserRole.DOCTOR,
            full_name="Dr. Minimal",
            email="minimal@clinic.org",
            hospital_id=hosp.id,
            phone=None,
        ),
    )
    doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=prof.id,
            hospital_id=hosp.id,
            license_number="LIC-MIN-999",
            department_id=None,
            average_rating=0.0,
            rating_count=0,
            languages="en",
        ),
    )

    res = client.get("/api/v1/doctors/me", headers=doctor_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["profile"]["full_name"] == "Dr. Minimal"
    assert data["profile"]["phone"] is None
    assert data["department"] is None
    assert data["specialties"] == []
