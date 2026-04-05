"""
WhatsApp sender via CallMeBot API.

One-time setup (do this ONCE from your phone):
  1. Save +34 644 21 84 22 as a contact ("CallMeBot")
  2. Send it this exact message on WhatsApp:
       I allow callmebot to send me messages
  3. You'll receive your API key back within seconds
  4. Put it in .env as  CALLMEBOT_APIKEY=your_key

Reference: https://www.callmebot.com/blog/free-api-whatsapp-messages/
"""
import logging
import os
import time
import urllib.parse

import requests

logger = logging.getLogger(__name__)

_URL = "https://api.callmebot.com/whatsapp.php"


def send(message: str) -> bool:
    """
    Send a plain-text WhatsApp message to the configured number.
    Returns True on success, False on failure.
    Retries once on transient errors.
    """
    phone  = os.getenv("WHATSAPP_PHONE", "")
    apikey = os.getenv("CALLMEBOT_APIKEY", "")

    if not phone or not apikey:
        logger.error("WHATSAPP_PHONE or CALLMEBOT_APIKEY not set in .env")
        return False

    params = {
        "phone":  phone,
        "text":   message,
        "apikey": apikey,
    }

    for attempt in (1, 2):
        try:
            resp = requests.get(_URL, params=params, timeout=15)
            if resp.status_code == 200:
                logger.info("WhatsApp sent (attempt %d)", attempt)
                return True
            logger.warning("CallMeBot HTTP %s: %s", resp.status_code, resp.text[:200])
        except requests.RequestException as e:
            logger.warning("CallMeBot request error (attempt %d): %s", attempt, e)
        if attempt == 1:
            time.sleep(3)

    logger.error("Failed to send WhatsApp message after 2 attempts")
    return False


def send_chunks(message: str, max_len: int = 1500) -> None:
    """Split long messages and send each chunk."""
    parts = [message[i:i + max_len] for i in range(0, len(message), max_len)]
    for i, part in enumerate(parts, 1):
        if len(parts) > 1:
            part = f"[{i}/{len(parts)}]\n{part}"
        send(part)
        if i < len(parts):
            time.sleep(2)   # avoid rate-limiting
