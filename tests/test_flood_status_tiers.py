from api import _flood_dashboard

def test_flood_dashboard_exposes_tiered_environmental_signal_without_claiming_no_flood():
    analysis = {
        "flood_assessment": {
            "status": "NOT_ASSESSED",
            "state": "NOT_ASSESSED",
            "complete": False,
            "missing_or_unconfigured": ["verified official station-specific warning thresholds"],
            "reason": "Evidence incomplete.",
        },
        "rainfall": {"classification": "HIGH"},
        "river": {"classification": "MODERATE"},
        "water_level": {"classification": "UNKNOWN", "available": False, "is_recent": False},
    }
    result = _flood_dashboard(analysis, {}, {}, {})
    assert result["environmental_level"] == "HIGH"
    assert result["assessment_status"] == "NOT_ASSESSED"
    assert "not official flood-risk" in result["status_disclaimer"]


def test_flood_dashboard_low_indicator_does_not_mean_no_flood():
    analysis = {
        "flood_assessment": {
            "status": "NOT_ASSESSED",
            "state": "NOT_ASSESSED",
            "complete": False,
            "missing_or_unconfigured": ["verified official station-specific warning thresholds"],
            "reason": "Evidence incomplete.",
        },
        "rainfall": {"classification": "LOW"},
        "river": {"classification": "LOW"},
        "water_level": {"classification": "STABLE", "available": False, "is_recent": False},
    }
    result = _flood_dashboard(analysis, {}, {}, {})
    assert result["environmental_level"] == "LOW"
    assert result["assessment_status"] == "NOT_ASSESSED"
    assert "all-clear" in result["status_disclaimer"]
