from typing import Any, Dict, Optional
from fastapi import Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_jwt_token
from app.db.session import get_db


class AuthenticatedUser(BaseModel):
    id: str  # auth_user_id (from JWT sub)
    role: str  # Authoritative role from Database Profile (or 'unregistered' if no profile exists)
    profile_id: Optional[str] = None
    hospital_id: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True
    has_profile: bool = True
    raw_claims: Dict[str, Any] = {}

    @property
    def is_patient(self) -> bool:
        return self.role.lower() == "patient"

    @property
    def is_doctor(self) -> bool:
        return self.role.lower() == "doctor"

    @property
    def is_admin(self) -> bool:
        return self.role.lower() == "admin"


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """Extracts, validates the Supabase JWT token, and resolves authoritative user identity.
    
    Validates token signature and expiration, then resolves user role and permissions
    strictly from trusted database Profile records, never trusting client-supplied role claims.
    """
    if not authorization:
        raise UnauthorizedError(
            message="Authorization header missing",
            code="AUTHORIZATION_HEADER_MISSING",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise UnauthorizedError(
            message="Invalid Authorization header format. Expected 'Bearer <token>'",
            code="INVALID_AUTH_HEADER",
        )

    token = parts[1]
    claims = decode_jwt_token(token)

    user_id = claims.get("sub")
    if not user_id:
        raise UnauthorizedError(
            message="Token does not contain a valid subject (user ID)",
            code="INVALID_TOKEN_CLAIMS",
        )

    # Resolve authoritative role & profile strictly from trusted database records
    from app.models.profile import Profile
    profile = db.query(Profile).filter(Profile.auth_user_id == str(user_id)).first()

    if profile:
        if not profile.is_active:
            raise ForbiddenError(
                message="Your account is currently inactive. Please contact an administrator.",
                code="ACCOUNT_INACTIVE",
            )
        return AuthenticatedUser(
            id=str(user_id),
            role=profile.role.value.lower(),
            profile_id=profile.id,
            hospital_id=profile.hospital_id,
            email=profile.email or claims.get("email"),
            is_active=profile.is_active,
            has_profile=True,
            raw_claims=claims,
        )

    # Verified token subject with no database profile registered yet
    # Role is strictly 'unregistered' - client-provided claims are NEVER trusted for authorization
    email = claims.get("email")
    return AuthenticatedUser(
        id=str(user_id),
        role="unregistered",
        profile_id=None,
        hospital_id=None,
        email=email,
        is_active=True,
        has_profile=False,
        raw_claims=claims,
    )


def require_role(allowed_roles: list[str]):
    """Factory creating a dependency that restricts access to specific roles."""

    def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not current_user.has_profile or current_user.role.lower() not in [r.lower() for r in allowed_roles]:
            raise ForbiddenError(
                message=f"Access forbidden: requires one of roles [{', '.join(allowed_roles)}]",
                code="INSUFFICIENT_ROLE_PERMISSIONS",
            )
        if not current_user.is_active:
            raise ForbiddenError(
                message="Account has been deactivated by administration. Access revoked.",
                code="ACCOUNT_DEACTIVATED",
            )
        return current_user

    return role_checker


require_patient = require_role(["patient", "admin"])
require_doctor = require_role(["doctor", "admin"])
require_admin = require_role(["admin"])


def verify_hospital_access(hospital_id: str, user: AuthenticatedUser) -> None:
    """Enforces multi-hospital tenant boundaries.
    
    Prevents doctors/staff from accessing records belonging to other hospitals.
    System administrators with no specific hospital binding may access across hospitals.
    """
    if user.is_admin and not user.hospital_id:
        # Global super-admin
        return

    if user.hospital_id and str(user.hospital_id) != str(hospital_id):
        raise ForbiddenError(
            message="Cross-hospital access is strictly forbidden",
            code="CROSS_HOSPITAL_FORBIDDEN",
        )
