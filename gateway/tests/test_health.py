from fastapi.testclient import TestClient

from app.main import app


def test_health_liveness() -> None:
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "gateway"}


def test_ready_reports_unavailable_dependencies() -> None:
    with TestClient(app) as client:
        resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["db"] is False
    assert body["redis"] is False
