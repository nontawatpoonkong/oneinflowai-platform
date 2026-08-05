"""Health endpoint tests."""

import pytest
from fastapi.testclient import TestClient

import app.api.health as health_module


def test_liveness_returns_200_with_envelope(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "alive"
    assert set(body.keys()) == {"success", "message", "data", "error"}


def test_readiness_reports_per_dependency_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _unavailable_database(db) -> tuple[bool, str]:
        return False, "error: RuntimeError"

    monkeypatch.setattr(health_module, "_check_database", _unavailable_database)

    response = client.get("/health/readiness")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    checks = body["data"]["checks"]
    assert checks["redis"] == "ok"
    assert checks["qdrant"] == "ok"
    assert checks["database"].startswith("error")
    assert body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
