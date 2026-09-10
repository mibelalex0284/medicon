import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
# Import all models so metadata knows all tables
from app import models as _models  # noqa: F401

# In-memory SQLite engine for fast, isolated tests
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Yields a clean transactional database session per test."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> TestClient:
    """HTTP client fixture with get_db overridden to use test database session."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def patient_token() -> str:
    return create_access_token(
        subject="patient-123",
        role="patient",
        hospital_id="hosp-001",
    )


@pytest.fixture
def other_patient_token() -> str:
    return create_access_token(
        subject="patient-999",
        role="patient",
        hospital_id="hosp-001",
    )


@pytest.fixture
def doctor_token() -> str:
    return create_access_token(
        subject="doctor-456",
        role="doctor",
        hospital_id="hosp-001",
    )


@pytest.fixture
def other_hospital_doctor_token() -> str:
    return create_access_token(
        subject="doctor-other",
        role="doctor",
        hospital_id="hosp-002",
    )


@pytest.fixture
def admin_token() -> str:
    return create_access_token(
        subject="admin-789",
        role="admin",
        hospital_id="hosp-001",
    )


@pytest.fixture
def global_admin_token() -> str:
    return create_access_token(
        subject="admin-global",
        role="admin",
        hospital_id=None,
    )


@pytest.fixture
def patient_headers(patient_token: str) -> dict:
    return {"Authorization": f"Bearer {patient_token}"}


@pytest.fixture
def other_patient_headers(other_patient_token: str) -> dict:
    return {"Authorization": f"Bearer {other_patient_token}"}


@pytest.fixture
def doctor_headers(doctor_token: str) -> dict:
    return {"Authorization": f"Bearer {doctor_token}"}


@pytest.fixture
def other_hospital_doctor_headers(other_hospital_doctor_token: str) -> dict:
    return {"Authorization": f"Bearer {other_hospital_doctor_token}"}


@pytest.fixture
def admin_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def global_admin_headers(global_admin_token: str) -> dict:
    return {"Authorization": f"Bearer {global_admin_token}"}
