from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from app.core.dependencies import AuthenticatedUser, require_admin, require_doctor, require_patient
from app.main import app

# Create a test router to verify dependency guards
guard_test_router = APIRouter(prefix="/api/v1/test-guard", tags=["TestGuard"])


@guard_test_router.get("/patient-only")
def patient_only_route(user: AuthenticatedUser = Depends(require_patient)):
    return {"user_id": user.id, "role": user.role}


@guard_test_router.get("/doctor-only")
def doctor_only_route(user: AuthenticatedUser = Depends(require_doctor)):
    return {"user_id": user.id, "role": user.role}


@guard_test_router.get("/admin-only")
def admin_only_route(user: AuthenticatedUser = Depends(require_admin)):
    return {"user_id": user.id, "role": user.role}


app.include_router(guard_test_router)


def test_missing_auth_header(client: TestClient):
    response = client.get("/api/v1/test-guard/patient-only")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "AUTHORIZATION_HEADER_MISSING"


def test_malformed_auth_header(client: TestClient):
    response = client.get(
        "/api/v1/test-guard/patient-only",
        headers={"Authorization": "Basic 12345"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "INVALID_AUTH_HEADER"


def test_patient_access_allowed(client: TestClient, patient_headers: dict):
    response = client.get("/api/v1/test-guard/patient-only", headers=patient_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "patient"
    assert data["user_id"] == "patient-123"


def test_patient_access_to_doctor_route_forbidden(client: TestClient, patient_headers: dict):
    response = client.get("/api/v1/test-guard/doctor-only", headers=patient_headers)
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"


def test_doctor_access_to_doctor_route_allowed(client: TestClient, doctor_headers: dict):
    response = client.get("/api/v1/test-guard/doctor-only", headers=doctor_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "doctor"
    assert data["user_id"] == "doctor-456"


def test_doctor_access_to_admin_route_forbidden(client: TestClient, doctor_headers: dict):
    response = client.get("/api/v1/test-guard/admin-only", headers=doctor_headers)
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"


def test_admin_access_allowed_everywhere(
    client: TestClient, admin_headers: dict
):
    # Admin is allowed on patient route
    r1 = client.get("/api/v1/test-guard/patient-only", headers=admin_headers)
    assert r1.status_code == 200

    # Admin is allowed on doctor route
    r2 = client.get("/api/v1/test-guard/doctor-only", headers=admin_headers)
    assert r2.status_code == 200

    # Admin is allowed on admin route
    r3 = client.get("/api/v1/test-guard/admin-only", headers=admin_headers)
    assert r3.status_code == 200
