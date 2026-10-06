import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "regions.json"


def load_regions():
    with CONFIG_PATH.open(encoding="utf-8") as file:
        config = json.load(file)
    regions = config.get("regions")
    if not isinstance(regions, list):
        raise TypeError(f"Invalid regions configuration: {CONFIG_PATH}")
    return regions


def get_region(region_id):
    for region in load_regions():
        if region.get("id") == region_id:
            return region
    raise ValueError(f"Region '{region_id}' not found")
