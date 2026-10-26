from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Optional
import jwt
from jwt import PyJWKClient
from app.core.config import settings
from app.core.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)

# Global thread-safe JWKS client cache: mapping jwks_url -> PyJWKClient
_jwks_clients: Dict[str, PyJWKClient] = {}


def get_jwks_client(jwks_url: str) -> PyJWKClient:
    """Returns a cached PyJWKClient instance for the given JWKS URL."""
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = PyJWKClient(
            jwks_url,
            cache_keys=True,
            max_cached_keys=16,
            cache_jwk_set=True,
            lifespan=3600,
        )
    return _jwks_clients[jwks_url]


def decode_jwt_token(
    token: str,
    secret: Optional[str] = None,
    verify_issuer: bool = True,
) -> Dict[str, Any]:
    """Decodes and verifies a Supabase or application JWT token.
    
    Supports asymmetric (ES256/RS256 via Supabase JWKS) and legacy symmetric
    (HS256 via SUPABASE_JWT_SECRET) verification. Inspects unverified headers,
    enforces allowed algorithms, validates signature, expiration, required claims,
    and strict issuer matching.
    Raises UnauthorizedError on invalid/expired/unsupported tokens.
    """
    try:
        header = jwt.get_unverified_header(token)
    except Exception as err:
        raise UnauthorizedError(
            message=f"Invalid authentication token header: {str(err)}",
            code="INVALID_AUTH_HEADER",
        )

    alg = header.get("alg")
    if not alg:
        raise UnauthorizedError(
            message="Token header does not specify a signing algorithm",
            code="UNSUPPORTED_ALGORITHM",
        )

    allowed_algorithms = [
        "ES256", "ES384", "ES512",
        "RS256", "RS384", "RS512",
        "HS256", "HS384", "HS512",
    ]
    if alg not in allowed_algorithms:
        raise UnauthorizedError(
            message=f"Unsupported JWT signing algorithm: '{alg}'",
            code="UNSUPPORTED_ALGORITHM",
        )

    try:
        decode_options = {
            "verify_aud": bool(settings.SUPABASE_JWT_AUDIENCE),
            "verify_exp": True,
        }
        decode_kwargs: Dict[str, Any] = {
            "algorithms": [alg],
            "options": decode_options,
        }
        if settings.SUPABASE_JWT_AUDIENCE:
            decode_kwargs["audience"] = settings.SUPABASE_JWT_AUDIENCE

        if alg.startswith("HS"):
            # Legacy symmetric HMAC verification
            key = secret or settings.SUPABASE_JWT_SECRET
            if not key and settings.ENVIRONMENT.lower() != "production":
                key = "dev-insecure-test-signing-secret-32bytes-min"

            if not key or (settings.ENVIRONMENT.lower() == "production" and "placeholder" in key):
                raise UnauthorizedError(
                    message="Legacy HS256 token verification is not configured or disabled in production",
                    code="LEGACY_SECRET_NOT_CONFIGURED",
                )
            payload = jwt.decode(
                token,
                key,
                **decode_kwargs,
            )
        else:
            # Asymmetric key verification (ES256 / RS256 via JWKS or explicit public key)
            if secret:
                payload = jwt.decode(
                    token,
                    secret,
                    **decode_kwargs,
                )
            elif settings.effective_jwks_url:
                jwks_client = get_jwks_client(settings.effective_jwks_url)
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    **decode_kwargs,
                )
            else:
                raise UnauthorizedError(
                    message="Supabase JWKS URL is not configured for ES256 verification",
                    code="JWKS_NOT_CONFIGURED",
                )

        # Enforce required expiration claim
        if "exp" not in payload:
            raise UnauthorizedError(
                message="Token does not contain an expiration claim",
                code="TOKEN_MISSING_EXP",
            )

        # Enforce required subject claim
        if not payload.get("sub"):
            raise UnauthorizedError(
                message="Token does not contain a valid subject claim",
                code="INVALID_TOKEN_CLAIMS",
            )

        # Verify issuer strictly when configured or when verify_issuer is enforced
        if verify_issuer and settings.is_supabase_configured:
            expected_issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
            token_issuer = payload.get("iss")
            if not token_issuer:
                raise UnauthorizedError(
                    message="Token does not contain an issuer claim",
                    code="MISSING_TOKEN_ISSUER",
                )
            if token_issuer.rstrip('/') != expected_issuer.rstrip('/'):
                raise UnauthorizedError(
                    message="Token issuer does not match configured Supabase project",
                    code="INVALID_TOKEN_ISSUER",
                )

        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(message="Authentication token has expired", code="TOKEN_EXPIRED")
    except UnauthorizedError:
        raise
    except jwt.PyJWKClientError as err:
        raise UnauthorizedError(message=f"Unable to verify token against Supabase JWKS: {str(err)}", code="JWKS_VERIFICATION_FAILED")
    except jwt.InvalidTokenError as err:
        raise UnauthorizedError(message=f"Invalid authentication token: {str(err)}", code="INVALID_TOKEN")


def create_access_token(
    subject: str,
    role: str,
    hospital_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None,
    secret: Optional[str] = None,
    algorithm: Optional[str] = None,
) -> str:
    """Helper to generate JWT tokens (primarily used for unit testing and dev verification)."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=1))

    claims: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
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

    if settings.SUPABASE_JWT_AUDIENCE:
        claims.setdefault("aud", settings.SUPABASE_JWT_AUDIENCE)

    if additional_claims:
        claims.update(additional_claims)

    signing_alg = algorithm or "HS256"
    signing_secret = (
        secret
        or settings.SUPABASE_JWT_SECRET
        or "dev-insecure-test-signing-secret-32bytes-min"
    )

    encoded_jwt = jwt.encode(
        claims,
        signing_secret,
        algorithm=signing_alg,
    )
    return encoded_jwt
