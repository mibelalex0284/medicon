from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.exceptions import ConflictError, NotFoundError
from app.models.specialty import Specialty
from app.repositories.specialty_repository import specialty_repo
from app.schemas.specialty import SpecialtyCreate, SpecialtyUpdate


class SpecialtyService:
    @staticmethod
    def get_specialty(db: Session, specialty_id: str) -> Specialty:
        spec = specialty_repo.get(db, specialty_id)
        if not spec:
            raise NotFoundError(
                message=f"Specialty with id '{specialty_id}' not found",
                code="SPECIALTY_NOT_FOUND",
            )
        return spec

    @staticmethod
    def list_specialties(
        db: Session, *, skip: int = 0, limit: int = 100, active_only: bool = True
    ) -> List[Specialty]:
        query = db.query(Specialty)
        if active_only:
            query = query.filter(Specialty.is_active.is_(True))
        return query.order_by(Specialty.name).offset(skip).limit(limit).all()

    @staticmethod
    def create_specialty(db: Session, obj_in: SpecialtyCreate) -> Specialty:
        existing_code = specialty_repo.get_by_code(db, obj_in.code)
        if existing_code:
            raise ConflictError(
                message=f"Specialty with code '{obj_in.code}' already exists",
                code="SPECIALTY_CODE_EXISTS",
            )
        existing_name = specialty_repo.get_by_name(db, obj_in.name)
        if existing_name:
            raise ConflictError(
                message=f"Specialty with name '{obj_in.name}' already exists",
                code="SPECIALTY_NAME_EXISTS",
            )
        return specialty_repo.create(db, obj_in=obj_in)


specialty_service = SpecialtyService()
