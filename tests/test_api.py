from unittest.mock import patch
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_api_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["simulation_only"] is True

def test_api_unknown_region():
    response = client.post("/api/run", json={"region_id": "does_not_exist", "seed": 1})
    assert response.status_code == 404

def test_api_weather_error_is_controlled():
    with patch("api.get_weather_data", side_effect=ValueError("bad payload")):
        response = client.post("/api/run", json={"region_id": "region_001", "seed": 1})
    assert response.status_code == 502
