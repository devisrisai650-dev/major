"""Authentication, account preferences, and platform-admin API routes."""
# ruff: noqa: E401, E701, E702
from __future__ import annotations
import hashlib
import logging
import os
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from services.auth_service import (SESSION_COOKIE,_connect,admin_snapshot,audit,authenticate,create_session,create_user,
 get_user_from_request,list_alert_dispatches,list_users,require_admin,require_user,revoke_session,set_alerts_enabled,set_user_active,verify_email_token,validate_email,login_is_locked,record_login_failure,clear_login_failures,email_verification_required)
from services.email_service import send_email, send_verification_email
logger=logging.getLogger(__name__)
router=APIRouter()
class RegisterRequest(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=10,max_length=128)
class LoginRequest(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    password:str=Field(min_length=1,max_length=128)
class NotificationPreference(BaseModel): enabled:bool
class UserStatusUpdate(BaseModel): active:bool
class AdminPipelineRequest(BaseModel):
    region_id:str=Field(min_length=1)
    communication_attempts:int=Field(default=5,ge=1,le=20)
    seed:int=2026
    time_of_day:str=Field(default="12:00",pattern=r"^(?:[01]\d|2[0-3]):00$")
    learn:bool=False

@router.post("/api/auth/register",status_code=201)
def register(payload:RegisterRequest,request:Request)->dict[str,Any]:
    uid,token=create_user(payload.email,payload.password)
    verification_required=email_verification_required()
    sent=False
    if verification_required:
        try: send_verification_email(validate_email(payload.email),token); sent=True
        except Exception as exc:
            logger.exception("Verification email could not be sent.")
            audit("verification_email_failed",target=str(uid),outcome="failure",details=f"{type(exc).__name__}: {str(exc)[:200]}")
    audit("user_registered",target=str(uid),details=f"ip={request.client.host if request.client else 'unknown'}")
    message="Account created. You can sign in now." if not verification_required else "Account created. Verify your email before signing in."
    return {"message":message,"verification_required":verification_required,"verification_email_sent":sent}
@router.get("/api/auth/verify")
def verify_email(token:str)->dict[str,str]:
    if not verify_email_token(token): raise HTTPException(400,"Verification link is invalid or expired.")
    audit("email_verified"); return {"message":"Email verified. You can now sign in to FloodAI."}
@router.post("/api/auth/login")
def login(payload:LoginRequest,request:Request,response:Response)->dict[str,Any]:
    client_ip=request.client.host if request.client else "unknown"
    attempt_key=hashlib.sha256(f"{payload.email.strip().lower()}|{client_ip}".encode()).hexdigest()
    if login_is_locked(attempt_key):
        audit("login_throttled",target=payload.email.strip().lower(),outcome="blocked")
        raise HTTPException(429,"Too many failed sign-in attempts. Try again in 15 minutes.")
    user=authenticate(payload.email,payload.password)
    if not user:
        record_login_failure(attempt_key)
        audit("login_failed",target=payload.email.strip().lower(),outcome="failure")
        raise HTTPException(401,"Invalid credentials, unverified email, or inactive account.")
    clear_login_failures(attempt_key)
    token,expires=create_session(user["id"]); secure=os.getenv("FLOODAI_COOKIE_SECURE","false").lower() in {"1","true","yes"}
    response.set_cookie(SESSION_COOKIE,token,max_age=60*60*12,httponly=True,secure=secure,samesite="strict",path="/")
    audit("login_success",actor=user); return {"user":user,"expires_at":expires}
@router.post("/api/auth/logout")
def logout(request:Request,response:Response)->dict[str,str]:
    user=get_user_from_request(request); revoke_session(request)
    response.delete_cookie(SESSION_COOKIE,path="/",httponly=True,samesite="strict")
    if user: audit("logout",actor=user)
    return {"message":"Signed out."}
@router.get("/api/auth/me")
def me(user:dict[str,Any]=Depends(require_user))->dict[str,Any]: return {"user":user}
@router.patch("/api/auth/notifications")
def update_notifications(payload:NotificationPreference,user:dict[str,Any]=Depends(require_user))->dict[str,Any]:
    if user["role"]!="user": raise HTTPException(403,"Notification preferences are for regular users.")
    set_alerts_enabled(user["id"],payload.enabled); audit("notification_preference_updated",actor=user,details=f"enabled={payload.enabled}")
    return {"alerts_enabled":payload.enabled}
@router.get("/api/admin/overview")
def admin_overview(admin:dict[str,Any]=Depends(require_admin))->dict[str,Any]:
    result=admin_snapshot(); audit("admin_view_overview",actor=admin); return result
@router.get("/api/admin/users")
def admin_users(admin:dict[str,Any]=Depends(require_admin))->dict[str,Any]:
    audit("admin_view_users",actor=admin); return {"users":list_users()}
@router.patch("/api/admin/users/{user_id}/status")
def admin_update_user(user_id:int,payload:UserStatusUpdate,admin:dict[str,Any]=Depends(require_admin))->dict[str,Any]:
    if not set_user_active(user_id,payload.active): raise HTTPException(404,"Regular user account not found.")
    audit("admin_user_status_changed",actor=admin,target=str(user_id),details=f"active={payload.active}")
    return {"user_id":user_id,"active":payload.active}
@router.get("/api/admin/backend")
def admin_backend(admin:dict[str,Any]=Depends(require_admin))->dict[str,Any]:
    with _connect() as db:
        verified=int(db.execute("SELECT COUNT(*) FROM users WHERE is_verified=1").fetchone()[0])
        unverified=int(db.execute("SELECT COUNT(*) FROM users WHERE is_verified=0").fetchone()[0])
    result={"application":"FloodAI","environment":os.getenv("FLOODAI_ENV","development"),"auth_database":"sqlite",
      "registered_verified_accounts":verified,"registered_unverified_accounts":unverified,
      "smtp_configured":bool(os.getenv("FLOODAI_SMTP_USER") and os.getenv("FLOODAI_SMTP_APP_PASSWORD")),
      "admin_bootstrap_configured":bool(os.getenv("FLOODAI_ADMIN_EMAIL") and os.getenv("FLOODAI_ADMIN_PASSWORD")),
      "notes":["Channel prediction, DRL, RIS-CNOMA and orchestrator outputs remain software simulations.",
      "Flood status must remain NOT_ASSESSED unless verified official thresholds and fresh QC-passed gauge evidence are available.",
      "Secrets and password hashes are never returned by this endpoint."]}
    audit("admin_view_backend",actor=admin); return result



@router.get("/api/admin/alerts/status")
def admin_alert_status(admin:dict[str,Any]=Depends(require_admin))->dict[str,Any]:
    """Explain why real flood alerts are or are not currently eligible."""
    from services.alert_monitor import monitor_configuration, monitor_state
    from services.flood_state import _thresholds_verified
    from services.auth_service import get_verified_alert_recipients
    recipients=get_verified_alert_recipients()
    result={
      "monitor_enabled":monitor_configuration()["enabled"],
      "monitor_interval_seconds":monitor_configuration()["interval_seconds"],
      "smtp_configured":bool(os.getenv("FLOODAI_SMTP_USER") and os.getenv("FLOODAI_SMTP_APP_PASSWORD") and (os.getenv("FLOODAI_EMAIL_FROM") or os.getenv("FLOODAI_SMTP_USER"))),
      "verified_alert_recipients":len(recipients),
      "official_thresholds_verified":_thresholds_verified(),
      "automatic_real_alerts_possible":False,
      "reason":"Real alert emails remain disabled until verified official thresholds and fresh authoritative QC gauge evidence produce a complete WARNING/FLOOD/EMERGENCY assessment.",
      "monitor_last_run":monitor_state(),
    }
    audit("admin_view_alert_status",actor=admin)
    return result

@router.get("/api/admin/alerts/history")
def admin_alert_history(admin:dict[str,Any]=Depends(require_admin))->dict[str,Any]:
    """Recent alert dispatch records (official alerts and environmental indicator notices)."""
    audit("admin_view_alert_history",actor=admin)
    return {"dispatches":list_alert_dispatches(50)}


@router.post("/api/admin/email-test")
def admin_email_test(admin:dict[str,Any]=Depends(require_admin))->dict[str,Any]:
    """Send a clearly labelled SMTP test only to the signed-in admin."""
    recipient=validate_email(admin["email"])
    try:
        send_email(recipient,"FloodAI SMTP test (not a flood alert)",
                   "This is a FloodAI SMTP connectivity test requested from the Platform Admin dashboard. "
                   "It is not a flood warning. No flood event was detected by this test.")
    except Exception as exc:
        audit("admin_smtp_test",actor=admin,outcome="failure",details=type(exc).__name__)
        logger.exception("Admin SMTP test failed.")
        raise HTTPException(status_code=502,detail=f"SMTP test delivery failed: {type(exc).__name__}: {str(exc)[:200]}") from exc
    audit("admin_smtp_test",actor=admin,outcome="success",details="Test email sent to signed-in administrator")
    return {"sent":True,"recipient":recipient,"message":"SMTP test email accepted for delivery to the administrator account. This is not a flood alert."}

@router.post("/api/admin/pipeline")
def admin_run_pipeline(payload: AdminPipelineRequest, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    """Expose research/backend diagnostics only to the pre-provisioned platform admin."""
    from api import RunRequest, run_pipeline
    result = run_pipeline(RunRequest(**payload.model_dump()))
    audit("admin_pipeline_run", actor=admin, target=payload.region_id,
          details=f"seed={payload.seed}; learn={payload.learn}; outputs_are_simulated=true")
    return result
