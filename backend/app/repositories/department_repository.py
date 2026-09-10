from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.department import Department
from app.repositories.base import BaseRepository
from app.schemas.department import DepartmentCreate, DepartmentUpdate


class DepartmentRepository(BaseRepository[Department, DepartmentCreate, DepartmentUpdate]):
    def __init__(self):
        super().__init__(Department)

    def get_by_hospital(
        self, db: Session, hospital_id: str, skip: int = 0, limit: int = 100
    ) -> List[Department]:
        return (
            db.query(Department)
            .filter(Department.hospital_id == hospital_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_by_hospital_and_code(
        self, db: Session, hospital_id: str, code: str
    ) -> Optional[Department]:
        return (
            db.query(Department)
            .filter(Department.hospital_id == hospital_id, Department.code == code)
            .first()
        )


department_repo = DepartmentRepository()
