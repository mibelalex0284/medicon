from typing import List, Optional
from sqlalchemy.orm import Session
from app.core.exceptions import ConflictError, NotFoundError
from app.models.department import Department
from app.repositories.department_repository import department_repo
from app.repositories.hospital_repository import hospital_repo
from app.schemas.department import DepartmentCreate, DepartmentUpdate


class DepartmentService:
    @staticmethod
    def get_department(db: Session, department_id: str) -> Department:
        dept = department_repo.get(db, department_id)
        if not dept:
            raise NotFoundError(
                message=f"Department with id '{department_id}' not found",
                code="DEPARTMENT_NOT_FOUND",
            )
        return dept

    @staticmethod
    def list_departments(
        db: Session,
        *,
        hospital_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = True,
    ) -> List[Department]:
        query = db.query(Department)
        if hospital_id:
            query = query.filter(Department.hospital_id == hospital_id)
        if active_only:
            query = query.filter(Department.is_active.is_(True))
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def create_department(db: Session, obj_in: DepartmentCreate) -> Department:
        # Validate that the parent hospital exists
        hospital = hospital_repo.get(db, obj_in.hospital_id)
        if not hospital:
            raise NotFoundError(
                message=f"Hospital with id '{obj_in.hospital_id}' not found",
                code="HOSPITAL_NOT_FOUND",
            )

        # Check unique code per hospital
        existing = department_repo.get_by_hospital_and_code(
            db, obj_in.hospital_id, obj_in.code
        )
        if existing:
            raise ConflictError(
                message=f"Department with code '{obj_in.code}' already exists in this hospital",
                code="DEPARTMENT_CODE_EXISTS",
            )

        return department_repo.create(db, obj_in=obj_in)


department_service = DepartmentService()
