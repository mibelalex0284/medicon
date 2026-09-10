from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser, require_admin, verify_hospital_access
from app.db.session import get_db
from app.schemas.department import DepartmentCreate, DepartmentResponse
from app.services.department_service import department_service

router = APIRouter(tags=["Departments"])


@router.get(
    "",
    response_model=List[DepartmentResponse],
    summary="List Departments",
    description="Retrieves departments, optionally filtered by hospital ID.",
)
def list_departments(
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[DepartmentResponse]:
    return department_service.list_departments(
        db, hospital_id=hospital_id, skip=skip, limit=limit
    )


@router.get(
    "/{department_id}",
    response_model=DepartmentResponse,
    summary="Get Department Details",
    description="Retrieves details of a specific department by ID.",
)
def get_department(
    department_id: str,
    db: Session = Depends(get_db),
) -> DepartmentResponse:
    return department_service.get_department(db, department_id)


@router.post(
    "",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Department (Admin Only)",
    description="Creates a new department within a hospital. Respects tenant isolation boundaries.",
)
def create_department(
    dept_in: DepartmentCreate,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> DepartmentResponse:
    verify_hospital_access(dept_in.hospital_id, admin_user)
    return department_service.create_department(db, dept_in)
