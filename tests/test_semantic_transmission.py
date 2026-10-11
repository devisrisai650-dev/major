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
