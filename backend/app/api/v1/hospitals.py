from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser, require_admin
from app.db.session import get_db
from app.schemas.hospital import HospitalCreate, HospitalResponse
from app.services.hospital_service import hospital_service

router = APIRouter(tags=["Hospitals"])


@router.get(
    "",
    response_model=List[HospitalResponse],
    summary="List Active Hospitals",
    description="Retrieves a list of all active hospitals/healthcare facilities.",
)
def list_hospitals(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[HospitalResponse]:
    return hospital_service.list_hospitals(db, skip=skip, limit=limit, active_only=True)


@router.get(
    "/{hospital_id}",
    response_model=HospitalResponse,
    summary="Get Hospital Details",
    description="Retrieves operational details for a specific hospital by ID.",
)
def get_hospital(
    hospital_id: str,
    db: Session = Depends(get_db),
) -> HospitalResponse:
    return hospital_service.get_hospital(db, hospital_id)


@router.post(
    "",
    response_model=HospitalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Hospital (Admin Only)",
    description="Registers a new healthcare facility. Restricted to global administrators.",
)
def create_hospital(
    hospital_in: HospitalCreate,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> HospitalResponse:
    return hospital_service.create_hospital(db, hospital_in)
