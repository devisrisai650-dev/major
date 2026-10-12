import numpy as np

from orchestrator_agent import (
    choose_fixed_ris_action,
    select_policy,
    summarize_decisions,
)


def observation(snr_db, available, node_available=None):
    snr = np.asarray(snr_db, dtype=float)
    avail = np.asarray(available, dtype=bool)
    return {
        "snr_db": snr,
        "available": avail,
        "node_available": np.asarray(
            node_available if node_available is not None else [True] * len(avail),
            dtype=bool,
        ),
        "cnoma_delivery_feasibility": np.ones((len(avail), len(avail[0]), 3)),
    }


def test_orchestrator_uses_drl_for_feasible_non_degraded_link():
    obs = observation([[8.0, 9.0], [6.0, 7.0]], [[True, True], [True, True]])
    mask = [True] * 12 + [False]
    result = select_policy(obs, mask, "MEDIUM")
    assert result["policy"] == "drl_ris_cnoma"
    assert result["simulation_only"] is True


def test_orchestrator_selects_fixed_ris_fallback_for_degraded_link():
    obs = observation([[-2.0, 1.0], [0.0, 2.0]], [[True, True], [True, True]])
    mask = [True] * 12 + [False]
    result = select_policy(obs, mask, "CRITICAL")
    assert result["policy"] == "fixed_ris_cnoma_fallback"
    assert "degraded-link threshold" in result["reason"]


def test_orchestrator_uses_safe_wait_when_no_transmission_is_feasible():
    obs = observation([[-20.0, -20.0]], [[False, False]], [False])
    mask = [False] * 6 + [True]
    result = select_policy(obs, mask, "HIGH")
    assert result["policy"] == "safe_wait"
    assert result["wait_action"] == 6


def test_fixed_ris_fallback_only_selects_feasible_zero_ris_actions():
    obs = observation([[8.0, 12.0], [6.0, 10.0]], [[True, True], [True, True]])
    mask = [True] * 12 + [False]
    action = choose_fixed_ris_action(obs, mask)
    assert action in {0, 2, 4, 6, 8, 10}
    assert mask[action]


def test_orchestrator_summary_reports_policy_counts():
    result = summarize_decisions([
        {"policy": "drl_ris_cnoma"},
        {"policy": "fixed_ris_cnoma_fallback"},
        {"policy": "drl_ris_cnoma"},
    ])
    assert result["policy_counts"] == {
        "drl_ris_cnoma": 2,
        "fixed_ris_cnoma_fallback": 1,
    }
    assert result["decision_count"] == 3


def test_degraded_link_does_not_choose_infeasible_fixed_ris_fallback():
    obs = observation([[1.0, 2.0], [0.0, 1.0]], [[False, True], [False, True]])
    mask = [False, True, False, True, False, True, False, True, False, True, False, True, False]
    result = select_policy(obs, mask, "HIGH")
    assert result["policy"] == "drl_ris_cnoma"
    assert "no fixed-RIS action is feasible" in result["reason"]
