from services import communication_reliability as comm


def test_simulation_records_message_delivery_and_ack_events(tmp_path, monkeypatch):
    monkeypatch.setattr(comm, "DB_PATH", tmp_path / "communication.sqlite3")
    request = comm.CommunicationTestRequest(
        sender="User A",
        receiver="User B",
        message="Flood water rising near the bridge. Please move to higher ground.",
        scenario="Severe",
        seed=2026,
    )
    result = comm.simulate_delivery(request)

    assert result["simulation_only"] is True
    assert result["flood_assessment_status"] == "NOT_ASSESSED"
    assert result["sender"] == "User A"
    assert result["receiver"] == "User B"
    assert result["message"] == request.message
    assert result["status"] in {"ACKNOWLEDGED", "DELIVERED_UNACKNOWLEDGED", "NOT_DELIVERED"}
    assert result["metrics"]["scenario_parameters_are_not_measured_radio_data"] is True
    assert result["events"][0]["event"] == "MESSAGE_CREATED"
    assert result["events"][-1]["event"] == "RUN_COMPLETED"
    if result["acknowledged"]:
        assert any(e["event"] == "ACK_RECEIVED" for e in result["events"])
        assert result["delivered"] is True


def test_admin_metrics_aggregate_saved_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(comm, "DB_PATH", tmp_path / "communication.sqlite3")
    comm.simulate_delivery(comm.CommunicationTestRequest(seed=2026))
    data = comm.admin_communication_metrics({"role": "admin"})

    assert data["simulation_only"] is True
    assert data["flood_assessment_status"] == "NOT_ASSESSED"
    assert data["totals"]["runs"] == 1
    assert 0 <= data["totals"]["delivery_rate_percent"] <= 100
    assert 0 <= data["totals"]["acknowledgement_rate_percent"] <= 100
    assert len(data["runs"]) == 1
    assert data["runs"][0]["events"]


def test_non_admin_cannot_read_backend_metrics(tmp_path, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(comm, "DB_PATH", tmp_path / "communication.sqlite3")
    try:
        comm.admin_communication_metrics({"role": "user"})
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Non-admin user should not access admin metrics")
