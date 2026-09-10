from typing import Optional
from sqlalchemy.orm import Session
from app.models.profile import Profile
from app.repositories.base import BaseRepository
from app.schemas.profile import ProfileCreate, ProfileUpdate


class ProfileRepository(BaseRepository[Profile, ProfileCreate, ProfileUpdate]):
    def __init__(self):
        super().__init__(Profile)

    def get_by_auth_user_id(self, db: Session, auth_user_id: str) -> Optional[Profile]:
        return db.query(Profile).filter(Profile.auth_user_id == auth_user_id).first()

    def get_by_email(self, db: Session, email: str) -> Optional[Profile]:
        return db.query(Profile).filter(Profile.email == email).first()


profile_repo = ProfileRepository()
