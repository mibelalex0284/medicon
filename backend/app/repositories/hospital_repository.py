from typing import Optional
from sqlalchemy.orm import Session
from app.models.hospital import Hospital
from app.repositories.base import BaseRepository
from app.schemas.hospital import HospitalCreate, HospitalUpdate


class HospitalRepository(BaseRepository[Hospital, HospitalCreate, HospitalUpdate]):
    def __init__(self):
        super().__init__(Hospital)

    def get_by_code(self, db: Session, code: str) -> Optional[Hospital]:
        return db.query(Hospital).filter(Hospital.code == code).first()


hospital_repo = HospitalRepository()
