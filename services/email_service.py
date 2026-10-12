"""SMTP delivery for verification and eligible flood alerts."""
# ruff: noqa: E401, E701, E702
from __future__ import annotations
import os, smtplib
from email.message import EmailMessage
from urllib.parse import urlencode
def _settings():
    host=os.getenv("FLOODAI_SMTP_HOST","smtp.gmail.com"); port=int(os.getenv("FLOODAI_SMTP_PORT","587"))
    username=os.getenv("FLOODAI_SMTP_USER",""); password=os.getenv("FLOODAI_SMTP_APP_PASSWORD","").replace(" ","")
    sender=os.getenv("FLOODAI_EMAIL_FROM") or username
    if not username or not password or not sender: raise RuntimeError("Email is not configured. Set FLOODAI_SMTP_USER and FLOODAI_SMTP_APP_PASSWORD.")
    return host,port,username,password,sender
def send_email(recipient,subject,body):
    host,port,username,password,sender=_settings()
    msg=EmailMessage(); msg["From"]=sender; msg["To"]=recipient; msg["Subject"]=subject; msg.set_content(body)
    with smtplib.SMTP(host,port,timeout=15) as smtp:
        smtp.ehlo(); smtp.starttls(); smtp.ehlo(); smtp.login(username,password); smtp.send_message(msg)
def send_verification_email(recipient,token):
    base=os.getenv("FLOODAI_BASE_URL","http://localhost:8000").rstrip("/")
    link=f"{base}/api/auth/verify?{urlencode({'token':token})}"
    send_email(recipient,"Verify your FloodAI email","Welcome to FloodAI. Verify your email using this link within 24 hours. If you did not create this account, ignore this message.\n\n"+link+"\n")
def send_flood_alert(recipient,*,region,status,observed_at,source,message):
    body=(f"FloodAI verified alert for {region}\n\nStatus: {status}\nTime: {observed_at}\nSource: {source}\n\n"
    f"{message}\n\nFollow official local disaster-management instructions. Do not rely on this email as a substitute for emergency services.")
    send_email(recipient,f"FloodAI {status} alert — {region}",body)
