from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.patient import Patient
from app.models.profile import Profile
from app.repositories.base import BaseRepository
from app.schemas.patient import PatientCreate, PatientUpdate


class PatientRepository(BaseRepository[Patient, PatientCreate, PatientUpdate]):
    def __init__(self):
        super().__init__(Patient)

    def get_with_details(self, db: Session, patient_id: str) -> Optional[Patient]:
        return (
            db.query(Patient)
            .options(joinedload(Patient.profile))
            .filter(Patient.id == patient_id)
            .first()
        )

    def get_by_profile_id(self, db: Session, profile_id: str) -> Optional[Patient]:
        return (
            db.query(Patient)
            .options(joinedload(Patient.profile))
            .filter(Patient.profile_id == profile_id)
            .first()
        )

    def get_by_auth_user_id(self, db: Session, auth_user_id: str) -> Optional[Patient]:
        return (
            db.query(Patient)
            .join(Patient.profile)
            .options(joinedload(Patient.profile))
            .filter(Profile.auth_user_id == auth_user_id)
            .first()
        )


patient_repo = PatientRepository()
