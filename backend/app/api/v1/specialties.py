from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.dependencies import AuthenticatedUser, require_admin
from app.db.session import get_db
from app.schemas.specialty import SpecialtyCreate, SpecialtyResponse
from app.services.specialty_service import specialty_service

router = APIRouter(tags=["Specialties"])


@router.get(
    "",
    response_model=List[SpecialtyResponse],
    summary="List Specialties",
    description="Retrieves all active clinical specialties (e.g., Cardiology, General Medicine, Dermatology).",
)
def list_specialties(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[SpecialtyResponse]:
    return specialty_service.list_specialties(db, skip=skip, limit=limit)


@router.get(
    "/{specialty_id}",
    response_model=SpecialtyResponse,
    summary="Get Specialty Details",
    description="Retrieves details of a specific specialty by ID.",
)
def get_specialty(
    specialty_id: str,
    db: Session = Depends(get_db),
) -> SpecialtyResponse:
    return specialty_service.get_specialty(db, specialty_id)


@router.post(
    "",
    response_model=SpecialtyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Specialty (Admin Only)",
    description="Creates a new clinical specialty. Restricted to administrators.",
)
def create_specialty(
    spec_in: SpecialtyCreate,
    db: Session = Depends(get_db),
    admin_user: AuthenticatedUser = Depends(require_admin),
) -> SpecialtyResponse:
    return specialty_service.create_specialty(db, spec_in)
