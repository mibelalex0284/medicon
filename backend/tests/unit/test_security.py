from datetime import timedelta
import pytest
from app.core.dependencies import AuthenticatedUser, verify_hospital_access
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import create_access_token, decode_jwt_token


def test_create_and_decode_valid_token():
    token = create_access_token(
        subject="usr-100",
        role="doctor",
        hospital_id="hosp-alpha",
        additional_claims={"email": "dr.smith@example.com"},
    )
    payload = decode_jwt_token(token)
    assert payload["sub"] == "usr-100"
    assert payload["role"] == "doctor"
    assert payload["hospital_id"] == "hosp-alpha"
    assert payload["email"] == "dr.smith@example.com"


def test_expired_token_raises_unauthorized():
    token = create_access_token(
        subject="usr-100",
        role="patient",
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token)
    assert exc_info.value.code == "TOKEN_EXPIRED"


def test_invalid_signature_raises_unauthorized():
    token = create_access_token(subject="usr-100", role="patient")
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token, secret="wrong-secret-key-1234567890-32bytes-long")
    assert exc_info.value.code == "INVALID_TOKEN"


def test_cross_hospital_access_forbidden():
    user = AuthenticatedUser(
        id="doc-1",
        role="doctor",
        hospital_id="hospital-A",
    )
    # Matching hospital succeeds
    verify_hospital_access("hospital-A", user)

    # Mismatched hospital raises ForbiddenError
    with pytest.raises(ForbiddenError) as exc_info:
        verify_hospital_access("hospital-B", user)
    assert exc_info.value.code == "CROSS_HOSPITAL_FORBIDDEN"


def test_global_admin_can_access_any_hospital():
    admin_user = AuthenticatedUser(
        id="admin-global",
        role="admin",
        hospital_id=None,
    )
    # Global admin with no specific hospital binding should pass
    verify_hospital_access("hospital-any", admin_user)


def test_es256_token_verification_with_ec_key():
    """Verifies ES256 token verification using Elliptic Curve P-256 keypair."""
    import jwt
    from datetime import datetime, timezone
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from app.core.config import settings

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "sub": "supabase-es256-user-uuid",
        "role": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": now + 3600,
        "iat": now - 10,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "test-key-id"})

    # Verify using direct public key
    decoded = decode_jwt_token(token, secret=public_pem)
    assert decoded["sub"] == "supabase-es256-user-uuid"
    assert decoded["role"] == "authenticated"


def test_es256_token_verification_via_jwks(monkeypatch):
    """Verifies ES256 token verification using cached PyJWKClient."""
    import jwt
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from cryptography.hazmat.primitives.asymmetric import ec
    from app.core.config import settings
    import app.core.security as security_module

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "sub": "jwks-verified-patient-uuid",
        "role": "patient",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": now + 3600,
        "iat": now - 10,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "efd5f80d-7adf-4af0-95e1-546357415b0e"})

    # Mock get_jwks_client to return a mock client with public_key
    mock_jwks_client = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = public_key
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key

    monkeypatch.setattr(security_module, "get_jwks_client", lambda url: mock_jwks_client)

    decoded = decode_jwt_token(token)
    assert decoded["sub"] == "jwks-verified-patient-uuid"
    assert decoded["role"] == "patient"


def test_unsupported_algorithm_rejected():
    """Verifies that tokens with unsupported or dangerous algorithms (e.g. none) are rejected."""
    import jwt

    token = jwt.encode({"sub": "attacker", "exp": 1999999999}, "", algorithm="none")
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token)
    assert exc_info.value.code == "UNSUPPORTED_ALGORITHM"


def test_missing_expiration_claim_rejected():
    """Verifies that tokens without an exp claim are rejected."""
    import jwt
    from app.core.config import settings

    token = jwt.encode(
        {"sub": "no-exp-user", "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"},
        settings.SUPABASE_JWT_SECRET or "dev-insecure-test-signing-secret-32bytes-min",
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token)
    assert exc_info.value.code == "TOKEN_MISSING_EXP"


def test_missing_subject_claim_rejected():
    """Verifies that tokens without a sub claim are rejected."""
    import jwt
    from app.core.config import settings

    token = jwt.encode(
        {"exp": 1999999999, "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"},
        settings.SUPABASE_JWT_SECRET or "dev-insecure-test-signing-secret-32bytes-min",
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token)
    assert exc_info.value.code == "INVALID_TOKEN_CLAIMS"


def test_missing_or_invalid_issuer_rejected(monkeypatch):
    """Verifies that tokens with missing or mismatched issuer are rejected when Supabase is configured."""
    import jwt
    from app.core.config import settings

    # Ensure Supabase is configured for this test
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "real-anon-key-12345")

    # 1. Missing issuer
    token_no_iss = jwt.encode(
        {"sub": "user-123", "exp": 1999999999},
        settings.SUPABASE_JWT_SECRET or "dev-insecure-test-signing-secret-32bytes-min",
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token_no_iss, verify_issuer=True)
    assert exc_info.value.code == "MISSING_TOKEN_ISSUER"

    # 2. Invalid issuer
    token_bad_iss = jwt.encode(
        {"sub": "user-123", "exp": 1999999999, "iss": "https://attacker.supabase.co/auth/v1"},
        settings.SUPABASE_JWT_SECRET or "dev-insecure-test-signing-secret-32bytes-min",
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token_bad_iss, verify_issuer=True)
    assert exc_info.value.code == "INVALID_TOKEN_ISSUER"


def test_legacy_hs256_rejected_in_production_when_placeholder(monkeypatch):
    """Verifies that legacy HS256 tokens are rejected if production secret is a placeholder."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", "placeholder-secret")

    token = create_access_token(subject="user-hs256", role="patient")
    with pytest.raises(UnauthorizedError) as exc_info:
        decode_jwt_token(token)
    assert exc_info.value.code == "LEGACY_SECRET_NOT_CONFIGURED"

