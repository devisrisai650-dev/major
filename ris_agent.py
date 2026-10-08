"""Tabular Q-learning agent for the software-only RIS environment."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path

import numpy as np

from ris_environment import PRIORITY_WEIGHT, POWER_SWITCH_PENALTY, RIS_SWITCH_PENALTY


@contextmanager
def _file_lock(lock_path: Path):
    """Cross-platform advisory lock used for Windows-safe policy writes."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class QLearningRISAgent:
    def __init__(self, n_channels=3, n_ris_configs=8, n_power_profiles=3, learning_rate=0.12,
                 discount=0.92, epsilon=1.0, epsilon_min=0.04,
                 epsilon_decay=0.996, learned_value_weight=0.05, seed=None):
        if learned_value_weight < 0:
            raise ValueError("learned_value_weight must be non-negative")
        self.n_channels = n_channels
        self.n_ris_configs = n_ris_configs
        self.n_power_profiles = n_power_profiles
        self.wait_action = n_channels * n_ris_configs * n_power_profiles
        self.n_actions = self.wait_action + 1
        self.learning_rate = learning_rate
        self.discount = discount
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.learned_value_weight = learned_value_weight
        self.rng = np.random.default_rng(seed)
        self.priority_index = {name: i for i, name in enumerate(PRIORITY_WEIGHT)}
        self.n_states = (4 ** n_channels) * n_ris_configs * n_power_profiles * len(PRIORITY_WEIGHT)
        self.q = np.zeros((self.n_states, self.n_actions), dtype=np.float32)

    def encode_state(self, observation):
        current_ris = int(observation["current_ris_config"])
        current_power = int(observation["current_power_profile"])
        priority = self.priority_index[observation["priority"]]
        snr = observation["snr_db"][:, current_ris]
        bins = np.digitize(snr, [-1.0, 5.0, 10.0]).astype(int)
        channel_code = 0
        multiplier = 1
        for bucket in bins:
            channel_code += int(bucket) * multiplier
            multiplier *= 4
        return (((priority * self.n_ris_configs + current_ris) * self.n_power_profiles
                 + current_power) * (4 ** self.n_channels) + channel_code)

    def choose_action(self, observation, action_mask, explore=False):
        valid = np.flatnonzero(action_mask)
        if valid.size == 0:
            return self.wait_action
        state = self.encode_state(observation)
        if explore and self.rng.random() < self.epsilon:
            return int(self.rng.choice(valid))
        weight = PRIORITY_WEIGHT[observation["priority"]]
        expected_reward = np.full(valid.size, -0.30 * weight)
        for i, action in enumerate(valid):
            if action == self.wait_action:
                continue
            block, power = divmod(int(action), self.n_power_profiles)
            channel, ris_config = divmod(block, self.n_ris_configs)
            probability = float(observation["cnoma_success_probability"][channel, ris_config, power])
            latency = float(observation["latency_ms"][channel, ris_config])
            throughput = float(observation["throughput_mbps"][channel, ris_config])
            switch_cost = (
                RIS_SWITCH_PENALTY if ris_config != int(observation["current_ris_config"]) else 0.0
            )
            switch_cost += (
                POWER_SWITCH_PENALTY if power != int(observation["current_power_profile"]) else 0.0
            )
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

    def learn(self, state, action, reward, next_state, next_mask, done):
        future = 0.0
        valid_next = np.flatnonzero(next_mask)
        if not done and valid_next.size:
            future = float(np.max(self.q[next_state, valid_next]))
        target = reward + self.discount * future
        self.q[state, action] += self.learning_rate * (target - self.q[state, action])

    def decay_exploration(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.tmp.npz")
        lock_path = path.with_name(f".{path.name}.lock")
        with _file_lock(lock_path):
            try:
                np.savez_compressed(
                    temp, q=self.q, n_channels=self.n_channels,
                    n_ris_configs=self.n_ris_configs,
                    learned_value_weight=self.learned_value_weight,
                )
                os.replace(temp, path)
            finally:
                if temp.exists():
                    temp.unlink()

    def load(self, path):
        path = Path(path)
        lock_path = path.with_name(f".{path.name}.lock")
        with _file_lock(lock_path):
            with np.load(path) as saved:
                if (int(saved["n_channels"]) != self.n_channels
                        or int(saved["n_ris_configs"]) != self.n_ris_configs
                        or int(saved.get("n_power_profiles", np.array(self.n_power_profiles))) != self.n_power_profiles):
                    raise ValueError("Saved Q-table dimensions do not match this environment")
                table = saved["q"]
                if table.shape != self.q.shape:
                    raise ValueError("Saved Q-table has an unexpected shape")
                self.q[:] = table
                if "learned_value_weight" in saved:
                    self.learned_value_weight = float(saved["learned_value_weight"])


def train_agent(agent, env, episodes=1200, max_steps=None):
    episode_rewards = []
    priorities = list(PRIORITY_WEIGHT)
    horizon = max_steps or env.max_steps
    for episode in range(episodes):
        observation = env.reset(priority=priorities[episode % len(priorities)])
        total_reward = 0.0
        for _ in range(horizon):
            state = agent.encode_state(observation)
            action = agent.choose_action(observation, env.action_mask(observation), explore=True)
            next_observation, reward, done, _ = env.step(action)
            next_state = agent.encode_state(next_observation)
            agent.learn(state, action, reward, next_state, env.action_mask(next_observation), done)
            total_reward += reward
            observation = next_observation
            if done:
                break
        agent.decay_exploration()
        episode_rewards.append(total_reward)
    return episode_rewards
