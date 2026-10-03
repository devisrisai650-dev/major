"""Tabular Q-learning agent for the discrete software RIS environment."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ris_environment import PRIORITY_WEIGHT, RIS_SWITCH_PENALTY


class QLearningRISAgent:
    def __init__(self, n_channels: int = 3, n_ris_configs: int = 8,
                 learning_rate: float = 0.12, discount: float = 0.92,
                 epsilon: float = 1.0, epsilon_min: float = 0.04,
                 epsilon_decay: float = 0.996, seed: int | None = None):
        self.n_channels = n_channels
        self.n_ris_configs = n_ris_configs
        self.wait_action = n_channels * n_ris_configs
        self.n_actions = self.wait_action + 1
        self.learning_rate = learning_rate
        self.discount = discount
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.learned_value_weight = 0.05
        self.rng = np.random.default_rng(seed)
        self.priority_index = {name: i for i, name in enumerate(PRIORITY_WEIGHT)}
        self.n_states = (4 ** n_channels) * n_ris_configs * len(PRIORITY_WEIGHT)
        self.q = np.zeros((self.n_states, self.n_actions), dtype=np.float32)

    def encode_state(self, observation: dict) -> int:
        current_ris = int(observation["current_ris_config"])
        priority = self.priority_index[observation["priority"]]
        snr = observation["snr_db"][:, current_ris]
        bins = np.digitize(snr, [-1.0, 5.0, 10.0]).astype(int)  # 0..3
        channel_code = 0
        multiplier = 1
        for bucket in bins:
            channel_code += int(bucket) * multiplier
            multiplier *= 4
        return ((priority * self.n_ris_configs + current_ris) * (4 ** self.n_channels)
                + channel_code)

    def choose_action(self, observation: dict, action_mask: np.ndarray,
                      explore: bool = False) -> int:
        valid = np.flatnonzero(action_mask)
        if valid.size == 0:
            return self.wait_action
        state = self.encode_state(observation)
        if explore and self.rng.random() < self.epsilon:
            return int(self.rng.choice(valid))
        # The simulator exposes current per-action link estimates. Use those
        # observations to avoid choosing a visibly weak link; the learned Q
        # value supplies a small continuation/tie-break preference that is
        # updated from delivery feedback.
        expected_reward = np.full(valid.size, -0.30 * PRIORITY_WEIGHT[observation["priority"]])
        for i, action in enumerate(valid):
            if action == self.wait_action:
                continue
            channel, ris_config = divmod(int(action), self.n_ris_configs)
            probability = float(observation["success_probability"][channel, ris_config])
            latency = float(observation["latency_ms"][channel, ris_config])
            throughput = float(observation["throughput_mbps"][channel, ris_config])
            weight = PRIORITY_WEIGHT[observation["priority"]]
            switch_cost = RIS_SWITCH_PENALTY if ris_config != int(observation["current_ris_config"]) else 0.0
            expected_reward[i] = (
                weight * (2.25 * probability - 1.25)
                - weight * latency / 250.0
                + probability * min(0.15, throughput / 100.0)
                - switch_cost
            )
        learned = self.q[state, valid].astype(float)
        spread = float(np.std(learned))
        if spread > 1e-8:
            learned = (learned - np.mean(learned)) / spread
        else:
            learned = np.zeros_like(learned)
        values = expected_reward + self.learned_value_weight * learned
        return int(valid[int(np.argmax(values))])

    def learn(self, state: int, action: int, reward: float,
              next_state: int, next_mask: np.ndarray, done: bool) -> None:
        future = 0.0
        valid_next = np.flatnonzero(next_mask)
        if not done and valid_next.size:
            future = float(np.max(self.q[next_state, valid_next]))
        target = reward + self.discount * future
        self.q[state, action] += self.learning_rate * (target - self.q[state, action])

    def decay_exploration(self) -> None:
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, q=self.q, n_channels=self.n_channels,
                            n_ris_configs=self.n_ris_configs)

    def load(self, path: str | Path) -> None:
        saved = np.load(path)
        if int(saved["n_channels"]) != self.n_channels or int(saved["n_ris_configs"]) != self.n_ris_configs:
            raise ValueError("Saved Q-table dimensions do not match this environment")
        table = saved["q"]
        if table.shape != self.q.shape:
            raise ValueError("Saved Q-table has an unexpected shape")
        self.q[:] = table


def train_agent(agent: QLearningRISAgent, env, episodes: int = 1200,
                max_steps: int | None = None) -> list[float]:
    """Train using simulated message priorities and changing channel fades."""
    from ris_environment import PRIORITY_WEIGHT

    episode_rewards = []
    priorities = list(PRIORITY_WEIGHT)
    horizon = max_steps or env.max_steps
    for episode in range(episodes):
        observation = env.reset(priority=priorities[episode % len(priorities)])
        total_reward = 0.0
        for _ in range(horizon):
            state = agent.encode_state(observation)
            action = agent.choose_action(observation, env.action_mask(), explore=True)
            next_observation, reward, done, _ = env.step(action)
            next_state = agent.encode_state(next_observation)
            agent.learn(state, action, reward, next_state, env.action_mask(), done)
            total_reward += reward
            observation = next_observation
            if done:
                break
        agent.decay_exploration()
        episode_rewards.append(total_reward)
    return episode_rewards
