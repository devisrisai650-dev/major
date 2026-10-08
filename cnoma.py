"""Software-only two-user CNOMA model with SIC decoding.

All radio values are synthetic. This module is a research simulation component,
not a physical modem implementation or field measurement system.
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
    simulation_only: bool = True


class CNOMASimulator:
    """Two-user downlink power-domain NOMA with simplified SIC."""

    POWER_PROFILES = (
        (0.70, 0.30),
        (0.60, 0.40),
        (0.80, 0.20),
    )

    def __init__(self, noise_floor_db: float = -90.0, sinr_threshold_db: float = 3.0):
        if not 0.0 < sinr_threshold_db < 30.0:
            raise ValueError("sinr_threshold_db must be between 0 and 30 dB")
        self.noise_floor_db = float(noise_floor_db)
        self.sinr_threshold_db = float(sinr_threshold_db)

    @staticmethod
    def _linear(db: float) -> float:
        return 10.0 ** (float(db) / 10.0)

    @staticmethod
    def _db(value: float) -> float:
        return 10.0 * np.log10(max(float(value), 1e-12))

    def evaluate(
        self,
        user1_channel_db: float,
        user2_channel_db: float,
        power_profile: int = 0,
        critical_user: int = 1,
        noise_db: float = -90.0,
    ) -> CNOMAResult:
        if power_profile not in range(len(self.POWER_PROFILES)):
            raise ValueError("Unknown CNOMA power profile")
        if critical_user not in {1, 2}:
            raise ValueError("critical_user must be 1 or 2")

        p1, p2 = self.POWER_PROFILES[power_profile]
        g1 = self._linear(user1_channel_db)
        g2 = self._linear(user2_channel_db)
        noise = self._linear(noise_db)

        # User 1 is the stronger-channel user in the conventional SIC order.
        # The critical user can still be assigned to either logical stream.
        strong = 1 if g1 >= g2 else 2
        weak = 2 if strong == 1 else 1
        powers = {1: p1, 2: p2}
        gains = {1: g1, 2: g2}

        weak_signal = powers[weak] * gains[weak]
        strong_signal = powers[strong] * gains[strong]

        weak_sinr = weak_signal / (strong_signal + noise)
        weak_sinr_db = self._db(weak_sinr)
        weak_decoded = weak_sinr_db >= self.sinr_threshold_db

        if weak_decoded:
            strong_sinr = strong_signal / noise
            sic_success = True
        else:
            strong_sinr = strong_signal / (weak_signal + noise)
            sic_success = False

        strong_sinr_db = self._db(strong_sinr)
        strong_decoded = strong_sinr_db >= self.sinr_threshold_db and sic_success

        decoded = {weak: weak_decoded, strong: strong_decoded}
        sinr = {weak: weak_sinr_db, strong: strong_sinr_db}
        interference = self._db(strong_signal if weak == 1 else weak_signal)

        return CNOMAResult(
            user1_sinr_db=float(sinr[1]),
            user2_sinr_db=float(sinr[2]),
            user1_decoded=bool(decoded[1]),
            user2_decoded=bool(decoded[2]),
            sic_success=bool(sic_success),
            power_user1=p1,
            power_user2=p2,
            critical_user=critical_user,
            interference_db=float(interference),
        )

    @classmethod
    def power_profile(cls, index: int) -> tuple[float, float]:
        if index not in range(len(cls.POWER_PROFILES)):
            raise ValueError("Unknown CNOMA power profile")
        return cls.POWER_PROFILES[index]
