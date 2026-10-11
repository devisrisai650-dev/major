import numpy as np

from cnoma import CNOMASimulator
from ris_agent import QLearningRISAgent, train_agent
from ris_environment import RISEnvironment
from semantic_transmission import transmit_semantic_message


def test_cnoma_power_profiles_and_sic():
    model = CNOMASimulator()
    result = model.evaluate(12.0, 4.0, power_profile=0, critical_user=1)
    assert result.simulation_only is True
    # User 1 has the stronger SNR here and therefore receives the smaller share.
    assert result.weak_user == 2
    assert result.strong_user == 1
    assert result.power_user1 == 0.30
    assert result.power_user2 == 0.70
    assert isinstance(result.sic_success, bool)



def test_cnoma_power_assignment_follows_channel_order_not_user_index():
    model = CNOMASimulator()
    user1_weak = model.evaluate(2.0, 15.0, power_profile=0)
    user2_weak = model.evaluate(15.0, 2.0, power_profile=0)
    assert user1_weak.weak_user == 1
    assert user1_weak.power_user1 == 0.70
    assert user1_weak.power_user2 == 0.30
    assert user2_weak.weak_user == 2
    assert user2_weak.power_user1 == 0.30
    assert user2_weak.power_user2 == 0.70


def test_training_epsilon_reaches_floor_and_records_curves():
    env = RISEnvironment(seed=19, max_steps=1)
    agent = QLearningRISAgent(seed=19)
    rewards = train_agent(agent, env, episodes=5, max_steps=1)
    assert len(rewards) == 5
    assert len(agent.training_epsilon_history) == 5
    assert len(agent.training_episode_rewards) == 5
    assert agent.training_epsilon_history[-1] == agent.epsilon_min
    assert agent.training_epsilon_history[3] == agent.epsilon_min


def test_ris_cnoma_environment_exposes_combined_actions():
    env = RISEnvironment(seed=7, max_steps=2)
    obs = env.reset(priority="CRITICAL")
    assert obs["cnoma_delivery_feasibility"].shape == (3, 8, 3)
    assert env.n_actions == 3 * 8 * 3 + 1
    action = int(np.flatnonzero(env.action_mask(obs))[0])
    _, _, _, info = env.step(action, packet="critical")
    assert "user1_sinr_db" in info
    assert "user2_sinr_db" in info
    assert "sic_success" in info
    assert "power_user1" in info
    assert info["delivery_model"] == "threshold_outage"
    critical_decoded = info["cnoma_user1_decoded"]
    assert info["delivered"] == critical_decoded


def test_agent_action_space_matches_cnoma_environment():
    env = RISEnvironment(seed=11, max_steps=1)
    agent = QLearningRISAgent(seed=11)
    obs = env.reset(priority="HIGH")
    assert agent.n_actions == env.n_actions
    action = agent.choose_action(obs, env.action_mask(obs), explore=False)
    assert 0 <= action < env.n_actions


def test_node_outage_can_remove_channel():
    env = RISEnvironment(seed=12, max_steps=2, node_loss_probability=1.0)
    obs = env.reset(priority="CRITICAL")
    assert obs["node_available"].all()
    env.step(env.wait_action)
    assert not env.measurements["node_available"].any()


def test_transmission_records_throughput_for_summary(tmp_path):
    policy_path = tmp_path / "policy.npz"
    QLearningRISAgent(seed=13).save(policy_path)

    result = transmit_semantic_message(
        "test packet",
        {"rainfall_current": {"available": True, "priority": "MEDIUM"}},
        policy_path,
        max_attempts=2,
        seed=13,
    )

    assert result["attempts"]
    assert all("throughput_mbps" in attempt for attempt in result["attempts"])
    assert result["mean_throughput_mbps"] >= 0
