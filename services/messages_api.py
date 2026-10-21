"""Authenticated user messaging and provider-based environmental indicators."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import auth_service
from services.auth_service import require_user
from services.region_manager import get_region
from services.weather_service import get_weather_data

router = APIRouter(tags=["messages-and-environmental-indicators"])


def init_messages_db() -> None:
    """Create the messaging table inside the existing authentication database."""
    with auth_service._connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS user_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            recipient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            shared_data_json TEXT,
            created_at TEXT NOT NULL,
            read_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_user_messages_pair
            ON user_messages(sender_user_id, recipient_user_id, id);
        CREATE INDEX IF NOT EXISTS idx_user_messages_recipient
            ON user_messages(recipient_user_id, read_at, id);
        """)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _user_contact(db, user_id: int) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT id, email, role, is_active, is_verified FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if not row or row["role"] != "user" or not row["is_active"] or not row["is_verified"]:
        return None
    return {"id": int(row["id"]), "email": row["email"]}


def list_contacts(user: dict[str, Any]) -> dict[str, Any]:
    if user.get("role") != "user":
        raise HTTPException(403, "Messaging is available to regular user accounts.")
    with auth_service._connect() as db:
        rows = db.execute(
            """SELECT id, email FROM users
               WHERE role='user' AND is_active=1 AND is_verified=1 AND id<>?
               ORDER BY email COLLATE NOCASE""",
            (user["id"],),
        ).fetchall()
    return {"contacts": [{"id": int(row["id"]), "email": row["email"]} for row in rows]}


class SendMessageRequest(BaseModel):
    recipient_id: int = Field(gt=0)
    content: str = Field(default="Shared environmental snapshot", min_length=1, max_length=4000)
    shared_data: dict[str, Any] | None = None


def send_message(payload: SendMessageRequest, user: dict[str, Any]) -> dict[str, Any]:
    if user.get("role") != "user":
        raise HTTPException(403, "Messaging is available to regular user accounts.")
    content = payload.content.strip()
    if not content and payload.shared_data is None:
        raise HTTPException(422, "Enter a message or attach environmental data.")
    if not content:
        content = "Shared environmental snapshot"
    shared_json = None
    if payload.shared_data is not None:
        shared_json = json.dumps(payload.shared_data, ensure_ascii=False, separators=(",", ":"))
        if len(shared_json.encode("utf-8")) > 12000:
            raise HTTPException(413, "Shared data attachment is too large (12 KB maximum).")
    if payload.recipient_id == int(user["id"]):
        raise HTTPException(422, "Choose another registered user as the recipient.")

    init_messages_db()
    created_at = _now()
    with auth_service._connect() as db:
        recipient = _user_contact(db, payload.recipient_id)
        if not recipient:
            raise HTTPException(404, "Recipient account not found or not eligible for messaging.")
        cursor = db.execute(
            """INSERT INTO user_messages
               (sender_user_id, recipient_user_id, content, shared_data_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (int(user["id"]), payload.recipient_id, content, shared_json, created_at),
        )
        message_id = int(cursor.lastrowid)
    return {
        "id": message_id,
        "sender": {"id": int(user["id"]), "email": user["email"]},
        "recipient": recipient,
        "content": content,
        "shared_data": payload.shared_data,
        "created_at": created_at,
        "read_at": None,
    }


def get_conversation(
    peer_id: int,
    after_id: int,
    limit: int,
    user: dict[str, Any],
) -> dict[str, Any]:
    if user.get("role") != "user":
        raise HTTPException(403, "Messaging is available to regular user accounts.")
    if peer_id == int(user["id"]):
        raise HTTPException(422, "Choose another registered user.")
    init_messages_db()
    with auth_service._connect() as db:
        peer = _user_contact(db, peer_id)
        if not peer:
            raise HTTPException(404, "Conversation participant not found.")
        if after_id > 0:
            rows = db.execute(
                """SELECT m.*, s.email AS sender_email, r.email AS recipient_email
                   FROM user_messages m
                   JOIN users s ON s.id=m.sender_user_id
                   JOIN users r ON r.id=m.recipient_user_id
                   WHERE ((m.sender_user_id=? AND m.recipient_user_id=?)
                       OR (m.sender_user_id=? AND m.recipient_user_id=?))
                     AND m.id>?
                   ORDER BY m.id ASC LIMIT ?""",
                (int(user["id"]), peer_id, peer_id, int(user["id"]), after_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT m.*, s.email AS sender_email, r.email AS recipient_email
                   FROM user_messages m
                   JOIN users s ON s.id=m.sender_user_id
                   JOIN users r ON r.id=m.recipient_user_id
                   WHERE ((m.sender_user_id=? AND m.recipient_user_id=?)
                       OR (m.sender_user_id=? AND m.recipient_user_id=?))
                   ORDER BY m.id DESC LIMIT ?""",
                (int(user["id"]), peer_id, peer_id, int(user["id"]), limit),
            ).fetchall()
            rows = list(reversed(rows))
        unread_ids = [
            int(row["id"]) for row in rows
            if int(row["recipient_user_id"]) == int(user["id"]) and row["read_at"] is None
        ]
        if unread_ids:
            placeholders = ",".join("?" for _ in unread_ids)
            read_at = _now()
            db.execute(
                f"UPDATE user_messages SET read_at=? WHERE id IN ({placeholders})",
                [read_at, *unread_ids],
            )
            rows = db.execute(
                f"""SELECT m.*, s.email AS sender_email, r.email AS recipient_email
                    FROM user_messages m
                    JOIN users s ON s.id=m.sender_user_id
                    JOIN users r ON r.id=m.recipient_user_id
                    WHERE m.id IN ({placeholders}) ORDER BY m.id ASC""",
                unread_ids,
            ).fetchall() + [row for row in rows if int(row["id"]) not in unread_ids]
            rows = sorted(rows, key=lambda row: int(row["id"]))
    messages = []
    for row in rows:
        messages.append({
            "id": int(row["id"]),
            "sender": {"id": int(row["sender_user_id"]), "email": row["sender_email"]},
            "recipient": {"id": int(row["recipient_user_id"]), "email": row["recipient_email"]},
            "content": row["content"],
            "shared_data": json.loads(row["shared_data_json"]) if row["shared_data_json"] else None,
            "created_at": row["created_at"],
            "read_at": row["read_at"],
        })
    return {"peer": peer, "messages": messages, "poll_interval_ms": 2500}


