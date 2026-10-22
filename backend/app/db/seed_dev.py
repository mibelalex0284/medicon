import datetime
from typing import Dict
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.profile import Profile, UserRole
from app.repositories.doctor_repository import doctor_repo
from app.repositories.hospital_repository import hospital_repo
from app.repositories.patient_repository import patient_repo
from app.repositories.profile_repository import profile_repo
from app.schemas.doctor import DoctorCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.services.doctor_service import doctor_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service


def seed_development_patient(db: Session) -> str:
    """Idempotently seeds a development patient corresponding to frontend mock user 'pat_101'."""
    existing_patient = patient_repo.get_by_auth_user_id(db, "pat_101")
    if not existing_patient:
        prof = profile_service.create_profile(
            db,
            ProfileCreate(
                auth_user_id="pat_101",
                role=UserRole.PATIENT,
                full_name="Sarah Jenkins",
                email="sarah.jenkins@example.com",
            ),
        )
        patient_service.create_patient(
            db,
            PatientCreate(
                profile_id=prof.id,
                date_of_birth=datetime.date(1988, 4, 12),
            ),
        )
        db.commit()

    token = create_access_token(
        subject="pat_101",
        role="patient",
        expires_delta=datetime.timedelta(days=365),
    )
    return token


def seed_development_doctor(db: Session) -> str:
    """Idempotently seeds a development doctor corresponding to frontend mock user 'doc_202'."""
    prof = profile_repo.get_by_auth_user_id(db, "doc_202")
    hospitals = hospital_repo.get_multi(db, limit=1)
    hospital_id = hospitals[0].id if hospitals else "e14e1435-aecd-480a-ad14-eaaed67560bc"

    if not prof:
        prof = profile_service.create_profile(
            db,
            ProfileCreate(
                auth_user_id="doc_202",
                role=UserRole.DOCTOR,
                full_name="Dr. Anita Menon, MD",
                email="dr.menon@metrocentral.org",
                hospital_id=hospital_id,
            ),
        )

    # Ensure Doctor record exists
    existing_doc = (
        db.query(doctor_repo.model)
        .filter(doctor_repo.model.profile_id == prof.id)
        .first()
    )
    if not existing_doc:
        doctor_service.create_doctor(
            db,
            DoctorCreate(
                profile_id=prof.id,
                hospital_id=hospital_id,
                license_number="MD-CRX-2026-0202",
                years_of_experience=14,
                consultation_mode="both",
                average_rating=4.9,
                rating_count=38,
                languages="en,hi,ml",
                is_active=True,
            ),
        )
        db.commit()

    token = create_access_token(
        subject="doc_202",
        role="doctor",
        hospital_id=hospital_id,
        expires_delta=datetime.timedelta(days=365),
    )
    return token


def seed_development_admin(db: Session) -> str:
    """Idempotently seeds a development administrator corresponding to mock user 'adm_303'."""
    prof = profile_repo.get_by_auth_user_id(db, "adm_303")
    hospitals = hospital_repo.get_multi(db, limit=1)
    hospital_id = hospitals[0].id if hospitals else "e14e1435-aecd-480a-ad14-eaaed67560bc"

    if not prof:
        prof = profile_service.create_profile(
            db,
            ProfileCreate(
                auth_user_id="adm_303",
                role=UserRole.ADMIN,
                full_name="Mark Evans",
                email="ops.admin@careroute.org",
                hospital_id=hospital_id,
            ),
        )
        db.commit()

    token = create_access_token(
        subject="adm_303",
        role="admin",
        hospital_id=hospital_id,
        expires_delta=datetime.timedelta(days=365),
    )
    return token


def seed_all_dev_accounts(db: Session) -> Dict[str, str]:
    if getattr(settings, "ENVIRONMENT", "development") == "production":
        raise RuntimeError("Development account seeding is strictly forbidden in production!")

    patient_token = seed_development_patient(db)
    doctor_token = seed_development_doctor(db)
    admin_token = seed_development_admin(db)

    return {
        "patient": patient_token,
        "doctor": doctor_token,
        "admin": admin_token,
    }


if __name__ == "__main__":
    db = SessionLocal()
    try:
        tokens = seed_all_dev_accounts(db)
        print("CareRoute-X Development Account Seeding Complete:")
        print(f"PATIENT (pat_101): Token generated successfully.")
        print(f"DOCTOR  (doc_202): Token generated successfully.")
        print(f"ADMIN   (adm_303): Token generated successfully.")
    finally:
        db.close()
