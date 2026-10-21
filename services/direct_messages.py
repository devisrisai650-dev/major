"""Authenticated near-real-time direct messages between registered FloodAI users."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.auth_service import _connect as auth_connect, audit, require_user, validate_email

router = APIRouter()
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "direct_messages.sqlite3"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS direct_messages (
        id TEXT PRIMARY KEY, sender_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL,
        sender_email TEXT NOT NULL, receiver_email TEXT NOT NULL, body TEXT NOT NULL,
        created_at TEXT NOT NULL, read_at TEXT
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_dm_receiver ON direct_messages(receiver_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_dm_sender ON direct_messages(sender_id, created_at)")
    return db


class SendMessageRequest(BaseModel):
    recipient_email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=1, max_length=2000)


def _active_registered_user(email: str):
    with auth_connect() as db:
        return db.execute(
            """SELECT id,email FROM users WHERE email=? AND role='user'
               AND is_active=1 AND is_verified=1""",
            (email,),
        ).fetchone()


@router.post("/api/messages", status_code=201)
def send_message(payload: SendMessageRequest, user: dict[str, Any] = Depends(require_user)):
    if user.get("role") != "user":
        raise HTTPException(403, "Direct messaging is available to registered user accounts.")
    recipient_email = validate_email(payload.recipient_email)
    recipient = _active_registered_user(recipient_email)
    if recipient is None:
        raise HTTPException(404, "No active, verified registered user was found for that email.")
    if int(recipient["id"]) == int(user["id"]):
        raise HTTPException(422, "Choose another registered user as the recipient.")
    body = payload.message.strip()
    if not body:
        raise HTTPException(422, "Message cannot be blank.")
    message_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        db.execute(
            """INSERT INTO direct_messages
               (id,sender_id,receiver_id,sender_email,receiver_email,body,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (message_id, int(user["id"]), int(recipient["id"]), user["email"],
             recipient["email"], body, created_at),
        )
    audit("direct_message_sent", actor=user, target=str(recipient["id"]),
          details=f"message_id={message_id}")
    return {"id": message_id, "created_at": created_at, "sender_email": user["email"],
            "recipient_email": recipient["email"], "message": body, "delivery": "STORED",
            "notice": "Stored on this FloodAI server. This is not an emergency-service dispatch."}


@router.get("/api/messages")
def list_messages(
    after: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    user: dict[str, Any] = Depends(require_user),
):
    """Return only messages involving the signed-in account; poll for near-real-time updates."""
    uid = int(user["id"])
    with _connect() as db:
        if after:
            rows = db.execute(
                """SELECT * FROM direct_messages
                   WHERE (sender_id=? OR receiver_id=?) AND created_at>?
                   ORDER BY created_at ASC LIMIT ?""",
                (uid, uid, after, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT * FROM (SELECT * FROM direct_messages
                   WHERE sender_id=? OR receiver_id=? ORDER BY created_at DESC LIMIT ?)
                   ORDER BY created_at ASC""",
                (uid, uid, limit),
            ).fetchall()
        # Mark only this user's returned inbound messages as read.
        inbound_ids = [row["id"] for row in rows
                       if int(row["receiver_id"]) == uid and row["read_at"] is None]
        if inbound_ids:
            now = datetime.now(timezone.utc).isoformat()
            db.executemany("UPDATE direct_messages SET read_at=? WHERE id=? AND receiver_id=?",
                           [(now, mid, uid) for mid in inbound_ids])
    return {"messages": [{
        "id": row["id"], "sender_email": row["sender_email"],
        "recipient_email": row["receiver_email"], "message": row["body"],
        "created_at": row["created_at"], "read": bool(row["read_at"]) or
            (int(row["receiver_id"]) == uid and row["id"] in inbound_ids),
        "direction": "sent" if int(row["sender_id"]) == uid else "received",
    } for row in rows], "poll_after_seconds": 3,
        "notice": "Messages are server-stored and access-controlled, not end-to-end encrypted. Do not use as the sole emergency channel."}
