"""
WhatsApp sender using Twilio API.
Supports two-way messaging (send alerts + receive user commands).
"""
import logging
import os
import time

from twilio.rest import Client

logger = logging.getLogger(__name__)


def _client():
    return Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN"),
    )


def send(message: str, to: str = None) -> bool:
    """Send a WhatsApp message. Returns True on success."""
    to   = to or os.getenv("WHATSAPP_TO", "")
    from_ = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not to:
        logger.error("WHATSAPP_TO not set in .env")
        return False

    # Ensure whatsapp: prefix
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    if not from_.startswith("whatsapp:"):
        from_ = f"whatsapp:{from_}"

    for attempt in (1, 2):
        try:
            msg = _client().messages.create(from_=from_, to=to, body=message)
            logger.info("WhatsApp sent (sid=%s)", msg.sid)
            return True
        except Exception as e:
            logger.warning("Twilio error attempt %d: %s", attempt, e)
            if attempt == 1:
                time.sleep(3)

    logger.error("Failed to send WhatsApp after 2 attempts")
    return False


def send_chunks(message: str, max_len: int = 1500) -> None:
    """Split long message into chunks and send each."""
    parts = [message[i:i + max_len] for i in range(0, len(message), max_len)]
    for i, part in enumerate(parts, 1):
        if len(parts) > 1:
            part = f"[{i}/{len(parts)}]\n{part}"
        send(part)
        if i < len(parts):
            time.sleep(2)
