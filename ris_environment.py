"""Discrete software environment for channel selection and virtual RIS control."""

from __future__ import annotations

import numpy as np

from channel_simulator import ChannelSimulator


PRIORITY_WEIGHT = {"LOW": 1.0, "MEDIUM": 1.5, "HIGH": 2.5, "CRITICAL": 4.0}
RIS_SWITCH_PENALTY = 0.20


class RISEnvironment:
    def __init__(self, n_channels: int = 3, n_ris_configs: int = 8,
                 n_ris_elements: int = 8, seed: int | None = None,
                 max_steps: int = 80):
        self.rng = np.random.default_rng(seed)
        self.n_channels = n_channels
        self.n_ris_configs = n_ris_configs
        self.max_steps = max_steps
        self.wait_action = n_channels * n_ris_configs
        self.n_actions = self.wait_action + 1
        self.simulator = ChannelSimulator(n_channels, n_ris_configs, n_ris_elements, seed)
        self.current_ris = 0
        self.priority = "LOW"
        self.step_count = 0
        self.measurements = None

    def reset(self, priority: str | None = None):
        if priority is None:
            priority = str(self.rng.choice(list(PRIORITY_WEIGHT)))
        if priority not in PRIORITY_WEIGHT:
            raise ValueError(f"Unknown message priority {priority!r}")
        self.priority = priority
        self.current_ris = 0
        self.step_count = 0
        self.measurements = self.simulator.reset()
        return self.observe()

    def observe(self) -> dict:
        return {
            "snr_db": self.measurements["snr_db"].copy(),
            "success_probability": self.measurements["success_probability"].copy(),
            "latency_ms": self.measurements["latency_ms"].copy(),
            "throughput_mbps": self.measurements["throughput_mbps"].copy(),
            "available": self.measurements["available"].copy(),
            "current_ris_config": self.current_ris,
            "priority": self.priority,
            "step": self.step_count,
            "simulation_only": True,
        }

    def action_mask(self) -> np.ndarray:
        mask = np.zeros(self.n_actions, dtype=bool)
        mask[:self.wait_action] = self.measurements["available"].reshape(-1)
        if not mask.any():
            mask[self.wait_action] = True
        return mask

    def step(self, action: int, packet: str | None = None):
        if not 0 <= int(action) < self.n_actions:
            raise ValueError(f"Action must be in [0, {self.n_actions - 1}]")
        action = int(action)
        mask = self.action_mask()
        if not mask[action]:
            raise ValueError("Selected action is unavailable under the current simulated measurements")

        priority_weight = PRIORITY_WEIGHT[self.priority]
        changed_ris = False
        delivered = False
        selected_channel = None
        selected_ris = self.current_ris
        snr_db = None
        latency_ms = None
        throughput_mbps = 0.0
        receiver_packet = None
        channel_condition = None
        if action == self.wait_action:
            # Queue/store-and-forward: no false claim of a successful delivery.
            reward = -0.30 * priority_weight
        else:
            selected_channel, selected_ris = divmod(action, self.n_ris_configs)
            snr_db = float(self.measurements["snr_db"][selected_channel, selected_ris])
            p_success = float(self.measurements["success_probability"][selected_channel, selected_ris])
            latency_ms = float(self.measurements["latency_ms"][selected_channel, selected_ris])
            throughput_mbps = float(self.measurements["throughput_mbps"][selected_channel, selected_ris])
            delivered = bool(self.rng.random() < p_success)
            if snr_db >= 10.0:
                channel_condition = "GOOD"
            elif snr_db >= 5.0:
                channel_condition = "MODERATE"
            elif snr_db >= 0.0:
                channel_condition = "POOR"
            else:
                channel_condition = "SEVERE"
            if delivered:
                receiver_packet = packet
            changed_ris = selected_ris != self.current_ris
            # Simulated semantic delivery reward, delay penalty and reconfiguration cost.
            reward = priority_weight * (1.0 if delivered else -1.25)
            reward -= priority_weight * (latency_ms / 250.0)
            reward -= RIS_SWITCH_PENALTY if changed_ris else 0.0
            if delivered:
                reward += min(0.15, throughput_mbps / 100.0)
            self.current_ris = selected_ris

        self.step_count += 1
        self.simulator.advance()
        self.measurements = self.simulator.measure()
        done = self.step_count >= self.max_steps
        info = {
            "delivered": delivered,
            "selected_channel": selected_channel,
            "channel_candidate": (f"sim_candidate_{selected_channel + 1}"
                                  if selected_channel is not None else None),
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
        }
        return self.observe(), float(reward), done, info

    def greedy_baseline_action(self) -> int:
        """Myopic best expected-utility choice from current simulated metrics."""
        available = self.action_mask()
        if available[self.wait_action]:
            return self.wait_action
        p = self.measurements["success_probability"].reshape(-1)
        latency = self.measurements["latency_ms"].reshape(-1)
        throughput = self.measurements["throughput_mbps"].reshape(-1)
        actions = np.arange(self.wait_action)
        change_cost = np.array([
            RIS_SWITCH_PENALTY if (a % self.n_ris_configs) != self.current_ris else 0.0
            for a in actions
        ])
        weight = PRIORITY_WEIGHT[self.priority]
        utility = weight * (2.25 * p - 1.25) - weight * latency / 250.0
        utility += np.minimum(0.15, throughput / 100.0) * p - change_cost
        utility[~available[:self.wait_action]] = -np.inf
        return int(np.argmax(utility))
