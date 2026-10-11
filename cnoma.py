"""Software-only two-user CNOMA model with SIC decoding.

Inputs are per-user post-noise SNR values in dB, including any channel/rain
loss already applied by ChannelSimulator. Power profiles are (weak-user share,
strong-user share). This is a normalized-SNR abstraction, not a calibrated
physical-layer receiver or field measurement system.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CNOMAResult:
    user1_sinr_db: float
    user2_sinr_db: float
    user1_decoded: bool
    user2_decoded: bool
    sic_success: bool
    power_user1: float
    power_user2: float
    critical_user: int
    interference_db: float
    weak_user: int
    strong_user: int
    simulation_only: bool = True


class CNOMASimulator:
    """Two-user downlink power-domain NOMA with threshold-based SIC."""

    # (weak-channel stream power, strong-channel stream power)
    POWER_PROFILES = (
        (0.70, 0.30),
        (0.60, 0.40),
        (0.80, 0.20),
    )

    def __init__(self, sinr_threshold_db: float = 3.0):
        if not 0.0 < sinr_threshold_db < 30.0:
            raise ValueError("sinr_threshold_db must be between 0 and 30 dB")
        self.sinr_threshold_db = float(sinr_threshold_db)

    @staticmethod
    def _linear(db: float) -> float:
        return 10.0 ** (float(db) / 10.0)

    @staticmethod
    def _db(value: float) -> float:
        return float(10.0 * np.log10(max(float(value), 1e-12)))

    def evaluate(
        self,
        user1_channel_db: float,
        user2_channel_db: float,
        power_profile: int = 0,
        critical_user: int = 1,
    ) -> CNOMAResult:
        """Evaluate streams using per-user SNR (dB), not raw channel gain.

        Noise is normalized to one because the input SNR already includes it.
        Rain/channel attenuation must be applied upstream exactly once.
        """
        if power_profile not in range(len(self.POWER_PROFILES)):
            raise ValueError("Unknown CNOMA power profile")
        if critical_user not in {1, 2}:
            raise ValueError("critical_user must be 1 or 2")

        gamma = {1: self._linear(user1_channel_db), 2: self._linear(user2_channel_db)}
        strong = 1 if gamma[1] >= gamma[2] else 2
        weak = 2 if strong == 1 else 1
        weak_power, strong_power = self.POWER_PROFILES[power_profile]
        powers = {weak: weak_power, strong: strong_power}

        # Weak user's own stream is decoded with the strong stream as interference.
        weak_sinr = weak_power * gamma[weak] / (strong_power * gamma[weak] + 1.0)
        weak_decoded = self._db(weak_sinr) >= self.sinr_threshold_db

        # The strong user must decode the weak stream before SIC can succeed.
        weak_stream_at_strong = (
            weak_power * gamma[strong] / (strong_power * gamma[strong] + 1.0)
        )
        sic_success = self._db(weak_stream_at_strong) >= self.sinr_threshold_db
        if sic_success:
            strong_sinr = strong_power * gamma[strong]
        else:
            strong_sinr = (
                strong_power * gamma[strong]
                / (weak_power * gamma[strong] + 1.0)
            )
        strong_decoded = (
            sic_success and self._db(strong_sinr) >= self.sinr_threshold_db
        )

        decoded = {weak: bool(weak_decoded), strong: bool(strong_decoded)}
        sinr = {weak: self._db(weak_sinr), strong: self._db(strong_sinr)}
        # Interference power at the weak receiver, in noise-normalized units.
        interference_db = self._db(strong_power * gamma[weak])

        return CNOMAResult(
            user1_sinr_db=sinr[1],
            user2_sinr_db=sinr[2],
            user1_decoded=decoded[1],
            user2_decoded=decoded[2],
            sic_success=bool(sic_success),
            power_user1=powers[1],
            power_user2=powers[2],
            critical_user=critical_user,
            interference_db=interference_db,
            weak_user=weak,
            strong_user=strong,
        )

    @classmethod
    def power_profile(cls, index: int) -> tuple[float, float]:
        if index not in range(len(cls.POWER_PROFILES)):
            raise ValueError("Unknown CNOMA power profile")
        return cls.POWER_PROFILES[index]
