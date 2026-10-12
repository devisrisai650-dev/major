import csv
from pathlib import Path


DATASET = Path(__file__).resolve().parents[1] / "data" / "demo_flood_scenarios.csv"


def test_demo_dataset_covers_all_regions_and_hours():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 72
    assert {row["region_id"] for row in rows} == {
        "region_001", "region_002", "region_003"
    }
    assert {row["hour"] for row in rows} == {
        f"{hour:02d}:00" for hour in range(24)
    }


def test_noon_demo_contains_requested_severe_flood_scenario():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["hour"] == "12:00"
        ]
    assert len(rows) == 3
    for row in rows:
        assert float(row["rainfall_mm_per_hour"]) == 80.0
        assert float(row["water_level_rise_m_per_hour"]) == 0.25
        assert row["communication_status"] == "PARTIAL_OUTAGE"


def test_demo_dataset_has_non_severe_hours_for_playback():
    with DATASET.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert any(float(row["rainfall_mm_per_hour"]) <= 2 for row in rows)
    assert any(row["communication_status"] == "NORMAL" for row in rows)
    assert any(row["communication_status"] == "DEGRADED" for row in rows)
