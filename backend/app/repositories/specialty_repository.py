from typing import Optional
from sqlalchemy.orm import Session
from app.models.specialty import Specialty
from app.repositories.base import BaseRepository
from app.schemas.specialty import SpecialtyCreate, SpecialtyUpdate


class SpecialtyRepository(BaseRepository[Specialty, SpecialtyCreate, SpecialtyUpdate]):
    def __init__(self):
        super().__init__(Specialty)

    def get_by_code(self, db: Session, code: str) -> Optional[Specialty]:
        return db.query(Specialty).filter(Specialty.code == code).first()

    def get_by_name(self, db: Session, name: str) -> Optional[Specialty]:
        return db.query(Specialty).filter(Specialty.name == name).first()


specialty_repo = SpecialtyRepository()
