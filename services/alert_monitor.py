"""Periodic environment-only assessment for eligible email alerts."""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Any
from services.alert_service import dispatch_verified_flood_alert
from services.flood_api import get_discharge_analysis
from services.flood_state import analyze_flood_state
from services.gauge_provider import CsvReplayProvider
from services.region_manager import get_region, load_regions
from services.weather_service import get_weather_data

logger=logging.getLogger(__name__)

def check_region(region:dict[str,Any])->dict[str,Any]:
    """Fetch environmental evidence and dispatch only if the assessment passes every gate."""
    weather=get_weather_data(region["latitude"],region["longitude"],region.get("timezone","Asia/Kolkata"))
    discharge=get_discharge_analysis(region["latitude"],region["longitude"])
    water=CsvReplayProvider().get_water_level(region)
    analysis=analyze_flood_state(weather,discharge,water)
    assessment=analysis.get("flood_assessment",{})
    evidence={
      "official_thresholds_verified":assessment.get("official_thresholds_verified") is True,
      "fresh_qc_gauge":assessment.get("fresh_qc_gauge") is True,
      "source_is_authoritative":assessment.get("source_is_authoritative") is True,
      "simulation_only":assessment.get("simulation_only") is True,
      "source_name":assessment.get("source_name"),
    }
    result=dispatch_verified_flood_alert(region_id=str(region["id"]),region_name=str(region["name"]),
                                          assessment=assessment,evidence=evidence)
    return {"region_id":region["id"],"assessment_status":assessment.get("status","NOT_ASSESSED"),
            "alert":result}

def _check_all_regions()->None:
    try:
        regions=load_regions()
    except Exception:
        logger.exception("Could not load FloodAI alert-monitor regions.")
        return
    for region in regions:
        try:
            result=check_region(region)
            logger.info("FloodAI alert monitor region=%s status=%s eligible=%s",
                        result["region_id"],result["assessment_status"],result["alert"].get("eligible",False))
        except Exception:
            logger.exception("FloodAI alert monitor failed for region=%s",region.get("id","unknown"))

async def _monitor_loop(interval_seconds:int)->None:
    while True:
        await asyncio.to_thread(_check_all_regions)
        await asyncio.sleep(interval_seconds)

def start_alert_monitor():
    enabled=os.getenv("FLOODAI_ALERT_MONITOR_ENABLED","false").lower() in {"1","true","yes"}
    if not enabled:
        logger.info("FloodAI automatic alert monitor is disabled.")
        return None
    interval=max(60,min(int(os.getenv("FLOODAI_ALERT_MONITOR_INTERVAL_SECONDS","300")),3600))
    logger.info("Starting FloodAI alert monitor; interval=%s seconds.",interval)
    return asyncio.create_task(_monitor_loop(interval),name="floodai-alert-monitor")

async def stop_alert_monitor(task)->None:
    if task is None: return
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
