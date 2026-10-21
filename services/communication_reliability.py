"""Two-user communication reliability demo. All radio/channel results are software simulations."""
from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.auth_service import require_user

router = APIRouter()
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "communication_reliability.sqlite3"
DEFAULT_MESSAGE = "Flood water rising near the bridge. Please move to higher ground."


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS communication_runs (
        message_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, sender TEXT NOT NULL,
        receiver TEXT NOT NULL, message TEXT NOT NULL, scenario TEXT NOT NULL,
        status TEXT NOT NULL, acknowledged INTEGER NOT NULL, attempts INTEGER NOT NULL,
        latency_ms REAL, metrics_json TEXT NOT NULL, events_json TEXT NOT NULL
    )""")
    db.commit()
    return db


class CommunicationTestRequest(BaseModel):
    sender: str = Field(default="User A", min_length=1, max_length=80)
    receiver: str = Field(default="User B", min_length=1, max_length=80)
    message: str = Field(default=DEFAULT_MESSAGE, min_length=1, max_length=1000)
    scenario: str = Field(default="Severe", pattern="^(Mild|Moderate|Severe)$")
    seed: int = Field(default=2026, ge=0, le=2**31 - 1)


def simulate_delivery(request: CommunicationTestRequest) -> dict[str, Any]:
    """Deterministic seeded software model; never represents actual radio measurements."""
    rng = random.Random(request.seed)
    now = datetime.now(timezone.utc).isoformat()
    message_id = str(uuid.uuid4())
    loss_by_scenario = {"Mild": 0.05, "Moderate": 0.18, "Severe": 0.38}
    ack_loss_by_scenario = {"Mild": 0.03, "Moderate": 0.10, "Severe": 0.24}
    base_latency = {"Mild": 45.0, "Moderate": 95.0, "Severe": 180.0}
    packet_loss_probability = loss_by_scenario[request.scenario]
    ack_loss_probability = ack_loss_by_scenario[request.scenario]
    events: list[dict[str, Any]] = []

    def event(event_type: str, detail: str, **extra):
        events.append({
            "sequence": len(events) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "detail": detail,
            **extra,
        })

    event("MESSAGE_CREATED", f"{request.sender} created a message for {request.receiver}.")
    delivered = False
    acknowledged = False
    latency_ms = None
    attempts = 0
    for attempt in range(1, 4):
        attempts = attempt
        event("TRANSMISSION_ATTEMPT", f"Software simulation started attempt {attempt}.", attempt=attempt)
        time.sleep(0.001)
        if rng.random() < packet_loss_probability:
            event("PACKET_LOST", f"Attempt {attempt} was dropped by the simulated channel.", attempt=attempt)
            continue
        delivered = True
        latency_ms = round(base_latency[request.scenario] * rng.uniform(0.75, 1.35) + (attempt - 1) * 35, 2)
        event("MESSAGE_RECEIVED", f"{request.receiver} received the message in the simulation.", attempt=attempt, latency_ms=latency_ms)
        if rng.random() < ack_loss_probability:
            event("ACK_LOST", f"The simulated acknowledgement for attempt {attempt} was lost.", attempt=attempt)
            continue
        acknowledged = True
        event("ACK_RECEIVED", f"{request.sender} received an acknowledgement from {request.receiver}.", attempt=attempt)
        break

    status = "ACKNOWLEDGED" if acknowledged else "DELIVERED_UNACKNOWLEDGED" if delivered else "NOT_DELIVERED"
    attempts_completed = attempts
    metrics = {
        "simulation_only": True,
        "scenario": request.scenario,
        "attempts": attempts_completed,
        "max_attempts": 3,
        "message_delivered": delivered,
        "acknowledged": acknowledged,
        "delivery_rate_percent": round(100.0 if delivered else 0.0, 2),
        "acknowledgement_rate_percent": round(100.0 if acknowledged else 0.0, 2),
        "modeled_latency_ms": latency_ms,
        "modeled_packet_loss_probability_percent": round(packet_loss_probability * 100, 2),
        "modeled_ack_loss_probability_percent": round(ack_loss_probability * 100, 2),
        "scenario_parameters_are_not_measured_radio_data": True,
    }
    event("RUN_COMPLETED", f"Simulation finished with status {status}.", status=status)
    result = {
        "message_id": message_id, "created_at": now, "sender": request.sender,
        "receiver": request.receiver, "message": request.message, "scenario": request.scenario,
        "status": status, "delivered": delivered, "acknowledged": acknowledged,
        "attempts": attempts_completed, "latency_ms": latency_ms, "metrics": metrics,
        "events": events, "simulation_only": True,
        "notice": "SOFTWARE SIMULATION ONLY. These results do not measure or prove real-world radio/link reliability. Flood risk remains NOT_ASSESSED.",
        "flood_assessment_status": "NOT_ASSESSED",
    }
    with _connect() as db:
        db.execute("""INSERT INTO communication_runs
          (message_id,created_at,sender,receiver,message,scenario,status,acknowledged,attempts,latency_ms,metrics_json,events_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
          (message_id, now, request.sender, request.receiver, request.message, request.scenario,
           status, int(acknowledged), attempts_completed, latency_ms,
           json.dumps(metrics), json.dumps(events)))
    return result


@router.post("/api/communication/test")
def run_communication_test(request: CommunicationTestRequest, user: dict = Depends(require_user)):
    return simulate_delivery(request)


@router.get("/api/admin/communication-metrics")
def admin_communication_metrics(user: dict = Depends(require_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    with _connect() as db:
        rows = db.execute("""SELECT * FROM communication_runs ORDER BY created_at DESC LIMIT 100""").fetchall()
        totals = db.execute("""SELECT COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN status IN ('ACKNOWLEDGED','DELIVERED_UNACKNOWLEDGED') THEN 1 ELSE 0 END),0) AS delivered,
            COALESCE(SUM(acknowledged),0) AS acknowledged,
            AVG(latency_ms) AS mean_latency_ms, AVG(attempts) AS mean_attempts
            FROM communication_runs""").fetchone()
    total = int(totals["total"] or 0)
    delivered = int(totals["delivered"] or 0)
    acknowledged = int(totals["acknowledged"] or 0)
    return {
        "simulation_only": True,
        "flood_assessment_status": "NOT_ASSESSED",
        "totals": {
            "runs": total,
            "delivered": delivered,
            "acknowledged": acknowledged,
            "delivery_rate_percent": round(100 * delivered / total, 2) if total else 0.0,
            "acknowledgement_rate_percent": round(100 * acknowledged / total, 2) if total else 0.0,
            "mean_modeled_latency_ms": round(totals["mean_latency_ms"], 2) if totals["mean_latency_ms"] is not None else None,
            "mean_attempts": round(totals["mean_attempts"], 2) if totals["mean_attempts"] is not None else None,
        },
        "runs": [{
            "message_id": row["message_id"], "created_at": row["created_at"],
            "sender": row["sender"], "receiver": row["receiver"], "message": row["message"],
            "scenario": row["scenario"], "status": row["status"], "acknowledged": bool(row["acknowledged"]),
            "attempts": row["attempts"], "latency_ms": row["latency_ms"],
            "metrics": json.loads(row["metrics_json"]), "events": json.loads(row["events_json"]),
        } for row in rows],
        "notice": "All values are software-simulated, not live radio telemetry or field measurements.",
    }
