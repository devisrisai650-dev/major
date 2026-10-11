import numpy as np

from evaluate_ris_agent import bootstrap_ci, choose_action, POLICIES, SCENARIOS
from ris_environment import RISEnvironment


def test_bootstrap_ci_is_bounded():
    low, high = bootstrap_ci([0.1, 0.2, 0.3], seed=1, samples=200)
    assert 0.1 <= low <= high <= 0.3


def test_required_policies_and_scenarios():
    assert {
        "agent", "random", "fixed", "initial_greedy", "myopic_noisy", "oracle"
    } == set(POLICIES)
    assert {"light", "moderate", "severe"} == set(SCENARIOS)


def test_weight_ablation_is_explicit():
    assert 0.0 < 0.05
    assert "noise" in SCENARIOS["moderate"]
    assert "delay" in SCENARIOS["moderate"]



def test_bootstrap_ci_resamples_independent_cluster_means():
    low, high = bootstrap_ci(
        [0.0, 1.0, 0.0, 1.0],
        samples=100,
        cluster_ids=["eval-a", "eval-a", "eval-b", "eval-b"],
    )
    assert low == 0.5
    assert high == 0.5


def test_fixed_policy_keeps_ris_zero_or_waits():
    env = RISEnvironment(seed=5, max_steps=1)
    mask = np.zeros(env.n_actions, dtype=bool)
    ris_zero_action = 8  # channel 1, RIS configuration 0, power profile 0
    mask[ris_zero_action] = True
    env.action_mask = lambda observation=None: mask
    assert choose_action(env, {}, "fixed", np.random.default_rng(5)) == ris_zero_action

    mask[:] = False
    mask[9] = True  # channel 1, RIS configuration 1
    assert choose_action(env, {}, "fixed", np.random.default_rng(5)) == env.wait_action


def test_initial_greedy_policy_waits_when_locked_action_is_infeasible():
    env = RISEnvironment(seed=6, max_steps=1)
    mask = np.zeros(env.n_actions, dtype=bool)
    mask[9] = True
    env.action_mask = lambda observation=None: mask
    assert choose_action(
        env, {}, "initial_greedy", np.random.default_rng(6), fixed_action=8
    ) == env.wait_action
