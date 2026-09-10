from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from app.models.doctor import Doctor
from app.models.doctor_specialty import DoctorSpecialty
from app.repositories.base import BaseRepository
from app.schemas.doctor import DoctorCreate, DoctorUpdate


class DoctorRepository(BaseRepository[Doctor, DoctorCreate, DoctorUpdate]):
    def __init__(self):
        super().__init__(Doctor)

    def get_with_details(self, db: Session, doctor_id: str) -> Optional[Doctor]:
        return (
            db.query(Doctor)
            .options(
                joinedload(Doctor.profile),
                joinedload(Doctor.hospital),
                joinedload(Doctor.department),
                joinedload(Doctor.specialties).joinedload(DoctorSpecialty.specialty),
            )
            .filter(Doctor.id == doctor_id)
            .first()
        )

    def get_by_profile_id(self, db: Session, profile_id: str) -> Optional[Doctor]:
        return (
            db.query(Doctor)
            .options(
                joinedload(Doctor.profile),
                joinedload(Doctor.hospital),
                joinedload(Doctor.department),
                joinedload(Doctor.specialties).joinedload(DoctorSpecialty.specialty),
            )
            .filter(Doctor.profile_id == profile_id)
            .first()
        )

    def get_by_license(self, db: Session, license_number: str) -> Optional[Doctor]:
        return db.query(Doctor).filter(Doctor.license_number == license_number).first()

    def filter_doctors(
        self,
        db: Session,
        *,
        hospital_id: Optional[str] = None,
        specialty_id: Optional[str] = None,
        department_id: Optional[str] = None,
        is_active: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Doctor]:
        query = (
            db.query(Doctor)
            .options(
                joinedload(Doctor.profile),
                joinedload(Doctor.hospital),
                joinedload(Doctor.department),
                joinedload(Doctor.specialties).joinedload(DoctorSpecialty.specialty),
            )
            .filter(Doctor.is_active == is_active)
        )

        if hospital_id:
            query = query.filter(Doctor.hospital_id == hospital_id)
        if department_id:
            query = query.filter(Doctor.department_id == department_id)
        if specialty_id:
            query = query.join(Doctor.specialties).filter(
                DoctorSpecialty.specialty_id == specialty_id
            )

        return query.offset(skip).limit(limit).all()


doctor_repo = DoctorRepository()
