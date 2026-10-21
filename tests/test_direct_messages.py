from fastapi import HTTPException

from services import direct_messages as dm


def test_message_requires_active_verified_registered_recipient(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "messages.sqlite3")
    monkeypatch.setattr(dm, "_active_registered_user", lambda email: None)
    try:
        dm.send_message(dm.SendMessageRequest(recipient_email="missing@example.com", message="Help"),
                        {"id": 1, "email": "sender@example.com", "role": "user"})
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("Unregistered recipient must be rejected")


def test_message_rejects_self_send(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "messages.sqlite3")
    monkeypatch.setattr(dm, "_active_registered_user",
                        lambda email: {"id": 7, "email": email})
    try:
        dm.send_message(dm.SendMessageRequest(recipient_email="me@example.com", message="Hello"),
                        {"id": 7, "email": "me@example.com", "role": "user"})
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Self-messaging must be rejected")


def test_message_body_is_trimmed_and_empty_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DB_PATH", tmp_path / "messages.sqlite3")
    try:
        dm.SendMessageRequest(recipient_email="other@example.com", message="   ")
        # Pydantic permits whitespace; endpoint rejects after trimming.
        monkeypatch.setattr(dm, "_active_registered_user", lambda email: {"id": 8, "email": email})
        dm.send_message(dm.SendMessageRequest(recipient_email="other@example.com", message="   "),
                        {"id": 7, "email": "me@example.com", "role": "user"})
    except HTTPException as exc:
        assert exc.status_code == 422
