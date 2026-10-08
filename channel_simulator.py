"""Software-only physics-informed time-varying channel and virtual RIS simulator.

All returned radio values are synthetic. Environmental inputs only perturb the
simulation; they do not establish measured radio conditions.
"""
from __future__ import annotations

import numpy as np


class ChannelSimulator:
    def __init__(
        self,
        n_channels: int = 3,
        n_ris_configs: int = 8,
        n_ris_elements: int = 8,
        seed: int | None = None,
    ):
        if n_channels < 1 or n_ris_configs < 2 or n_ris_elements < 1:
            raise ValueError("Need >=1 channel/element and >=2 RIS configurations")
        self.n_channels = n_channels
        self.n_ris_configs = n_ris_configs
        self.n_ris_elements = n_ris_elements
        self.rng = np.random.default_rng(seed)
        self.rho = 0.92
        self.carrier_hz = 3.5e9
        self.c_light = 299_792_458.0
        self.environment = {}
        self.codebook = self._make_codebook()
        self.reset()

    def _make_codebook(self) -> np.ndarray:
        element = np.arange(self.n_ris_elements)
        configs = np.arange(self.n_ris_configs)[:, None]
        return np.exp(1j * 2 * np.pi * configs * element / self.n_ris_configs)

    def _complex_normal(self, shape):
        return (
            self.rng.normal(size=shape) + 1j * self.rng.normal(size=shape)
        ) / np.sqrt(2)

    def set_environment(
        self,
        rain_mm: float | None = None,
        flow_velocity_mps: float | None = None,
        water_depth_m: float | None = None,
        debris_density: float | None = None,
        los_obstruction: float | None = None,
        node_loss_probability: float = 0.0,
    ):
        self.environment = {
            "rain_mm": max(0.0, float(rain_mm or 0.0)),
            "flow_velocity_mps": max(0.0, float(flow_velocity_mps or 0.0)),
            "water_depth_m": max(0.0, float(water_depth_m or 0.0)),
            "debris_density": float(np.clip(debris_density or 0.0, 0.0, 1.0)),
            "los_obstruction": float(np.clip(los_obstruction or 0.0, 0.0, 1.0)),
        }

    def reset(self):
        self.step_count = 0
        self.direct = self._complex_normal(self.n_channels)
        self.reflected = self._complex_normal(
            (self.n_channels, self.n_ris_elements)
        )
        self.los_phase = self.rng.uniform(-np.pi, np.pi, self.n_channels)
        self.k_factor = self._environment_k_factor()
        self.noise_db = self.rng.normal(0.0, 1.5, self.n_channels)
        self.link_budget_db = np.linspace(5.0, 10.0, self.n_channels)
        return self.measure()

    def _environment_k_factor(self):
        base = self.rng.uniform(0.2, 6.0, self.n_channels)
        obstruction = self.environment.get("los_obstruction", 0.0)
        debris = self.environment.get("debris_density", 0.0)
        depth = self.environment.get("water_depth_m", 0.0)
        return np.clip(base + 2.0 - 4.0 * obstruction - 1.5 * debris - 0.4 * depth, 0.05, 12.0)

    def _rain_attenuation_db(self):
        rain = self.environment.get("rain_mm", 0.0)
        return min(12.0, 0.018 * rain**1.15)

    def _doppler_hz(self):
        velocity = self.environment.get("flow_velocity_mps", 0.0)
        return velocity * self.carrier_hz / self.c_light

    def advance(self):
        innovation = np.sqrt(1.0 - self.rho**2)
        self.direct = self.rho * self.direct + innovation * self._complex_normal(
            self.n_channels
        )
        self.reflected = self.rho * self.reflected + innovation * self._complex_normal(
            (self.n_channels, self.n_ris_elements)
        )
        doppler_phase = 2.0 * np.pi * self._doppler_hz() * 0.01
        self.los_phase = (
            self.los_phase
            + self.rng.normal(0, 0.15, self.n_channels)
            + doppler_phase
            + np.pi
        ) % (2 * np.pi) - np.pi
        self.noise_db = 0.85 * self.noise_db + 0.15 * self.rng.normal(
            0, 2.0, self.n_channels
        )
        if self.step_count and self.step_count % 20 == 0:
            index = int(self.rng.integers(self.n_channels))
            self.noise_db[index] += float(self.rng.uniform(3.0, 8.0))
        self.step_count += 1

    def _effective_gain(self, channel: int, ris_config: int) -> float:
        k = self.k_factor[channel]
        direct = (
            np.sqrt(k / (k + 1.0))
            * np.exp(1j * self.los_phase[channel])
            + np.sqrt(1.0 / (k + 1.0)) * self.direct[channel]
        )
        ris_gain = (
            0.48
            * np.sum(self.reflected[channel] * self.codebook[ris_config])
            / np.sqrt(self.n_ris_elements)
        )
        return float(np.abs(direct + ris_gain))

    def measure(self) -> dict:
        snr = np.empty((self.n_channels, self.n_ris_configs), dtype=float)
        success_probability = np.empty_like(snr)
        latency_ms = np.empty_like(snr)
        throughput_mbps = np.empty_like(snr)
        rain_loss = self._rain_attenuation_db()
        for c in range(self.n_channels):
            for r in range(self.n_ris_configs):
                gain = max(self._effective_gain(c, r), 1e-5)
                snr_db = float(
                    np.clip(
                        self.link_budget_db[c]
                        + 20 * np.log10(gain)
                        - self.noise_db[c]
                        - rain_loss,
                        -25,
                        30,
                    )
                )
                p_success = float(
                    1.0
                    / (
                        1.0
                        + np.exp(-np.clip((snr_db - 2.0) / 2.5, -30, 30))
                    )
                )
                snr[c, r] = snr_db
                success_probability[c, r] = p_success
                latency_ms[c, r] = (
                    18.0
                    + 85.0 * (1.0 - p_success)
                    + max(0.0, 3.0 - snr_db) * 3.0
                )
                throughput_mbps[c, r] = (
                    2.0 * np.log2(1.0 + 10.0 ** (snr_db / 10.0)) * p_success
                )
        return {
            "snr_db": snr,
            "success_probability": success_probability,
            "latency_ms": latency_ms,
            "throughput_mbps": throughput_mbps,
            "available": snr >= -3.0,
            "rain_attenuation_db": rain_loss,
            "doppler_hz": self._doppler_hz(),
            "k_factor": self.k_factor.copy(),
            "simulation_only": True,
        }
