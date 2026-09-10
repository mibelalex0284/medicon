from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from app.core.config import settings
from app.core.exceptions import UnauthorizedError


def decode_jwt_token(token: str, secret: Optional[str] = None) -> Dict[str, Any]:
    """Decodes and verifies a Supabase or application JWT token.
    
    Extracts claims including sub, role, email, and custom claims.
    Raises UnauthorizedError on invalid/expired tokens.
    """
    key = secret or settings.SUPABASE_JWT_SECRET
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[settings.SUPABASE_JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(message="Authentication token has expired", code="TOKEN_EXPIRED")
    except jwt.InvalidTokenError as err:
        raise UnauthorizedError(message=f"Invalid authentication token: {str(err)}", code="INVALID_TOKEN")


def create_access_token(
    subject: str,
    role: str,
    hospital_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Helper to generate JWT tokens (primarily used for unit testing and dev verification)."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=1))

    claims: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "app_metadata": {
            "role": role,
            "hospital_id": hospital_id,
        },
        "user_metadata": {
            "role": role,
            "hospital_id": hospital_id,
        },
        "iat": now,
        "exp": expire,
    }
    if hospital_id:
        claims["hospital_id"] = hospital_id

    if additional_claims:
        claims.update(additional_claims)

    encoded_jwt = jwt.encode(
        claims,
        settings.SUPABASE_JWT_SECRET,
        algorithm=settings.SUPABASE_JWT_ALGORITHM,
    )
    return encoded_jwt
