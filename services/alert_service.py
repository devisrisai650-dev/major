"""Safety-gated flood-alert dispatch; simulated/incomplete assessments never email users."""
# ruff: noqa: E401, E701, E702
from __future__ import annotations
import logging
from typing import Any
from services.auth_service import finish_alert_dispatch,get_verified_alert_recipients,reserve_alert_dispatch
from services.email_service import send_flood_alert
logger=logging.getLogger(__name__)
ALERT_STATUSES={"WARNING","FLOOD","EMERGENCY"}
def dispatch_verified_flood_alert(*,region_id:str,region_name:str,assessment:dict[str,Any],evidence:dict[str,Any])->dict[str,Any]:
    status_value=str(assessment.get("status","")).upper(); event_id=str(assessment.get("event_id","")).strip()
    if (status_value not in ALERT_STATUSES or assessment.get("complete") is not True or not event_id
        or evidence.get("official_thresholds_verified") is not True or evidence.get("fresh_qc_gauge") is not True
        or evidence.get("source_is_authoritative") is not True or evidence.get("simulation_only") is True):
        return {"sent":0,"eligible":False,"reason":"Verified official alert evidence is incomplete."}
    if not reserve_alert_dispatch(region_id,status_value,event_id): return {"sent":0,"eligible":True,"duplicate":True}
    recipients=get_verified_alert_recipients()
    observed_at=str(assessment.get("observed_at") or assessment.get("timestamp") or "not provided")
    source=str(evidence.get("source_name") or "verified official source")
    message=str(assessment.get("message") or "Follow official local emergency guidance.")
    sent=0; errors=0
    for recipient in recipients:
        try:
            send_flood_alert(recipient,region=region_name,status=status_value,observed_at=observed_at,source=source,message=message); sent+=1
        except Exception:
            errors+=1; logger.exception("Flood alert email delivery failed for a recipient.")
    finish_alert_dispatch(region_id,status_value,event_id,sent)
    return {"sent":sent,"eligible":True,"recipient_count":len(recipients),"delivery_errors":errors}
