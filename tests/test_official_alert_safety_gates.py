"""Safety-gate regression tests: incomplete or simulated evidence cannot send official alerts."""
from services import alert_service


def test_simulation_only_assessment_never_sends_official_alert(monkeypatch):
    calls = {"reserve": 0, "recipients": 0, "send": 0}

    monkeypatch.setattr(
        alert_service, "reserve_alert_dispatch",
        lambda *args: calls.__setitem__("reserve", calls["reserve"] + 1) or True,
    )
    monkeypatch.setattr(
        alert_service, "get_verified_alert_recipients",
        lambda: calls.__setitem__("recipients", calls["recipients"] + 1) or ["test@example.invalid"],
    )
    monkeypatch.setattr(
        alert_service, "send_flood_alert",
        lambda *args, **kwargs: calls.__setitem__("send", calls["send"] + 1),
    )

    result = alert_service.dispatch_verified_flood_alert(
        region_id="test-region",
        region_name="Test Region",
        assessment={
            "status": "WARNING",
            "complete": True,
            "event_id": "simulated-event-1",
        },
        evidence={
            "official_thresholds_verified": True,
            "fresh_qc_gauge": True,
            "source_is_authoritative": True,
            "simulation_only": True,
        },
    )

    assert result["eligible"] is False
    assert result["sent"] == 0
    assert calls == {"reserve": 0, "recipients": 0, "send": 0}


def test_missing_verified_evidence_never_sends_official_alert(monkeypatch):
    calls = {"reserve": 0, "send": 0}
    monkeypatch.setattr(
        alert_service, "reserve_alert_dispatch",
        lambda *args: calls.__setitem__("reserve", calls["reserve"] + 1) or True,
    )
    monkeypatch.setattr(
        alert_service, "send_flood_alert",
        lambda *args, **kwargs: calls.__setitem__("send", calls["send"] + 1),
    )

    result = alert_service.dispatch_verified_flood_alert(
        region_id="test-region",
        region_name="Test Region",
        assessment={
            "status": "WARNING",
            "complete": True,
            "event_id": "unverified-event-1",
        },
        evidence={
            "official_thresholds_verified": False,
            "fresh_qc_gauge": False,
            "source_is_authoritative": False,
            "simulation_only": False,
        },
    )

    assert result["eligible"] is False
    assert result["sent"] == 0
    assert calls == {"reserve": 0, "send": 0}


def test_not_assessed_state_never_sends_official_alert(monkeypatch):
    monkeypatch.setattr(
        alert_service, "reserve_alert_dispatch",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not reserve")),
    )
    monkeypatch.setattr(
        alert_service, "send_flood_alert",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not send")),
    )

    result = alert_service.dispatch_verified_flood_alert(
        region_id="test-region",
        region_name="Test Region",
        assessment={
            "status": "NOT_ASSESSED",
            "complete": False,
            "event_id": "",
        },
        evidence={},
    )

    assert result["eligible"] is False
    assert result["sent"] == 0
