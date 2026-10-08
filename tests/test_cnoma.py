import numpy as np

from cnoma import CNOMASimulator
from ris_agent import QLearningRISAgent
from ris_environment import RISEnvironment


def test_cnoma_power_profiles_and_sic():
    model = CNOMASimulator()
    result = model.evaluate(12.0, 4.0, power_profile=0, critical_user=1)
    assert result.simulation_only is True
    assert result.power_user1 == 0.70
    assert result.power_user2 == 0.30
    assert isinstance(result.sic_success, bool)


def test_ris_cnoma_environment_exposes_combined_actions():
    env = RISEnvironment(seed=7, max_steps=2)
    obs = env.reset(priority="CRITICAL")
    assert obs["cnoma_success_probability"].shape == (3, 8, 3)
    assert env.n_actions == 3 * 8 * 3 + 1
    action = int(np.flatnonzero(env.action_mask(obs))[0])
    _, _, _, info = env.step(action, packet="critical")
    assert "user1_sinr_db" in info
    assert "user2_sinr_db" in info
    assert "sic_success" in info
    assert "power_user1" in info


def test_agent_action_space_matches_cnoma_environment():
    env = RISEnvironment(seed=11, max_steps=1)
    agent = QLearningRISAgent(seed=11)
    obs = env.reset(priority="HIGH")
    assert agent.n_actions == env.n_actions
    action = agent.choose_action(obs, env.action_mask(obs), explore=False)
    assert 0 <= action < env.n_actions
