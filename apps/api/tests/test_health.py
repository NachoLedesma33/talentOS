from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.api.routes import health as health_routes
from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def override_settings(settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: settings


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "talentos", "version": "0.1.0"}


def test_ready_returns_ok_with_valid_settings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_routes, "_check_database", lambda: True)
    monkeypatch.setattr(health_routes, "_check_redis", lambda settings: True)
    override_settings(Settings())

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"database": "ok", "redis": "ok"},
    }
    assert response.headers["X-Request-ID"]


def test_ready_reports_database_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_routes, "_check_database", lambda: False)
    monkeypatch.setattr(health_routes, "_check_redis", lambda settings: True)
    override_settings(Settings())

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["dependencies"] == {"database": "error", "redis": "ok"}
    assert "database" in body["detail"]
    assert "redis" not in body["detail"]
    assert response.headers["X-Request-ID"]


def test_ready_reports_redis_failure_without_leaking_dsn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_routes, "_check_database", lambda: True)
    monkeypatch.setattr(health_routes, "_check_redis", lambda settings: False)
    override_settings(Settings(REDIS_URL="redis://user:synthetic-secret@redis:6379/0"))

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["dependencies"] == {"database": "ok", "redis": "error"}
    assert "redis" in body["detail"]
    assert "synthetic-secret" not in response.text
    assert "redis://" not in response.text
    assert response.headers["X-Request-ID"]


def test_ready_reports_both_failures(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_routes, "_check_database", lambda: False)
    monkeypatch.setattr(health_routes, "_check_redis", lambda settings: False)
    override_settings(Settings())

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["dependencies"] == {"database": "error", "redis": "error"}
    assert "database" in body["detail"]
    assert "redis" in body["detail"]


def test_ready_returns_actionable_503_when_setting_missing(client: TestClient) -> None:
    override_settings(Settings(APP_NAME=""))

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["dependencies"] == {"database": "skipped", "redis": "skipped"}
    assert "APP_NAME" in body["detail"]
    assert "PostgreSQL" in body["detail"]
    assert response.headers["X-Request-ID"]


def test_unknown_route_uses_consistent_error_envelope(client: TestClient) -> None:
    response = client.get("/ruta-inexistente")

    assert response.status_code == 404
    error = response.json()["error"]
    assert set(error) == {"code", "message", "request_id"}
    assert error["code"] == "not_found"


def test_request_id_generated_and_propagated(client: TestClient) -> None:
    generated = client.get("/health")
    generated_id = generated.headers.get("X-Request-ID")
    assert generated_id

    missing = client.get("/ruta-inexistente")
    assert missing.json()["error"]["request_id"] == missing.headers["X-Request-ID"]

    propagated = client.get("/health", headers={"X-Request-ID": "req-from-caller"})
    assert propagated.headers["X-Request-ID"] == "req-from-caller"


def test_security_headers_present_in_non_production(client: TestClient) -> None:
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert "Strict-Transport-Security" not in response.headers
    assert "Content-Security-Policy" not in response.headers


def test_production_redirects_http_to_https(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "settings", Settings(APP_ENV="production"))

    response = client.get("/health?probe=1", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://testserver/health?probe=1"
    assert response.headers["X-Request-ID"]
    assert (
        response.headers["Content-Security-Policy"]
        == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    assert "Strict-Transport-Security" not in response.headers


def test_production_trusts_forwarded_proto_for_hsts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main_module, "settings", Settings(APP_ENV="production"))

    response = client.get(
        "/health", headers={"X-Forwarded-Proto": "https, http"}, follow_redirects=False
    )

    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["Content-Security-Policy"]
