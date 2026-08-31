"""
Automated tests for the Patient Registration REST API.

Run with: pytest test_main.py -v

These tests use FastAPI's TestClient against an in-memory SQLite database,
completely independent of the deployed Postgres instance and of Vapi —
no live server, no external calls, no cost.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Use an isolated in-memory SQLite DB for tests, regardless of the real DATABASE_URL
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "sqlite:///./test_patients.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Fresh schema for every test, so tests don't leak state into each other."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


VALID_PATIENT = {
    "first_name": "Jane",
    "last_name": "Doe",
    "date_of_birth": "1990-05-12",
    "sex": "Female",
    "phone_number": "5551234567",
    "email": "jane.doe@example.com",
    "address_line_1": "123 Main St",
    "city": "Austin",
    "state": "TX",
    "zip_code": "73301",
}


class TestCreatePatient:
    def test_create_valid_patient_returns_201(self, client):
        response = client.post("/patients", json=VALID_PATIENT)
        assert response.status_code == 201
        body = response.json()
        assert body["error"] is None
        assert body["data"]["first_name"] == "Jane"
        assert "patient_id" in body["data"]

    def test_create_with_invalid_state_returns_422(self, client):
        payload = {**VALID_PATIENT, "state": "Texas"}
        response = client.post("/patients", json=payload)
        assert response.status_code == 422
        assert response.json()["data"] is None

    def test_create_with_future_dob_returns_422(self, client):
        payload = {**VALID_PATIENT, "date_of_birth": "2099-01-01"}
        response = client.post("/patients", json=payload)
        assert response.status_code == 422

    def test_create_with_short_phone_number_returns_422(self, client):
        payload = {**VALID_PATIENT, "phone_number": "12345"}
        response = client.post("/patients", json=payload)
        assert response.status_code == 422

    def test_create_with_invalid_zip_returns_422(self, client):
        payload = {**VALID_PATIENT, "zip_code": "ABCDE"}
        response = client.post("/patients", json=payload)
        assert response.status_code == 422

    def test_create_with_invalid_sex_returns_422(self, client):
        payload = {**VALID_PATIENT, "sex": "Unknown"}
        response = client.post("/patients", json=payload)
        assert response.status_code == 422

    def test_create_duplicate_phone_number_returns_400(self, client):
        client.post("/patients", json=VALID_PATIENT)
        response = client.post("/patients", json=VALID_PATIENT)
        assert response.status_code == 400


class TestGetPatients:
    def test_list_patients_empty(self, client):
        response = client.get("/patients")
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_list_patients_after_create(self, client):
        client.post("/patients", json=VALID_PATIENT)
        response = client.get("/patients")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_filter_by_last_name(self, client):
        client.post("/patients", json=VALID_PATIENT)
        response = client.get("/patients?last_name=Doe")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

        response_no_match = client.get("/patients?last_name=Smith")
        assert response_no_match.json()["data"] == []

    def test_get_single_patient_by_id(self, client):
        created = client.post("/patients", json=VALID_PATIENT).json()["data"]
        response = client.get(f"/patients/{created['patient_id']}")
        assert response.status_code == 200
        assert response.json()["data"]["first_name"] == "Jane"

    def test_get_nonexistent_patient_returns_404(self, client):
        response = client.get("/patients/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestUpdatePatient:
    def test_partial_update_succeeds(self, client):
        created = client.post("/patients", json=VALID_PATIENT).json()["data"]
        response = client.put(
            f"/patients/{created['patient_id']}", json={"city": "Oakland"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["city"] == "Oakland"
        # Unrelated fields should be unchanged
        assert response.json()["data"]["first_name"] == "Jane"

    def test_update_with_invalid_field_returns_422(self, client):
        created = client.post("/patients", json=VALID_PATIENT).json()["data"]
        response = client.put(
            f"/patients/{created['patient_id']}", json={"state": "NotAState"}
        )
        assert response.status_code == 422

    def test_update_nonexistent_patient_returns_404(self, client):
        response = client.put(
            "/patients/00000000-0000-0000-0000-000000000000",
            json={"city": "Nowhere"},
        )
        assert response.status_code == 404


class TestDeletePatient:
    def test_soft_delete_removes_from_list(self, client):
        created = client.post("/patients", json=VALID_PATIENT).json()["data"]
        delete_response = client.delete(f"/patients/{created['patient_id']}")
        assert delete_response.status_code == 200

        list_response = client.get("/patients")
        assert list_response.json()["data"] == []

    def test_delete_nonexistent_patient_returns_404(self, client):
        response = client.delete("/patients/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestRootAndHealthCheck:
    def test_root_returns_status(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "running"