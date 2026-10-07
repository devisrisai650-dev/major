from fastapi.testclient import TestClient

from api import app


client = TestClient(app)


def test_health_and_metrics_endpoints():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["simulation_only"] is True

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert b"floodai_api_requests_total" in metrics.content
