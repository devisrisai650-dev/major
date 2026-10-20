"""Periodic environment-only assessment for eligible email alerts."""
# ruff: noqa: E401, E701, E702
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any
from services.alert_service import dispatch_environmental_indicator_alert,dispatch_verified_flood_alert
from services.flood_api import get_discharge_analysis
from services.flood_state import analyze_flood_state
from services.gauge_provider import CsvReplayProvider
from services.region_manager import load_regions
from services.weather_service import get_weather_data

logger=logging.getLogger(__name__)

def monitor_configuration()->dict[str,Any]:
    enabled=os.getenv("FLOODAI_ALERT_MONITOR_ENABLED","false").strip().lower() in {"1","true","yes","on"}
    interval=max(60,min(int(os.getenv("FLOODAI_ALERT_MONITOR_INTERVAL_SECONDS","300")),3600))
    return {"enabled":enabled,"interval_seconds":interval}

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
    rain=analysis.get("rainfall",{})
    rain_class=str(rain.get("classification","UNKNOWN")).upper()
    # This separate email is an advisory about live environmental indicators,
    # not a claim of an official flood warning. Synthetic dashboard data is not used here.
    indicator_result={"sent":0,"eligible":False,"reason":"No moderate/high live rainfall indicator."}
    if rain_class in {"MODERATE","HIGH","VERY_HIGH"}:
        level="MODERATE" if rain_class=="MODERATE" else "HIGH"
        observed_at=str(weather.get("current",{}).get("time") or analysis.get("timestamp") or "")
        # One advisory per region, per level, per calendar day. Keying on the full observation
        # timestamp (which changes every ~15 minutes) re-emailed everyone for the same rain event.
        # A MODERATE -> HIGH escalation still produces a new email because the level differs.
        indicator_result=dispatch_environmental_indicator_alert(
            region_id=str(region["id"]),region_name=str(region["name"]),level=level,
            event_id=f"{level}:{observed_at[:10]}",observed_at=observed_at,
            source="Open-Meteo live weather data",
            indicators=f"current rainfall={rain.get('current_rain_mm')} mm; 6-hour rainfall={rain.get('last_6h_precipitation_mm')} mm")
    return {"region_id":region["id"],"assessment_status":assessment.get("status","NOT_ASSESSED"),
            "alert":result,"environmental_indicator_email":indicator_result}

_STATE:dict[str,Any]={"last_run_at":None,"runs":0,"regions":[]}

def monitor_state()->dict[str,Any]:
    """Snapshot of the most recent monitor cycle, for the admin dashboard."""
    return {"last_run_at":_STATE["last_run_at"],"runs":_STATE["runs"],"regions":list(_STATE["regions"])}

def _summarize(region:dict[str,Any],result:dict[str,Any]|None,error:str|None)->dict[str,Any]:
    if result is None:
        return {"region_id":region.get("id","unknown"),"region_name":region.get("name"),"error":error}
    indicator=result.get("environmental_indicator_email",{})
    return {"region_id":result["region_id"],"region_name":region.get("name"),"assessment_status":result["assessment_status"],
            "official_alert_sent":result["alert"].get("sent",0),"indicator_sent":indicator.get("sent",0),
            "indicator_eligible":indicator.get("eligible",False),"indicator_duplicate":bool(indicator.get("duplicate")),
            "delivery_errors":int(result["alert"].get("delivery_errors",0))+int(indicator.get("delivery_errors",0)),
            "indicator_note":indicator.get("reason"),"error":None}

def _check_all_regions()->None:
    summaries:list[dict[str,Any]]=[]
    try:
        regions=load_regions()
    except Exception:
        logger.exception("Could not load FloodAI alert-monitor regions.")
        _STATE.update(last_run_at=datetime.now(timezone.utc).isoformat(),runs=_STATE["runs"]+1,
                      regions=[{"region_id":"*","error":"Could not load regions."}])
        return
    for region in regions:
        try:
            result=check_region(region)
            summaries.append(_summarize(region,result,None))
            logger.info("FloodAI alert monitor region=%s status=%s eligible=%s sent=%s reason=%s",
                        result["region_id"],result["assessment_status"],result["alert"].get("eligible",False),
                        result["alert"].get("sent",0),result["alert"].get("reason","eligible"))
        except Exception as exc:
            logger.exception("FloodAI alert monitor failed for region=%s",region.get("id","unknown"))
            summaries.append(_summarize(region,None,f"{type(exc).__name__}: {str(exc)[:160]}"))
    _STATE.update(last_run_at=datetime.now(timezone.utc).isoformat(),runs=_STATE["runs"]+1,regions=summaries)

async def _monitor_loop(interval_seconds:int)->None:
    while True:
        await asyncio.to_thread(_check_all_regions)
        await asyncio.sleep(interval_seconds)

def start_alert_monitor():
    config=monitor_configuration()
    if not config["enabled"]:
        logger.info("FloodAI automatic alert monitor is disabled.")
        return None
    interval=config["interval_seconds"]
    logger.info("Starting FloodAI alert monitor; interval=%s seconds.",interval)
    return asyncio.create_task(_monitor_loop(interval),name="floodai-alert-monitor")

async def stop_alert_monitor(task)->None:
    if task is None: return
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
