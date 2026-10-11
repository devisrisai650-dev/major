from semantic_transmission import priority_for_message


def test_semantic_priority_uses_highest_available_priority():
    priorities = {
        "rainfall": {"available": True, "priority": "MEDIUM"},
        "gauge": {"available": True, "priority": "CRITICAL"},
        "discharge": {"available": True, "priority": "HIGH"},
    }
    assert priority_for_message(priorities) == "CRITICAL"


def test_unavailable_critical_field_does_not_escalate_packet_priority():
    priorities = {
        "gauge": {"available": False, "priority": "CRITICAL"},
        "rainfall": {"available": True, "priority": "MEDIUM"},
    }
    assert priority_for_message(priorities) == "MEDIUM"


def test_empty_or_unavailable_semantics_default_to_low_priority():
    assert priority_for_message({}) == "LOW"
    assert priority_for_message({
        "gauge": {"available": False, "priority": "CRITICAL"}
    }) == "LOW"

def test_aoi_accumulates_failed_attempt_age_until_successful_delivery():
    from semantic_transmission import summarize_aoi

    result = summarize_aoi([
        {"latency_ms": 20.0, "delivered": False},
        {"latency_ms": 30.0, "delivered": True},
        {"latency_ms": 40.0, "delivered": False},
    ])

    assert result["delivery_aoi_ms"] == 50.0
    assert result["final_aoi_ms"] == 90.0
    assert result["mean_aoi_ms"] == (20.0 + 50.0 + 90.0) / 3


def test_aoi_is_unavailable_when_there_are_no_attempts():
    from semantic_transmission import summarize_aoi

    assert summarize_aoi([]) == {
        "mean_aoi_ms": None,
        "delivery_aoi_ms": None,
        "final_aoi_ms": None,
    }

def test_aoi_accumulates_failed_attempt_age_until_successful_delivery():
    from semantic_transmission import summarize_aoi

    result = summarize_aoi([
        {"latency_ms": 20.0, "delivered": False},
        {"latency_ms": 30.0, "delivered": True},
        {"latency_ms": 40.0, "delivered": False},
    ])

    assert result["delivery_aoi_ms"] == 50.0
    assert result["final_aoi_ms"] == 90.0
    assert result["mean_aoi_ms"] == (20.0 + 50.0 + 90.0) / 3


def test_aoi_is_unavailable_when_there_are_no_attempts():
    from semantic_transmission import summarize_aoi

    assert summarize_aoi([]) == {
        "mean_aoi_ms": None,
        "delivery_aoi_ms": None,
        "final_aoi_ms": None,
    }
