"""Healthcheck endpoint tests.

Quick smoke test for the health endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


@pytest.mark.unit
def test_health_returns_200(client: TestClient) -> None:
    """/health 200 OK + version döner."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["service"] == "nodrat-api"


@pytest.mark.unit
def test_readiness_returns_check_dict(client: TestClient) -> None:
    """/readiness checks dict + ready bool döner."""
    response = client.get("/readiness")
    # 503 olabilir Faz 0 implementation'a göre
    assert response.status_code in {200, 503}
    data = response.json()
    assert "ready" in data
    assert "checks" in data
    assert isinstance(data["checks"], dict)
