import datetime
from sqlalchemy.orm import Session
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.profile import UserRole
from app.repositories.patient_repository import patient_repo
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
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

    # Generate a long-lived development JWT token (365 days) signed with existing SUPABASE_JWT_SECRET
    token = create_access_token(
        subject="pat_101",
        role="patient",
        expires_delta=datetime.timedelta(days=365),
    )
    return token


if __name__ == "__main__":
    db = SessionLocal()
    try:
        dev_token = seed_development_patient(db)
        print(f"DEV_PATIENT_TOKEN={dev_token}")
    finally:
        db.close()
