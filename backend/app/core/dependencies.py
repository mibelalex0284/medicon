from typing import Any, Dict, Optional
from fastapi import Depends, Header
from pydantic import BaseModel
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_jwt_token


class AuthenticatedUser(BaseModel):
    id: str
    role: str
    hospital_id: Optional[str] = None
    email: Optional[str] = None
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
) -> AuthenticatedUser:
    """Extracts and validates the Supabase JWT token from the Authorization header.
    
    Determines user identity and role from trusted token claims.
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

    # Supabase roles can be in app_metadata, user_metadata, or direct role claim
    app_meta = claims.get("app_metadata", {})
    user_meta = claims.get("user_metadata", {})
    role = (
        app_meta.get("role")
        or user_meta.get("role")
        or claims.get("role")
        or "authenticated"
    )

    hospital_id = (
        claims.get("hospital_id")
        or app_meta.get("hospital_id")
        or user_meta.get("hospital_id")
    )

    email = claims.get("email")

    return AuthenticatedUser(
        id=str(user_id),
        role=str(role).lower(),
        hospital_id=str(hospital_id) if hospital_id else None,
        email=email,
        raw_claims=claims,
    )


def require_role(allowed_roles: list[str]):
    """Factory creating a dependency that restricts access to specific roles."""

    def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if current_user.role.lower() not in [r.lower() for r in allowed_roles]:
            raise ForbiddenError(
                message=f"Access forbidden: requires one of roles [{', '.join(allowed_roles)}]",
                code="INSUFFICIENT_ROLE_PERMISSIONS",
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
