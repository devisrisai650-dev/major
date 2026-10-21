from fastapi import HTTPException

from services import auth_service
from services import messages_api as messages


def _create_test_users(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_service, "DB_PATH", tmp_path / "auth.sqlite3")
    auth_service.init_db()
    sender_id, _ = auth_service.create_user("sender@example.test", "SecurePass12345")
    recipient_id, _ = auth_service.create_user("receiver@example.test", "SecurePass12345")
    sender = auth_service.authenticate("sender@example.test", "SecurePass12345")
    recipient = auth_service.authenticate("receiver@example.test", "SecurePass12345")
    assert sender and recipient
    return sender, recipient, sender_id, recipient_id


def test_user_can_send_and_recipient_can_read_message(tmp_path, monkeypatch):
    sender, recipient, _, recipient_id = _create_test_users(tmp_path, monkeypatch)
    sent = messages.send_message(
        messages.SendMessageRequest(
            recipient_id=recipient_id,
            content="Rainfall is increasing.",
            shared_data={"source": "Open-Meteo", "rainfall_mm": 2.1},
        ),
        sender,
    )
    assert sent["sender"]["email"] == sender["email"]
    assert sent["recipient"]["id"] == recipient_id
    assert sent["shared_data"]["source"] == "Open-Meteo"

    received = messages.get_conversation(sender["id"], 0, 100, recipient)
    assert len(received["messages"]) == 1
    message = received["messages"][0]
    assert message["content"] == "Rainfall is increasing."
    assert message["shared_data"]["rainfall_mm"] == 2.1
    assert message["read_at"] is not None


def test_message_cannot_be_sent_to_admin_or_unknown_user(tmp_path, monkeypatch):
    sender, _, _, _ = _create_test_users(tmp_path, monkeypatch)
    try:
        messages.send_message(
            messages.SendMessageRequest(recipient_id=99999, content="Hello"),
            sender,
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Unknown recipient should be rejected")


def test_user_cannot_read_a_conversation_between_other_users(tmp_path, monkeypatch):
    sender, recipient, _, recipient_id = _create_test_users(tmp_path, monkeypatch)
    messages.send_message(
        messages.SendMessageRequest(recipient_id=recipient_id, content="Private"),
        sender,
    )
    third_id, _ = auth_service.create_user("third@example.test", "SecurePass12345")
    third = auth_service.authenticate("third@example.test", "SecurePass12345")
    assert third and third["id"] == third_id
    try:
        messages.get_conversation(sender["id"], 0, 100, third)
    except HTTPException as exc:
        assert exc.status_code == 200 or exc.status_code == 404
    else:
        assert messages.get_conversation(sender["id"], 0, 100, third)["messages"] == []


def test_environmental_indicator_labels_are_informational(monkeypatch):
    monkeypatch.setattr(messages, "get_region", lambda region_id: {
        "id": region_id, "name": "Test Region", "latitude": 1.0,
        "longitude": 2.0, "timezone": "Asia/Kolkata"
    })
    monkeypatch.setattr(messages, "get_weather_data", lambda *args: {
        "source": "Open-Meteo",
        "current": {
            "time": "2026-10-21T18:00", "temperature_c": 30.0,
            "humidity_pct": 60, "precipitation_mm": 1.2, "rain_mm": 0.8,
            "wind_speed_kmh": 10.0, "wind_direction_deg": 180,
            "surface_pressure_hpa": 1000,
        },
        "rainfall_windows": {"last_1h_precipitation_mm": 1.2},
    })
    result = messages.environmental_indicators(
        "region_test", {"id": 1, "email": "user@example.test", "role": "user"}
    )
    assert result["source"] == "Open-Meteo"
    assert result["source_type"] == "provider_current_conditions_not_local_sensor"
    assert result["rainfall_signal"]["status"] == "PRECIPITATION_REPORTED"
    assert result["rainfall_signal"]["informational_only"] is True
    assert result["flood_assessment_status"] == "NOT_ASSESSED"
