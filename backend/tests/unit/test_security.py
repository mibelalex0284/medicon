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
