from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.profile import UserRole
from app.schemas.department import DepartmentCreate
from app.schemas.doctor import DoctorCreate
from app.schemas.hospital import HospitalCreate
from app.schemas.patient import PatientCreate
from app.schemas.profile import ProfileCreate
from app.schemas.specialty import SpecialtyCreate
from app.services.department_service import department_service
from app.services.doctor_service import doctor_service
from app.services.hospital_service import hospital_service
from app.services.patient_service import patient_service
from app.services.profile_service import profile_service
from app.services.specialty_service import specialty_service


def test_public_and_read_endpoints(client: TestClient, db_session: Session):
    # 1. Create seed hospital, department, specialty, doctor
    hosp = hospital_service.create_hospital(
        db_session,
        HospitalCreate(name="St. Mary Hospital", code="SMH-01", address="100 Main St"),
    )
    dept = department_service.create_department(
        db_session,
        DepartmentCreate(
            hospital_id=hosp.id,
            name="Emergency Dept",
            code="EMRG",
        ),
    )
    spec = specialty_service.create_specialty(
        db_session,
        SpecialtyCreate(name="General Medicine", code="GEN-MED"),
    )
    doc_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="doc-auth-api-1",
            role=UserRole.DOCTOR,
            full_name="Dr. Sarah Connor",
            email="sarah@hospital.org",
            hospital_id=hosp.id,
        ),
    )
    doc = doctor_service.create_doctor(
        db_session,
        DoctorCreate(
            profile_id=doc_prof.id,
            hospital_id=hosp.id,
            department_id=dept.id,
            license_number="LIC-SARAH-1",
            years_of_experience=8,
        ),
    )

    # 2. Test GET /api/v1/hospitals
    res_hosp = client.get("/api/v1/hospitals")
    assert res_hosp.status_code == 200
    hosps_data = res_hosp.json()
    assert len(hosps_data) >= 1
    assert any(h["code"] == "SMH-01" for h in hosps_data)

    # 3. Test GET /api/v1/hospitals/{id}
    res_hosp_id = client.get(f"/api/v1/hospitals/{hosp.id}")
    assert res_hosp_id.status_code == 200
    assert res_hosp_id.json()["name"] == "St. Mary Hospital"

    # 4. Test GET /api/v1/departments (with hospital_id query param)
    res_dept = client.get(f"/api/v1/departments?hospital_id={hosp.id}")
    assert res_dept.status_code == 200
    assert len(res_dept.json()) == 1
    assert res_dept.json()[0]["code"] == "EMRG"

    # 5. Test GET /api/v1/specialties
    res_spec = client.get("/api/v1/specialties")
    assert res_spec.status_code == 200
    assert any(s["code"] == "GEN-MED" for s in res_spec.json())

    # 6. Test GET /api/v1/doctors and GET /api/v1/doctors/{id}
    res_docs = client.get(f"/api/v1/doctors?hospital_id={hosp.id}")
    assert res_docs.status_code == 200
    assert len(res_docs.json()) >= 1

    res_doc_id = client.get(f"/api/v1/doctors/{doc.id}")
    assert res_doc_id.status_code == 200
    assert res_doc_id.json()["license_number"] == "LIC-SARAH-1"
    assert res_doc_id.json()["profile"]["full_name"] == "Dr. Sarah Connor"


def test_not_found_endpoints(client: TestClient):
    res = client.get("/api/v1/hospitals/non-existent-hospital-id")
    assert res.status_code == 404
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "HOSPITAL_NOT_FOUND"

    res_doc = client.get("/api/v1/doctors/non-existent-doctor-id")
    assert res_doc.status_code == 404
    assert res_doc.json()["error"]["code"] == "DOCTOR_NOT_FOUND"


def test_patients_me_endpoint_flow(
    client: TestClient,
    db_session: Session,
    patient_token: str,
    patient_headers: dict,
):
    # Setup Patient tied to subject 'patient-123'
    prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Jane Doe",
            email="jane@example.com",
        ),
    )
    patient = patient_service.create_patient(
        db_session,
        PatientCreate(
            profile_id=prof.id,
            date_of_birth=date(1995, 8, 14),
            preferred_language="en",
        ),
    )

    # 1. Unauthenticated request must fail with 401
    res_unauth = client.get("/api/v1/patients/me")
    assert res_unauth.status_code == 401
    assert res_unauth.json()["error"]["code"] == "AUTHORIZATION_HEADER_MISSING"

    # 2. Authenticated request succeeds
    res_auth = client.get("/api/v1/patients/me", headers=patient_headers)
    assert res_auth.status_code == 200
    data = res_auth.json()
    assert data["id"] == patient.id
    assert data["profile"]["full_name"] == "Jane Doe"


def test_cross_patient_access_forbidden(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    other_patient_headers: dict,
):
    # Create patient 1 (auth: patient-123)
    p1_prof = profile_service.create_profile(
        db_session,
        ProfileCreate(
            auth_user_id="patient-123",
            role=UserRole.PATIENT,
            full_name="Patient One",
            email="p1@example.com",
        ),
    )
    p1 = patient_service.create_patient(
        db_session,
        PatientCreate(profile_id=p1_prof.id, date_of_birth=date(1990, 1, 1)),
    )

    # Patient 2 (auth: patient-999) attempts to read Patient 1's record
    res = client.get(f"/api/v1/patients/{p1.id}", headers=other_patient_headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ACCESS_FORBIDDEN"

    # Patient 1 accessing own record succeeds
    res_own = client.get(f"/api/v1/patients/{p1.id}", headers=patient_headers)
    assert res_own.status_code == 200
    assert res_own.json()["id"] == p1.id


def test_rbac_and_tenant_enforcement(
    client: TestClient,
    db_session: Session,
    patient_headers: dict,
    doctor_headers: dict,
    admin_headers: dict,
    global_admin_headers: dict,
):
    # Setup Hospital A
    hosp_a = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Hospital Alpha", code="ALPHA-01")
    )
    # Setup Hospital B
    hosp_b = hospital_service.create_hospital(
        db_session, HospitalCreate(name="Hospital Beta", code="BETA-01")
    )

    # 1. Patient cannot create hospital (Admin only)
    res_pat = client.post(
        "/api/v1/hospitals",
        json={"name": "New Hosp", "code": "NEW-01"},
        headers=patient_headers,
    )
    assert res_pat.status_code == 403
    assert res_pat.json()["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    # 2. Doctor cannot create hospital (Admin only)
    res_doc = client.post(
        "/api/v1/hospitals",
        json={"name": "New Hosp", "code": "NEW-01"},
        headers=doctor_headers,
    )
    assert res_doc.status_code == 403
    assert res_doc.json()["error"]["code"] == "INSUFFICIENT_ROLE_PERMISSIONS"

    # 3. Admin scoped to hosp-001 attempts to create department in hosp_b -> Cross-hospital forbidden!
    res_cross = client.post(
        "/api/v1/departments",
        json={"hospital_id": hosp_b.id, "name": "Radiology", "code": "RAD-1"},
        headers=admin_headers,  # Scoped to hosp-001
    )
    assert res_cross.status_code == 403
    assert res_cross.json()["error"]["code"] == "CROSS_HOSPITAL_FORBIDDEN"

    # 4. Global admin can create in any hospital
    res_global = client.post(
        "/api/v1/departments",
        json={"hospital_id": hosp_b.id, "name": "Radiology", "code": "RAD-1"},
        headers=global_admin_headers,
    )
    assert res_global.status_code == 201
    assert res_global.json()["code"] == "RAD-1"
