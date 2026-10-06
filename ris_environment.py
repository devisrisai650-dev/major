"""Software-only partially observable channel/RIS simulation environment."""
from __future__ import annotations
from collections import deque
import numpy as np
from channel_simulator import ChannelSimulator

PRIORITY_WEIGHT = {"LOW": 1.0, "MEDIUM": 1.5, "HIGH": 2.5, "CRITICAL": 4.0}
RIS_SWITCH_PENALTY = 0.20

class RISEnvironment:
    """Virtual channel/RIS environment; every radio value is simulated."""

    def __init__(self, n_channels=3, n_ris_configs=8, n_ris_elements=8,
                 seed=None, max_steps=80, observation_mode="partial",
                 snr_noise_std_db=1.5, observation_delay=1):
        if observation_mode not in {"partial", "oracle"}:
            raise ValueError("observation_mode must be 'partial' or 'oracle'")
        if snr_noise_std_db < 0 or observation_delay < 0:
            raise ValueError("observation noise and delay must be non-negative")
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.n_channels = n_channels
        self.n_ris_configs = n_ris_configs
        self.max_steps = max_steps
        self.wait_action = n_channels * n_ris_configs
        self.n_actions = self.wait_action + 1
        self.observation_mode = observation_mode
        self.snr_noise_std_db = snr_noise_std_db
        self.observation_delay = observation_delay
        self.simulator = ChannelSimulator(n_channels, n_ris_configs, n_ris_elements, seed)
        self.current_ris = 0
        self.priority = "LOW"
        self.step_count = 0
        self.measurements = None
        self._history = deque(maxlen=max(2, observation_delay + 1))
        self._last_observation = None

    def reseed(self, seed):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.simulator = ChannelSimulator(
            self.n_channels, self.n_ris_configs, self.simulator.n_ris_elements, seed
        )
        self._history.clear()

    def reset(self, priority=None):
        if priority is None:
            priority = str(self.rng.choice(list(PRIORITY_WEIGHT)))
        if priority not in PRIORITY_WEIGHT:
            raise ValueError(f"Unknown message priority {priority!r}")
        self.priority = priority
        self.current_ris = 0
        self.step_count = 0
        self.measurements = self.simulator.reset()
        self._history.clear()
        self._history.append(self.measurements)
        return self.observe()

    def _observed_measurements(self):
        if self.observation_mode == "oracle":
            source = self.measurements
        elif len(self._history) <= self.observation_delay:
            source = self._history[0]
        else:
            source = list(self._history)[-(self.observation_delay + 1)]
        result = {key: value.copy() if hasattr(value, "copy") else value for key, value in source.items()}
        if self.observation_mode == "partial":
            result["snr_db"] += self.rng.normal(
                0.0, self.snr_noise_std_db, result["snr_db"].shape
            )
            result["success_probability"] = np.clip(
                1.0 / (1.0 + np.exp(-((result["snr_db"] - 2.0) / 2.5))), 0.0, 1.0
            )
            result["available"] = result["snr_db"] >= -3.0
        return result

    def observe(self):
        observed = self._observed_measurements()
        return {
            "snr_db": observed["snr_db"].copy(),
            "success_probability": observed["success_probability"].copy(),
            "latency_ms": observed["latency_ms"].copy(),
            "throughput_mbps": observed["throughput_mbps"].copy(),
            "available": observed["available"].copy(),
            "current_ris_config": self.current_ris,
            "priority": self.priority,
            "step": self.step_count,
            "observation_mode": self.observation_mode,
            "observation_noise_std_db": self.snr_noise_std_db,
            "observation_delay_steps": self.observation_delay,
            "simulation_only": True,
        }

    def action_mask(self):
        mask = np.zeros(self.n_actions, dtype=bool)
        observation = self._last_observation if self._last_observation is not None else self.observe()
        mask[:self.wait_action] = observation["available"].reshape(-1)
        if not mask.any():
            mask[self.wait_action] = True
        return mask

    def step(self, action, packet=None):
        if not 0 <= int(action) < self.n_actions:
            raise ValueError(f"Action must be in [0, {self.n_actions - 1}]")
        action = int(action)
        mask = self.action_mask()
        weight = PRIORITY_WEIGHT[self.priority]
        changed_ris = False
        delivered = False
        selected_channel = None
        selected_ris = self.current_ris
        snr_db = latency_ms = None
        throughput_mbps = 0.0
        receiver_packet = None
        channel_condition = None

        if action == self.wait_action:
            reward = -0.30 * weight
        else:
            selected_channel, selected_ris = divmod(action, self.n_ris_configs)
            snr_db = float(self.measurements["snr_db"][selected_channel, selected_ris])
            p_success = float(
                self.measurements["success_probability"][selected_channel, selected_ris]
            )
            latency_ms = float(self.measurements["latency_ms"][selected_channel, selected_ris])
            throughput_mbps = float(
                self.measurements["throughput_mbps"][selected_channel, selected_ris]
            )
            delivered = bool(self.rng.random() < p_success)
            channel_condition = (
                "GOOD" if snr_db >= 10 else
                "MODERATE" if snr_db >= 5 else
                "POOR" if snr_db >= 0 else "SEVERE"
            )
            if delivered:
                receiver_packet = packet
            changed_ris = selected_ris != self.current_ris
            reward = weight * (1.0 if delivered else -1.25)
            reward -= weight * latency_ms / 250.0
            reward -= RIS_SWITCH_PENALTY if changed_ris else 0.0
            if delivered:
                reward += min(0.15, throughput_mbps / 100.0)
            self.current_ris = selected_ris

        self.step_count += 1
        self.simulator.advance()
        self.measurements = self.simulator.measure()
        self._history.append(self.measurements)
        done = self.step_count >= self.max_steps
        info = {
            "delivered": delivered,
            "selected_channel": selected_channel,
            "channel_candidate": (
                f"sim_candidate_{selected_channel + 1}" if selected_channel is not None else None
            ),
            "selected_ris_config": selected_ris,
            "channel_condition": channel_condition,
            "snr_db": snr_db,
            "latency_ms": latency_ms,
            "throughput_mbps": throughput_mbps,
            "changed_ris": changed_ris,
            "waited": action == self.wait_action,
            "sender_packet": packet,
            "receiver_packet": receiver_packet,
            "priority": self.priority,
            "simulation_only": True,
            "observation_mode": self.observation_mode,
        }
        return self.observe(), float(reward), done, info

    def greedy_baseline_action(self, observation=None):
        observation = observation or self.observe()
        available = observation["available"].reshape(-1)
        p = observation["success_probability"].reshape(-1)
        latency = observation["latency_ms"].reshape(-1)
        throughput = observation["throughput_mbps"].reshape(-1)
        weight = PRIORITY_WEIGHT[self.priority]
        actions = np.arange(self.wait_action)
        change_cost = np.array([
            RIS_SWITCH_PENALTY if a % self.n_ris_configs != self.current_ris else 0.0
            for a in actions
        ])
        utility = weight * (2.25 * p - 1.25) - weight * latency / 250.0
        utility += np.minimum(0.15, throughput / 100.0) * p - change_cost
        utility[~available] = -np.inf
        if not np.isfinite(utility).any():
            return self.wait_action
        return int(np.argmax(utility))
