from typing import Optional
from sqlalchemy.orm import Session
from app.core.exceptions import ConflictError, NotFoundError
from app.models.profile import Profile
from app.repositories.hospital_repository import hospital_repo
from app.repositories.profile_repository import profile_repo
from app.schemas.profile import ProfileCreate, ProfileUpdate


class ProfileService:
    @staticmethod
    def get_profile(db: Session, profile_id: str) -> Profile:
        profile = profile_repo.get(db, profile_id)
        if not profile:
            raise NotFoundError(
                message=f"Profile with id '{profile_id}' not found",
                code="PROFILE_NOT_FOUND",
            )
        return profile

    @staticmethod
    def get_by_auth_user_id(db: Session, auth_user_id: str) -> Optional[Profile]:
        return profile_repo.get_by_auth_user_id(db, auth_user_id)

    @staticmethod
    def create_profile(db: Session, obj_in: ProfileCreate) -> Profile:
        # Check unique auth_user_id
        existing_auth = profile_repo.get_by_auth_user_id(db, obj_in.auth_user_id)
        if existing_auth:
            raise ConflictError(
                message=f"Profile for auth user '{obj_in.auth_user_id}' already exists",
                code="AUTH_USER_PROFILE_EXISTS",
            )

        # Check hospital exists if specified
        if obj_in.hospital_id:
            hospital = hospital_repo.get(db, obj_in.hospital_id)
            if not hospital:
                raise NotFoundError(
                    message=f"Hospital with id '{obj_in.hospital_id}' not found",
                    code="HOSPITAL_NOT_FOUND",
                )

        return profile_repo.create(db, obj_in=obj_in)


profile_service = ProfileService()
