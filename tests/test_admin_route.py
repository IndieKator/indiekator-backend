import pytest
from fastapi.testclient import TestClient

from app.api.routes import admin
from app.main import app

LEGACY_PATHS = [
    "/api/sentiment/current",
    "/api/sentiment/history",
    "/api/sentiment/breakdown",
]


@pytest.mark.parametrize("path", LEGACY_PATHS)
def test_removed_legacy_sentiment_endpoints_return_404(path: str) -> None:
    assert TestClient(app).get(path).status_code == 404


def test_retained_routes_are_still_registered() -> None:
    registered = set(app.openapi()["paths"])

    assert {"/api/health", "/api/fgi", "/api/zones", "/api/admin/ingest"} <= registered


def test_no_registered_route_path_mentions_sentiment() -> None:
    assert [path for path in app.openapi()["paths"] if "sentiment" in path] == []


def test_trigger_ingest_rejects_a_mismatched_admin_secret(monkeypatch) -> None:
    monkeypatch.setattr(
        admin, "run_ingestion", lambda: pytest.fail("ingestion must not run")
    )

    response = TestClient(app).post(
        "/api/admin/ingest", headers={"X-Admin-Secret": "not-the-secret"}
    )

    assert response.status_code == 403


def test_trigger_ingest_requires_the_admin_secret_header() -> None:
    response = TestClient(app).post("/api/admin/ingest")

    assert response.status_code == 422


def test_trigger_ingest_returns_the_consolidated_ingestion_payload(monkeypatch) -> None:
    payload = {
        "status": "success",
        "rows_upserted": 50,
        "message": "Ingested 50 weekly FGI snapshots and rebuilt 6 zone periods",
    }
    monkeypatch.setattr(admin, "run_ingestion", lambda: payload)
    monkeypatch.setattr(
        admin, "get_settings", lambda: _settings_with_secret("test-secret")
    )

    response = TestClient(app).post(
        "/api/admin/ingest", headers={"X-Admin-Secret": "test-secret"}
    )

    assert response.status_code == 200
    assert response.json() == payload


def _settings_with_secret(secret: str) -> object:
    class _Settings:
        admin_secret = secret

    return _Settings()
