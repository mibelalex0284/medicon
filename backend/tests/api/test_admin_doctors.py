from fastapi.testclient import TestClient


def test_admin_list_doctors_unauthenticated(client: TestClient):
    """GET /api/v1/doctors/admin/list must reject unauthenticated requests with 401."""
    response = client.get("/api/v1/doctors/admin/list")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "AUTHORIZATION_HEADER_MISSING"


def test_admin_list_doctors_forbidden_for_patient(client: TestClient, patient_headers: dict):
    """GET /api/v1/doctors/admin/list must reject patients with 403."""
    response = client.get("/api/v1/doctors/admin/list", headers=patient_headers)
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"


def test_admin_list_doctors_forbidden_for_doctor(client: TestClient, doctor_headers: dict):
    """GET /api/v1/doctors/admin/list must reject doctors without admin role with 403."""
    response = client.get("/api/v1/doctors/admin/list", headers=doctor_headers)
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"


def test_admin_list_doctors_authorized_for_admin(client: TestClient, admin_headers: dict):
    """GET /api/v1/doctors/admin/list succeeds for authorized administrators."""
    response = client.get("/api/v1/doctors/admin/list", headers=admin_headers)
    assert response.status_code == 200
    doctors = response.json()
    assert isinstance(doctors, list)
    # Verify doctor objects structure
    for doc in doctors:
        assert "id" in doc
        assert "profile" in doc
        assert "full_name" in doc["profile"]
        assert "email" in doc["profile"]
        assert "license_number" in doc
        assert "is_active" in doc
        assert "specialties" in doc
