"""Software-only partially observable RIS-CNOMA environment."""
from __future__ import annotations

from collections import deque

import numpy as np

from channel_simulator import ChannelSimulator
from cnoma import CNOMASimulator

PRIORITY_WEIGHT = {"LOW": 1.0, "MEDIUM": 1.5, "HIGH": 2.5, "CRITICAL": 4.0}
RIS_SWITCH_PENALTY = 0.20
POWER_SWITCH_PENALTY = 0.05


class RISEnvironment:
    """Virtual channel/RIS/CNOMA environment; every radio value is simulated."""

    def __init__(
        self,
        n_channels=3,
        n_ris_configs=8,
        n_ris_elements=8,
        n_power_profiles=3,
        seed=None,
        max_steps=80,
        observation_mode="partial",
        snr_noise_std_db=1.5,
        observation_delay=1,
        channel_context=None,
        node_loss_probability=0.0,
    ):
        if observation_mode not in {"partial", "oracle"}:
            raise ValueError("observation_mode must be 'partial' or 'oracle'")
        if snr_noise_std_db < 0 or observation_delay < 0:
            raise ValueError("observation noise and delay must be non-negative")
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.n_channels = n_channels
        self.n_ris_configs = n_ris_configs
        self.n_power_profiles = n_power_profiles
        self.max_steps = max_steps
        self.wait_action = n_channels * n_ris_configs * n_power_profiles
        self.n_actions = self.wait_action + 1
        self.observation_mode = observation_mode
        self.snr_noise_std_db = snr_noise_std_db
        self.observation_delay = observation_delay
        self.channel_context = channel_context or {}
        self.node_loss_probability = float(np.clip(node_loss_probability, 0.0, 1.0))
        self.simulator = ChannelSimulator(
            n_channels, n_ris_configs, n_ris_elements, seed
        )
        self.cnoma = CNOMASimulator()
        self.current_ris = 0
        self.current_power_profile = 0
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
        self._last_observation = None

    def reset(self, priority=None):
        if priority is None:
            priority = str(self.rng.choice(list(PRIORITY_WEIGHT)))
        if priority not in PRIORITY_WEIGHT:
            raise ValueError(f"Unknown message priority {priority!r}")
        self.priority = priority
        self.current_ris = 0
        self.current_power_profile = 0
        self.step_count = 0
        self.simulator.set_environment(
            rain_mm=self.channel_context.get("rain_mm"),
            flow_velocity_mps=self.channel_context.get("flow_velocity_mps"),
            water_depth_m=self.channel_context.get("water_depth_m"),
            debris_density=self.channel_context.get("debris_density"),
            los_obstruction=self.channel_context.get("los_obstruction"),
            node_loss_probability=self.node_loss_probability,
        )
        self.measurements = self.simulator.reset()
        self._history.clear()
        self._history.append(self.measurements)
        return self.observe()

    def _cnoma_probability(self, measurements):
        probabilities = np.zeros(
            (self.n_channels, self.n_ris_configs, self.n_power_profiles),
            dtype=float,
        )
        critical_user = 1 if self.priority in {"HIGH", "CRITICAL"} else 2
        for c in range(self.n_channels):
            second = (c + 1) % self.n_channels
            for r in range(self.n_ris_configs):
                for p in range(self.n_power_profiles):
                    result = self.cnoma.evaluate(
                        float(measurements["snr_db"][c, r]),
                        float(measurements["snr_db"][second, r]),
                        p,
                        critical_user=critical_user,
                    )
                    probabilities[c, r, p] = float(
                        result.user1_decoded if critical_user == 1 else result.user2_decoded
                    )
        return probabilities

    def _observed_measurements(self):
        if self.observation_mode == "oracle":
            source = self.measurements
        elif len(self._history) <= self.observation_delay:
            source = self._history[0]
        else:
            source = list(self._history)[-(self.observation_delay + 1)]
        result = {
            key: value.copy() if hasattr(value, "copy") else value
            for key, value in source.items()
        }
        if self.observation_mode == "partial":
            result["snr_db"] += self.rng.normal(
                0.0, self.snr_noise_std_db, result["snr_db"].shape
            )
            result["success_probability"] = np.clip(
                1.0
                / (1.0 + np.exp(-((result["snr_db"] - 2.0) / 2.5))),
                0.0,
                1.0,
            )
            result["available"] = (
                result["snr_db"] >= -3.0
            ) & result["node_available"][:, None]
        result["cnoma_success_probability"] = self._cnoma_probability(result)
        return result

    def observe(self):
        observed = self._observed_measurements()
        self._last_observation = {
            "snr_db": observed["snr_db"].copy(),
            "success_probability": observed["success_probability"].copy(),
            "cnoma_success_probability": observed["cnoma_success_probability"].copy(),
            "latency_ms": observed["latency_ms"].copy(),
            "throughput_mbps": observed["throughput_mbps"].copy(),
            "available": observed["available"].copy(),
            "node_available": observed["node_available"].copy(),
            "rain_attenuation_db": float(observed["rain_attenuation_db"]),
            "doppler_hz": float(observed["doppler_hz"]),
            "k_factor": observed["k_factor"].copy(),
            "current_ris_config": self.current_ris,
            "current_power_profile": self.current_power_profile,
            "priority": self.priority,
            "step": self.step_count,
            "observation_mode": self.observation_mode,
            "observation_noise_std_db": self.snr_noise_std_db,
            "observation_delay_steps": self.observation_delay,
            "simulation_only": True,
        }
        return {
            key: value.copy() if hasattr(value, "copy") else value
            for key, value in self._last_observation.items()
        }

    def action_mask(self, observation=None):
        observation = observation or self._last_observation or self.observe()
        mask = np.zeros(self.n_actions, dtype=bool)
        availability = observation["available"]
        for c in range(self.n_channels):
            for r in range(self.n_ris_configs):
                if not availability[c, r]:
                    continue
                base = (c * self.n_ris_configs + r) * self.n_power_profiles
                mask[base:base + self.n_power_profiles] = True
        if not mask.any():
            mask[self.wait_action] = True
        return mask

    def action_to_tuple(self, action):
        if action == self.wait_action:
            return None
        block, power = divmod(int(action), self.n_power_profiles)
        channel, ris = divmod(block, self.n_ris_configs)
        return channel, ris, power

    def step(self, action, packet=None):
        if not 0 <= int(action) < self.n_actions:
            raise ValueError(f"Action must be in [0, {self.n_actions - 1}]")
        action = int(action)
        weight = PRIORITY_WEIGHT[self.priority]
        changed_ris = False
        changed_power = False
        delivered = False
        selected_channel = None
        selected_ris = self.current_ris
        power_profile = self.current_power_profile
        snr_db = latency_ms = None
        throughput_mbps = 0.0
        receiver_packet = None
        channel_condition = None
        cnoma_result = None

        if action == self.wait_action:
            reward = -0.30 * weight
        else:
            selected_channel, selected_ris, power_profile = self.action_to_tuple(action)
            snr_db = float(self.measurements["snr_db"][selected_channel, selected_ris])
            latency_ms = float(
                self.measurements["latency_ms"][selected_channel, selected_ris]
            )
            throughput_mbps = float(
                self.measurements["throughput_mbps"][selected_channel, selected_ris]
            )
            second = (selected_channel + 1) % self.n_channels
            critical_user = 1 if self.priority in {"HIGH", "CRITICAL"} else 2
            cnoma_result = self.cnoma.evaluate(
                snr_db,
                float(self.measurements["snr_db"][second, selected_ris]),
                power_profile,
                critical_user=critical_user,
                noise_db=-90.0 + float(self.measurements["rain_attenuation_db"]),
            )
            critical_decoded = (
                cnoma_result.user1_decoded
                if critical_user == 1
                else cnoma_result.user2_decoded
            )
            delivered = bool(critical_decoded and self.rng.random() < max(
                0.05, float(self.measurements["success_probability"][selected_channel, selected_ris])
            ))
            channel_condition = (
                "GOOD" if snr_db >= 10 else
                "MODERATE" if snr_db >= 5 else
                "POOR" if snr_db >= 0 else "SEVERE"
            )
            changed_ris = selected_ris != self.current_ris
            changed_power = power_profile != self.current_power_profile
            reward = weight * (1.0 if delivered else -1.25)
            reward += weight * (0.25 if cnoma_result.sic_success else -0.20)
            reward -= weight * latency_ms / 250.0
            reward -= RIS_SWITCH_PENALTY if changed_ris else 0.0
            reward -= POWER_SWITCH_PENALTY if changed_power else 0.0
            if delivered:
                receiver_packet = packet
                reward += min(0.15, throughput_mbps / 100.0)
            self.current_ris = selected_ris
            self.current_power_profile = power_profile

        self.step_count += 1
        self.simulator.advance()
        self.measurements = self.simulator.measure()
        self._history.append(self.measurements)
        done = self.step_count >= self.max_steps
        info = {
            "delivered": delivered,
            "selected_channel": selected_channel,
            "channel_candidate": (
                f"sim_candidate_{selected_channel + 1}"
                if selected_channel is not None else None
            ),
            "selected_ris_config": selected_ris,
            "power_profile": power_profile,
            "power_user1": (
                cnoma_result.power_user1 if cnoma_result else None
            ),
            "power_user2": (
                cnoma_result.power_user2 if cnoma_result else None
            ),
            "channel_condition": channel_condition,
            "snr_db": snr_db,
            "user1_sinr_db": cnoma_result.user1_sinr_db if cnoma_result else None,
            "user2_sinr_db": cnoma_result.user2_sinr_db if cnoma_result else None,
            "sic_success": cnoma_result.sic_success if cnoma_result else False,
            "cnoma_user1_decoded": cnoma_result.user1_decoded if cnoma_result else False,
            "cnoma_user2_decoded": cnoma_result.user2_decoded if cnoma_result else False,
            "latency_ms": latency_ms,
            "throughput_mbps": throughput_mbps,
            "changed_ris": changed_ris,
            "changed_power": changed_power,
            "node_available": (
                bool(self.measurements["node_available"][selected_channel])
                if selected_channel is not None else False
            ),
            "rain_attenuation_db": float(self.measurements["rain_attenuation_db"]),
            "doppler_hz": float(self.measurements["doppler_hz"]),
            "waited": action == self.wait_action,
            "sender_packet": packet,
            "receiver_packet": receiver_packet,
            "priority": self.priority,
            "simulation_only": True,
            "observation_mode": self.observation_mode,
        }
        return self.observe(), float(reward), done, info

    def greedy_baseline_action(self, observation=None):
        observation = observation or self._last_observation or self.observe()
        available = observation["available"]
        p = observation["cnoma_success_probability"]
        latency = observation["latency_ms"]
        throughput = observation["throughput_mbps"]
        weight = PRIORITY_WEIGHT[self.priority]
        best = self.wait_action
        best_value = -np.inf
        for c in range(self.n_channels):
            for r in range(self.n_ris_configs):
                for power in range(self.n_power_profiles):
                    if not available[c, r]:
                        continue
                    utility = (
                        weight * (2.25 * p[c, r, power] - 1.25)
                        - weight * latency[c, r] / 250.0
                        + min(0.15, throughput[c, r] / 100.0)
                    )
                    utility -= (
                        RIS_SWITCH_PENALTY
                        if r != self.current_ris else 0.0
                    )
                    utility -= (
                        POWER_SWITCH_PENALTY
                        if power != self.current_power_profile else 0.0
                    )
                    if utility > best_value:
                        best_value = utility
                        best = (
                            (c * self.n_ris_configs + r) * self.n_power_profiles
                            + power
                        )
        return int(best)
