from starlette.requests import Request

import services.auth_service as auth_service
import services.alert_service as alert_service


def use_test_database(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_service, "DB_PATH", tmp_path / "auth.sqlite3")
    monkeypatch.delenv("FLOODAI_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("FLOODAI_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("FLOODAI_EMAIL_VERIFICATION_REQUIRED", "true")
    auth_service.init_db()


def test_email_verification_can_be_disabled_for_prototype(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    monkeypatch.setenv("FLOODAI_EMAIL_VERIFICATION_REQUIRED", "false")
    user_id, token = auth_service.create_user("Test.User@gmail.com", "correct horse battery")
    assert user_id > 0
    assert token == ""
    user = auth_service.authenticate("test.user@gmail.com", "correct horse battery")
    assert user is not None
    assert user["role"] == "user"
    assert user["is_verified"] is True
    assert auth_service.authenticate("test.user@gmail.com", "wrong password") is None


def test_email_verification_can_be_required(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    monkeypatch.setenv("FLOODAI_EMAIL_VERIFICATION_REQUIRED", "true")
    user_id, token = auth_service.create_user("verified-later@gmail.com", "correct horse battery")
    assert user_id > 0
    assert token
    assert auth_service.authenticate("verified-later@gmail.com", "correct horse battery") is None
    assert auth_service.verify_email_token(token) is True
    assert auth_service.authenticate("verified-later@gmail.com", "correct horse battery") is not None


def test_admin_is_bootstrapped_only_from_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_service, "DB_PATH", tmp_path / "auth.sqlite3")
    monkeypatch.setenv("FLOODAI_ADMIN_EMAIL", "platform.admin@gmail.com")
    monkeypatch.setenv("FLOODAI_ADMIN_PASSWORD", "a-very-long-admin-secret-123")
    auth_service.init_db()
    admin = auth_service.authenticate("platform.admin@gmail.com", "a-very-long-admin-secret-123")
    assert admin is not None
    assert admin["role"] == "admin"
    assert auth_service.create_user("another@gmail.com", "a-long-user-password")[0] > 0


def test_session_cookie_resolves_server_side_user(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    user_id, verify_token = auth_service.create_user("session@gmail.com", "a-long-user-password")
    assert user_id > 0
    assert auth_service.verify_email_token(verify_token) is True
    raw, _ = auth_service.create_session(user_id)
    request = Request({
        "type": "http", "method": "GET", "path": "/",
        "headers": [(b"cookie", f"floodai_session={raw}".encode())],
    })
    assert auth_service.get_user_from_request(request)["email"] == "session@gmail.com"


def test_alert_dispatch_requires_verified_official_evidence(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(alert_service, "send_flood_alert", lambda *args, **kwargs: sent.append(args))
    result = alert_service.dispatch_verified_flood_alert(
        region_id="region_001", region_name="Kakinada",
        assessment={"status": "WARNING", "complete": True, "event_id": "event-1"},
        evidence={"official_thresholds_verified": True, "fresh_qc_gauge": True,
                  "source_is_authoritative": True, "simulation_only": True},
    )
    assert result["eligible"] is False
    assert sent == []


def test_verified_alert_sends_once_and_suppresses_duplicates(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    user_id, token = auth_service.create_user("alerts@gmail.com", "a-long-user-password")
    assert user_id > 0
    assert auth_service.verify_email_token(token)
    sent = []
    monkeypatch.setattr(alert_service, "send_flood_alert", lambda recipient, **kwargs: sent.append(recipient))
    args = dict(
        region_id="region_001", region_name="Kakinada",
        assessment={"status": "WARNING", "complete": True, "event_id": "official-event-1",
                    "observed_at": "2026-10-12T12:00:00+05:30", "message": "Official warning issued."},
        evidence={"official_thresholds_verified": True, "fresh_qc_gauge": True,
                  "source_is_authoritative": True, "simulation_only": False, "source_name": "Official authority"},
    )
    first = alert_service.dispatch_verified_flood_alert(**args)
    second = alert_service.dispatch_verified_flood_alert(**args)
    assert first["eligible"] is True
    assert first["sent"] == 1
    assert second["duplicate"] is True
    assert sent == ["alerts@gmail.com"]


def test_login_attempts_are_throttled_and_cleared_after_success(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    key = "test-login-attempt-key"
    assert auth_service.login_is_locked(key) is False
    for _ in range(5):
        auth_service.record_login_failure(key)
    assert auth_service.login_is_locked(key) is True
    auth_service.clear_login_failures(key)
    assert auth_service.login_is_locked(key) is False


def test_environmental_indicator_emails_for_moderate_high_and_deduplicates(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    user_id, token = auth_service.create_user("indicator@gmail.com", "a-long-user-password")
    assert user_id > 0
    assert auth_service.verify_email_token(token)
    sent = []
    monkeypatch.setattr(alert_service, "send_environmental_indicator_email",
                        lambda recipient, **kwargs: sent.append((recipient, kwargs["level"])))
    args = dict(region_id="region_001", region_name="Kakinada", level="HIGH",
                event_id="HIGH:2026-10-14T12:00", observed_at="2026-10-14T12:00",
                source="Open-Meteo live weather data", indicators="current rainfall=12 mm")
    first = alert_service.dispatch_environmental_indicator_alert(**args)
    second = alert_service.dispatch_environmental_indicator_alert(**args)
    assert first["sent"] == 1
    assert second["duplicate"] is True
    assert sent == [("indicator@gmail.com", "HIGH")]


def test_environmental_indicator_email_rejects_low_level(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(alert_service, "send_environmental_indicator_email",
                        lambda *args, **kwargs: sent.append(True))
    result = alert_service.dispatch_environmental_indicator_alert(
        region_id="region_001", region_name="Kakinada", level="LOW",
        event_id="low-event", observed_at="2026-10-14T12:00",
        source="Open-Meteo", indicators="rainfall=0 mm")
    assert result["eligible"] is False
    assert sent == []


def _register_alert_user(email="retry@gmail.com"):
    user_id, token = auth_service.create_user(email, "a-long-user-password")
    assert auth_service.verify_email_token(token)
    return user_id


def test_failed_delivery_is_audited_and_retried_next_cycle(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    _register_alert_user()
    args = dict(region_id="region_001", region_name="Kakinada", level="HIGH",
                event_id="HIGH:2026-10-20", observed_at="2026-10-20T11:45",
                source="Open-Meteo live weather data", indicators="current rainfall=12 mm")

    def broken(*_args, **_kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(alert_service, "send_environmental_indicator_email", broken)
    first = alert_service.dispatch_environmental_indicator_alert(**args)
    assert first["sent"] == 0 and first["delivery_errors"] == 1 and first["released_for_retry"] is True
    failures = [a for a in auth_service.admin_snapshot()["recent_activity"] if a["action"] == "alert_email_failed"]
    assert failures and "smtp down" in failures[0]["details"]

    sent = []
    monkeypatch.setattr(alert_service, "send_environmental_indicator_email",
                        lambda recipient, **kwargs: sent.append(recipient))
    second = alert_service.dispatch_environmental_indicator_alert(**args)
    assert second["sent"] == 1 and "duplicate" not in second
    assert sent == ["retry@gmail.com"]
    assert alert_service.dispatch_environmental_indicator_alert(**args)["duplicate"] is True


def test_no_subscribers_does_not_consume_the_event(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    monkeypatch.setattr(alert_service, "send_environmental_indicator_email", lambda *a, **k: None)
    args = dict(region_id="region_001", region_name="Kakinada", level="MODERATE",
                event_id="MODERATE:2026-10-20", observed_at="2026-10-20T09:00",
                source="Open-Meteo live weather data", indicators="current rainfall=4 mm")
    assert alert_service.dispatch_environmental_indicator_alert(**args)["sent"] == 0
    _register_alert_user("late@gmail.com")
    assert alert_service.dispatch_environmental_indicator_alert(**args)["sent"] == 1


def test_indicator_email_body_uses_real_newlines(monkeypatch):
    import services.email_service as email_service
    captured = {}
    monkeypatch.setattr(email_service, "send_email", lambda recipient, subject, body: captured.update(body=body))
    email_service.send_environmental_indicator_email(
        "a@gmail.com", region="Kakinada", level="HIGH", observed_at="2026-10-20T11:45",
        source="Open-Meteo", indicators="current rainfall=12 mm")
    assert "\\n" not in captured["body"]
    assert "Indicator level: HIGH\nObservation time:" in captured["body"]


def test_monitor_sends_one_indicator_notice_per_level_per_day(monkeypatch, tmp_path):
    import services.alert_monitor as alert_monitor
    use_test_database(monkeypatch, tmp_path)
    _register_alert_user("daily@gmail.com")
    sent = []
    monkeypatch.setattr(alert_service, "send_environmental_indicator_email",
                        lambda recipient, **kwargs: sent.append(kwargs["observed_at"]))

    class FakeGauge:
        def get_water_level(self, region):
            return {"available": False}

    monkeypatch.setattr(alert_monitor, "CsvReplayProvider", FakeGauge)
    monkeypatch.setattr(alert_monitor, "get_discharge_analysis", lambda lat, lon: {"available": False})
    region = {"id": "region_001", "name": "Kakinada", "latitude": 1.0, "longitude": 2.0}
    for stamp in ("2026-10-20T11:45", "2026-10-20T12:00", "2026-10-20T12:15"):
        monkeypatch.setattr(alert_monitor, "get_weather_data", lambda lat, lon, tz, s=stamp: {
            "current": {"time": s, "rain_mm": 12.0}, "rainfall_windows": {"last_6h_precipitation_mm": 15.0}})
        alert_monitor.check_region(region)
    assert sent == ["2026-10-20T11:45"]


def test_configured_alert_recipient_is_included_and_deduplicated(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    _register_alert_user("pleaserespond.vnr@gmail.com")
    monkeypatch.setenv("FLOODAI_ALERT_RECIPIENT", "pleaserespond.vnr@gmail.com")
    assert auth_service.get_verified_alert_recipients() == ["pleaserespond.vnr@gmail.com"]


def test_configured_alert_recipient_is_added_to_registered_users(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    _register_alert_user("registered-alerts@gmail.com")
    monkeypatch.setenv("FLOODAI_ALERT_RECIPIENT", "pleaserespond.vnr@gmail.com")
    recipients = auth_service.get_verified_alert_recipients()
    assert recipients == ["registered-alerts@gmail.com", "pleaserespond.vnr@gmail.com"]


def test_invalid_configured_alert_recipient_is_ignored(monkeypatch, tmp_path):
    use_test_database(monkeypatch, tmp_path)
    monkeypatch.setenv("FLOODAI_ALERT_RECIPIENT", "not-an-email")
    assert auth_service.get_verified_alert_recipients() == []
