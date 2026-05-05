"""
Alert sender — email (SMTP) + optional WhatsApp (Twilio).
Called by main.py after each pipeline run.
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

import pandas as pd

import config

logger = logging.getLogger(__name__)


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email_alert(summary: dict) -> bool:
    """
    Send an email summary after each pipeline run.
    summary keys: mca_count, msme_count, gem_count, top5 (list of dicts),
                  total_leads, run_time
    """
    sender   = os.getenv("ALERT_EMAIL_SENDER", "")
    password = os.getenv("ALERT_EMAIL_PASSWORD", "")
    recipient = os.getenv("ALERT_EMAIL_RECIPIENT", "")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not all([sender, password, recipient]):
        logger.warning(
            "Email alert skipped — set ALERT_EMAIL_SENDER, "
            "ALERT_EMAIL_PASSWORD, ALERT_EMAIL_RECIPIENT in .env"
        )
        return False

    mca_count  = summary.get("mca_count", 0)
    msme_count = summary.get("msme_count", 0)
    gem_count  = summary.get("gem_count", 0)
    top5       = summary.get("top5", [])
    total      = summary.get("total_leads", 0)
    run_time   = summary.get("run_time", "N/A")
    date_str   = datetime.now().strftime("%d-%b-%Y %I:%M %p")

    top5_lines = "\n".join(
        f"  {i+1}. {r.get('COMPANY_NAME','N/A')[:40]} | "
        f"{r.get('DISTRICT','N/A')} | Score: {r.get('SCORE', 0)}"
        for i, r in enumerate(top5)
    ) or "  (no data)"

    body = f"""\
Dear Sir/Madam,

Indian Overseas Bank — Nagapattinam RO Lead Generation Pipeline
Daily Sync Report  |  {date_str}
{'─'*60}

Today's sync results:
  • New MCA Companies   : {mca_count}
  • New Udyam MSMEs     : {msme_count}
  • New GeM Sellers     : {gem_count}
  • Total Master Leads  : {total}
  • Pipeline run time   : {run_time}

TOP 5 LEADS TODAY:
{'─'*60}
{top5_lines}

Please open the Google Sheet for full details:
  Sheet: Nagapattinam RO - Live Leads

{'─'*60}
This is an automated message from the IOB Lead Generation System.
"""

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = (
        f"IOB Nagapattinam RO — Daily Lead Sync: "
        f"{mca_count} MCA + {msme_count} MSME + {gem_count} GeM  [{date_str}]"
    )
    msg.attach(MIMEText(body, "plain"))

    # Attach master_leads.csv if it exists
    if os.path.exists(config.MASTER_LEADS_CSV_OUT):
        with open(config.MASTER_LEADS_CSV_OUT, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="master_leads_{datetime.now().strftime("%Y%m%d")}.csv"',
        )
        msg.attach(part)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"  [Email] Alert sent to {recipient}")
        return True
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False


# ── WhatsApp (Twilio) ─────────────────────────────────────────────────────────

def send_whatsapp_alert(summary: dict) -> bool:
    """Send a WhatsApp summary using Twilio (optional)."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_wa     = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    to_wa       = os.getenv("ALERT_WHATSAPP_TO", "")

    if not all([account_sid, auth_token, to_wa]):
        logger.info("WhatsApp alert skipped — Twilio credentials not set in .env")
        return False

    try:
        from twilio.rest import Client
    except ImportError:
        logger.warning("twilio package not installed. Run: pip install twilio")
        return False

    mca_count  = summary.get("mca_count", 0)
    msme_count = summary.get("msme_count", 0)
    gem_count  = summary.get("gem_count", 0)
    top5       = summary.get("top5", [])
    date_str   = datetime.now().strftime("%d-%b-%Y")

    top5_text = "\n".join(
        f"  {i+1}. {r.get('COMPANY_NAME','N/A')[:30]} ({r.get('SCORE',0)}/100)"
        for i, r in enumerate(top5)
    ) or "  None"

    message_body = (
        f"*IOB Nagapattinam RO — Daily Lead Sync* ({date_str})\n\n"
        f"Today's sync:\n"
        f"  MCA Companies : {mca_count}\n"
        f"  Udyam MSMEs   : {msme_count}\n"
        f"  GeM Sellers   : {gem_count}\n\n"
        f"*Top 5 Leads:*\n{top5_text}\n\n"
        f"Check Google Sheet for full report."
    )

    try:
        client = Client(account_sid, auth_token)
        client.messages.create(body=message_body, from_=from_wa, to=to_wa)
        print(f"  [WhatsApp] Alert sent to {to_wa}")
        return True
    except Exception as exc:
        logger.error("WhatsApp send failed: %s", exc)
        return False


# ── Unified dispatcher ────────────────────────────────────────────────────────

def send_alerts(summary: dict) -> None:
    """Send both email and WhatsApp alerts."""
    print("\n[Alerts] Sending notifications …")
    send_email_alert(summary)
    send_whatsapp_alert(summary)
