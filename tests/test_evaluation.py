from evaluate_ris_agent import bootstrap_ci, POLICIES, SCENARIOS

def test_bootstrap_ci_is_bounded():
    low, high = bootstrap_ci([0.1, 0.2, 0.3], seed=1, samples=200)
    assert 0.1 <= low <= high <= 0.3

def test_required_policies_and_scenarios():
    assert {"agent", "random", "fixed", "best_fixed", "myopic_noisy", "oracle"} == set(POLICIES)
    assert {"light", "moderate", "severe"} == set(SCENARIOS)
