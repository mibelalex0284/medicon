from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.exceptions import ConflictError, NotFoundError
from app.models.hospital import Hospital
from app.repositories.hospital_repository import hospital_repo
from app.schemas.hospital import HospitalCreate, HospitalUpdate


class HospitalService:
    @staticmethod
    def get_hospital(db: Session, hospital_id: str) -> Hospital:
        hospital = hospital_repo.get(db, hospital_id)
        if not hospital:
            raise NotFoundError(message=f"Hospital with id '{hospital_id}' not found", code="HOSPITAL_NOT_FOUND")
        return hospital

    @staticmethod
    def list_hospitals(
        db: Session, *, skip: int = 0, limit: int = 100, active_only: bool = True
    ) -> List[Hospital]:
        query = db.query(Hospital)
        if active_only:
            query = query.filter(Hospital.is_active.is_(True))
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def create_hospital(db: Session, obj_in: HospitalCreate) -> Hospital:
        existing = hospital_repo.get_by_code(db, obj_in.code)
        if existing:
            raise ConflictError(
                message=f"Hospital with code '{obj_in.code}' already exists",
                code="HOSPITAL_CODE_EXISTS",
            )
        return hospital_repo.create(db, obj_in=obj_in)

    @staticmethod
    def update_hospital(
        db: Session, hospital_id: str, obj_in: HospitalUpdate
    ) -> Hospital:
        hospital = HospitalService.get_hospital(db, hospital_id)
        if obj_in.code and obj_in.code != hospital.code:
            existing = hospital_repo.get_by_code(db, obj_in.code)
            if existing:
                raise ConflictError(
                    message=f"Hospital with code '{obj_in.code}' already exists",
                    code="HOSPITAL_CODE_EXISTS",
                )
        return hospital_repo.update(db, db_obj=hospital, obj_in=obj_in)


hospital_service = HospitalService()
