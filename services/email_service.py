"""SMTP delivery for verification and eligible flood alerts."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


def _settings():
    host = os.getenv("FLOODAI_SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("FLOODAI_SMTP_PORT", "465"))
    username = os.getenv("FLOODAI_SMTP_USER", "").strip()
    password = os.getenv("FLOODAI_SMTP_APP_PASSWORD", "").replace(" ", "")
    sender = (os.getenv("FLOODAI_EMAIL_FROM") or username).strip()
    if not username or not password or not sender:
        raise RuntimeError(
            "Email is not configured. Set FLOODAI_SMTP_USER, "
            "FLOODAI_SMTP_APP_PASSWORD, and FLOODAI_EMAIL_FROM in .env."
        )
    if port not in (465, 587):
        raise RuntimeError("FLOODAI_SMTP_PORT must be 465 (SSL) or 587 (STARTTLS).")
    return host, port, username, password, sender


def send_email(recipient, subject, body):
    host, port, username, password, sender = _settings()
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()

    # Gmail supports implicit TLS on 465 and STARTTLS on 587. Do not silently
    # retry authentication with a second mode; surface the actual failure stage.
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=25, context=context) as smtp:
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=25) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)


def send_verification_email(recipient, token):
    base = os.getenv("FLOODAI_BASE_URL", "http://localhost:8000").rstrip("/")
    link = f"{base}/api/auth/verify?{urlencode({'token': token})}"
    body = (
        "Welcome to FloodAI. Verify your email using this link within 24 hours. "
        "If you did not create this account, ignore this message.\n\n"
        f"{link}\n"
    )
    send_email(recipient, "Verify your FloodAI email", body)


def send_flood_alert(recipient, *, region, status, observed_at, source, message):
    body = (
        f"FloodAI verified alert for {region}\n\n"
        f"Status: {status}\nTime: {observed_at}\nSource: {source}\n\n"
        f"{message}\n\n"
        "Follow official local disaster-management instructions. "
        "Do not rely on this email as a substitute for emergency services."
    )
    send_email(recipient, f"FloodAI {status} alert — {region}", body)


def send_environmental_indicator_email(
    recipient, *, region, level, observed_at, source, indicators
):
    """Send a clearly labelled advisory email, never an official flood warning."""
    body = (
        f"FloodAI environmental indicator notice for {region}\n\n"
        f"Indicator level: {level}\nObservation time: {observed_at}\n"
        f"Source: {source}\nIndicators: {indicators}\n\n"
        "This is an automated environmental indicator based on available live data, "
        "not an official flood warning or all-clear. Flood risk remains NOT_ASSESSED "
        "unless verified official station thresholds and fresh quality-controlled "
        "gauge evidence are available. Follow local disaster-management authorities "
        "for emergency instructions."
    )
    send_email(
        recipient, f"FloodAI {level} environmental indicator — {region}", body
    )