@router.get("/api/messages/contacts")
def message_contacts(user: dict[str, Any] = Depends(require_user)):
    return list_contacts(user)


@router.post("/api/messages")
def create_message(payload: SendMessageRequest, user: dict[str, Any] = Depends(require_user)):
    return send_message(payload, user)


@router.get("/api/messages/{peer_id}")
def read_conversation(
    peer_id: int,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    user: dict[str, Any] = Depends(require_user),
):
    return get_conversation(peer_id, after_id, limit, user)


@router.get("/api/environmental-indicators/{region_id}")
def environmental_indicators(
    region_id: str,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    """Return provider current conditions and rainfall signals, never an official flood classification."""
    if user.get("role") != "user":
        raise HTTPException(403, "Environmental indicators are available on the user dashboard.")
    try:
        region = get_region(region_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        weather = get_weather_data(
            region["latitude"],
            region["longitude"],
            region.get("timezone", "Asia/Kolkata"),
        )
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(502, f"Weather provider unavailable: {type(exc).__name__}") from exc

    current = weather.get("current") or {}
    rainfall = current.get("precipitation_mm")
    if rainfall is None:
        rainfall_signal = "UNAVAILABLE"
        rainfall_description = "The provider did not return current precipitation."
    elif float(rainfall) > 0:
        rainfall_signal = "PRECIPITATION_REPORTED"
        rainfall_description = "The weather provider reports precipitation for its current period."
    else:
        rainfall_signal = "NO_PRECIPITATION_REPORTED"
        rainfall_description = "The weather provider reports no precipitation for its current period."

    return {
        "region": {"id": region["id"], "name": region["name"], "timezone": region.get("timezone", "Asia/Kolkata")},
        "source": weather.get("source", "Open-Meteo"),
        "source_type": "provider_current_conditions_not_local_sensor",
        "source_timestamp": current.get("time"),
        "retrieved_at": _now(),
        "conditions": {
            "temperature_c": current.get("temperature_c"),
            "relative_humidity_pct": current.get("humidity_pct"),
            "precipitation_mm": rainfall,
            "rain_mm": current.get("rain_mm"),
            "wind_speed_kmh": current.get("wind_speed_kmh"),
            "wind_direction_deg": current.get("wind_direction_deg"),
            "surface_pressure_hpa": current.get("surface_pressure_hpa"),
        },
        "rainfall_windows": weather.get("rainfall_windows", {}),
        "rainfall_signal": {
            "status": rainfall_signal,
            "description": rainfall_description,
            "informational_only": True,
        },
        "flood_assessment_status": "NOT_ASSESSED",
        "warning": (
            "Weather-provider current conditions may be model-derived and are not local river-gauge observations. "
            "This environmental signal is not a flood warning or an all-clear."
        ),
    }
