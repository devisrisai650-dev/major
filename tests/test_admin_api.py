import pytest
from fastapi.testclient import TestClient

import api
import services.alert_monitor as alert_monitor
import services.auth_service as auth_service

ADMIN_EMAIL = "platform.admin@gmail.com"
ADMIN_PASSWORD = "a-very-long-admin-secret-123"
USER_EMAIL = "regular@gmail.com"
USER_PASSWORD = "a-long-user-password"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_service, "DB_PATH", tmp_path / "auth.sqlite3")
    monkeypatch.setenv("FLOODAI_ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("FLOODAI_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("FLOODAI_EMAIL_VERIFICATION_REQUIRED", "false")
    monkeypatch.setenv("FLOODAI_ALERT_MONITOR_ENABLED", "false")
    with TestClient(api.app) as test_client:
        yield test_client


def sign_in(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def test_admin_alert_status_includes_monitor_last_run(client, monkeypatch):
    monkeypatch.setitem(alert_monitor._STATE, "last_run_at", "2026-10-20T06:00:00+00:00")
    monkeypatch.setitem(alert_monitor._STATE, "runs", 3)
    monkeypatch.setitem(alert_monitor._STATE, "regions", [
        {"region_id": "region_001", "region_name": "Kakinada", "assessment_status": "NOT_ASSESSED",
         "official_alert_sent": 0, "indicator_sent": 2, "indicator_eligible": True,
         "indicator_duplicate": False, "delivery_errors": 0, "indicator_note": None, "error": None}])
    sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    body = client.get("/api/admin/alerts/status").json()
    assert body["monitor_last_run"]["runs"] == 3
    assert body["monitor_last_run"]["regions"][0]["indicator_sent"] == 2


def test_admin_alert_history_lists_dispatches_newest_first(client):
    auth_service.reserve_alert_dispatch("region_001", "INDICATOR_HIGH", "HIGH:2026-10-19")
    auth_service.finish_alert_dispatch("region_001", "INDICATOR_HIGH", "HIGH:2026-10-19", 4)
    auth_service.reserve_alert_dispatch("region_002", "INDICATOR_MODERATE", "MODERATE:2026-10-20")
    auth_service.finish_alert_dispatch("region_002", "INDICATOR_MODERATE", "MODERATE:2026-10-20", 2)
    sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    dispatches = client.get("/api/admin/alerts/history").json()["dispatches"]
    assert [d["event_id"] for d in dispatches] == ["MODERATE:2026-10-20", "HIGH:2026-10-19"]
    assert dispatches[0]["recipient_count"] == 2


def test_admin_alert_endpoints_reject_regular_and_anonymous_users(client):
    assert client.get("/api/admin/alerts/history").status_code == 401
    assert client.get("/api/admin/alerts/status").status_code == 401
    assert client.post("/api/auth/register", json={"email": USER_EMAIL, "password": USER_PASSWORD}).status_code == 201
    sign_in(client, USER_EMAIL, USER_PASSWORD)
    assert client.get("/api/admin/alerts/history").status_code == 403
    assert client.get("/api/admin/alerts/status").status_code == 403


def test_admin_smtp_test_failure_reports_the_reason(client, monkeypatch):
    import services.auth_api as auth_api

    def broken(*_args, **_kwargs):
        raise RuntimeError("Email is not configured. Set FLOODAI_SMTP_USER and FLOODAI_SMTP_APP_PASSWORD.")

    monkeypatch.setattr(auth_api, "send_email", broken)
    sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    response = client.post("/api/admin/email-test")
    assert response.status_code == 502
    assert "not configured" in response.json()["detail"]


def test_admin_page_is_served_only_to_the_admin(client):
    assert client.get("/admin", follow_redirects=False).status_code == 303
    sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    page = client.get("/admin")
    assert page.status_code == 200
    assert "Alert dispatch history" in page.text and "Simulation runner" in page.text
