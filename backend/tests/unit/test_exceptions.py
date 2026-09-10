import json
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidStateTransitionError,
    NotFoundError,
    UnauthorizedError,
    create_error_response,
)


def test_exception_properties():
    nf = NotFoundError("Appointment not found")
    assert nf.status_code == 404
    assert nf.code == "NOT_FOUND"
    assert nf.message == "Appointment not found"

    ist = InvalidStateTransitionError("A completed queue entry cannot be started again.")
    assert ist.status_code == 400
    assert ist.code == "INVALID_STATE_TRANSITION"
    assert "completed queue entry" in ist.message

    unauth = UnauthorizedError()
    assert unauth.status_code == 401
    assert unauth.code == "UNAUTHORIZED"

    forbid = ForbiddenError()
    assert forbid.status_code == 403
    assert forbid.code == "FORBIDDEN"

    conf = ConflictError()
    assert conf.status_code == 409
    assert conf.code == "CONFLICT"


def test_create_error_response_envelope():
    response = create_error_response(
        code="TEST_ERROR",
        message="This is a test error message.",
        status_code=400,
        details={"field": "test"},
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status_code == 400
    assert "error" in body
    assert body["error"]["code"] == "TEST_ERROR"
    assert body["error"]["message"] == "This is a test error message."
    assert body["error"]["details"] == {"field": "test"}
