from __future__ import annotations

from datetime import datetime

from services.water_level import get_water_level_analysis


class GaugeProvider:
    """Interface for current or replayed gauge observations."""

    def get_water_level(self, region: dict, as_of: datetime | None = None) -> dict:
        raise NotImplementedError


class CsvReplayProvider(GaugeProvider):
    """Read the configured CSV gauge as a labeled historical replay."""

    def get_water_level(self, region: dict, as_of: datetime | None = None) -> dict:
        result = get_water_level_analysis(region, as_of=as_of)
        result["provider"] = "csv_replay"
        result["mode"] = "historical_replay"
        return result


class LiveProvider(GaugeProvider):
    """Placeholder for a future live gauge integration."""

    def get_water_level(self, region: dict, as_of: datetime | None = None) -> dict:
        raise NotImplementedError(
            "Live gauge fetching is not implemented in this phase."
        )
