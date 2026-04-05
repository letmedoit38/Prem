"""
Main entry point for the Stock Alert Bot.

On startup:
  1. Validates .env credentials
  2. Opens an ngrok HTTPS tunnel so Twilio can reach this machine
  3. Registers the tunnel URL as the Twilio webhook
  4. Sends a startup WhatsApp message:
       "Alert Bot is working!" + top-10 prices + interactive menu
  5. Starts the APScheduler background jobs (price checks, news, digests)
  6. Starts Flask (blocking) to receive incoming WhatsApp replies

Interactive menu (user replies via WhatsApp):
  1  →  Current prices of top 10 stocks
  2  →  Enable 52-week low alerts
  3  →  View full watchlist (stocks + ETFs)
  Any other text → show menu again
"""
import logging
import os
import sys
import threading

from dotenv import load_dotenv
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()

os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
for lib in ("apscheduler", "yfinance", "urllib3", "werkzeug", "pyngrok"):
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ── State ──────────────────────────────────────────────────────────────────
low_alerts_enabled = False   # toggled by menu option 2

# ── Flask app ──────────────────────────────────────────────────────────────
app = Flask(__name__)

MENU_TEXT = (
    "What would you like to do?\n\n"
    "1 - Get current prices of top 10 stocks\n"
    "2 - Toggle 52-week low alerts (ON/OFF)\n"
    "3 - View full watchlist (stocks + ETFs)\n\n"
    "Reply with 1, 2, or 3"
)


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive incoming WhatsApp message from user and reply."""
    global low_alerts_enabled
    body = request.form.get("Body", "").strip()
    resp = MessagingResponse()
    msg  = resp.message()

    logger.info("Incoming WhatsApp: %r", body)

    if body == "1":
        from stock_monitor import fetch_snapshots, make_status_report
        from watchlist_manager import DEFAULT_STOCKS
        snaps  = fetch_snapshots(DEFAULT_STOCKS)
        report = make_status_report(snaps)
        msg.body(f"Top 10 Stock Prices\n\n{report}\n\nReply 1/2/3 for more options.")

    elif body == "2":
        low_alerts_enabled = not low_alerts_enabled
        state = "ENABLED" if low_alerts_enabled else "DISABLED"
        msg.body(
            f"52-week low alerts are now {state}.\n\n"
            f"{'You will be alerted when any top-10 stock falls within 5% of its 52-week low.' if low_alerts_enabled else 'No low-alerts will be sent.'}\n\n"
            "Reply 1/2/3 for more options."
        )

    elif body == "3":
        from watchlist_manager import get_watchlist_text
        msg.body(f"{get_watchlist_text()}\n\nReply 1/2/3 for more options.")

    else:
        msg.body(MENU_TEXT)

    return str(resp)


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


# ── Startup helpers ────────────────────────────────────────────────────────

def _check_env() -> bool:
    missing = []
    for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "WHATSAPP_TO"):
        if not os.getenv(key):
            missing.append(key)
    if missing:
        print(f"\n  ERROR: Missing in .env: {', '.join(missing)}")
        print("  Copy .env.example to .env and fill in the values.\n")
        return False
    return True


def _setup_ngrok(port: int) -> str:
    """Start ngrok tunnel and return the public HTTPS URL."""
    auth_token = os.getenv("NGROK_AUTH_TOKEN", "")
    from pyngrok import conf, ngrok
    if auth_token:
        conf.get_default().auth_token = auth_token
    tunnel    = ngrok.connect(port, "http")
    public_url = tunnel.public_url.replace("http://", "https://")
    logger.info("ngrok tunnel: %s", public_url)
    return public_url


def _register_twilio_webhook(webhook_url: str) -> None:
    """Update the Twilio WhatsApp sandbox incoming-message webhook."""
    sid    = os.getenv("TWILIO_ACCOUNT_SID")
    token  = os.getenv("TWILIO_AUTH_TOKEN")
    from_  = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    number = from_.replace("whatsapp:", "")

    try:
        client = Client(sid, token)
        # Find the phone number resource and update its webhook
        for pn in client.incoming_phone_numbers.list():
            if pn.phone_number == number:
                pn.update(sms_url=webhook_url)
                logger.info("Webhook registered on phone number %s", number)
                return
        # Sandbox numbers aren't in incoming_phone_numbers — update via sandbox
        # This works for the sandbox automatically via the Twilio console.
        logger.info("Webhook URL to paste in Twilio console: %s", webhook_url)
    except Exception as e:
        logger.warning("Could not auto-register webhook: %s", e)
        logger.info("Paste this URL in Twilio WhatsApp Sandbox settings: %s", webhook_url)


def _send_startup_message() -> None:
    """Send 'bot is working' + top 10 prices + menu."""
    from stock_monitor import fetch_snapshots, make_status_report
    from watchlist_manager import DEFAULT_STOCKS
    from whatsapp import send_chunks

    logger.info("Fetching startup prices...")
    snaps  = fetch_snapshots(DEFAULT_STOCKS)
    report = make_status_report(snaps)

    message = (
        "Stock Alert Bot is working!\n\n"
        "Top 10 NSE Stock Prices:\n"
        f"{report}\n\n"
        "-----------------------------\n"
        f"{MENU_TEXT}"
    )
    send_chunks(message)
    logger.info("Startup message sent.")


def _start_scheduler() -> None:
    """Launch APScheduler in a background thread."""
    from scheduler import build_scheduler
    scheduler = build_scheduler()
    scheduler.start()
    jobs = [j.id for j in scheduler.get_jobs()]
    logger.info("Scheduler started with jobs: %s", jobs)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    if not _check_env():
        sys.exit(1)

    port = int(os.getenv("FLASK_PORT", 5000))

    # 1. Start ngrok tunnel
    print("\n  Starting ngrok tunnel...")
    try:
        public_url   = _setup_ngrok(port)
        webhook_url  = f"{public_url}/webhook"
        print(f"  Webhook URL: {webhook_url}")
        print(f"  >>> Paste this in Twilio Console > Messaging > Sandbox Settings")
        print(f"  >>> under 'When a message comes in':  {webhook_url}\n")
        _register_twilio_webhook(webhook_url)
    except Exception as e:
        logger.error("ngrok failed: %s", e)
        print(
            "\n  WARNING: Could not start ngrok tunnel.\n"
            "  Two-way commands will not work.\n"
            "  Continuing with one-way alerts only...\n"
        )

    # 2. Start background scheduler
    _start_scheduler()

    # 3. Send startup WhatsApp message (in background so Flask starts fast)
    threading.Thread(target=_send_startup_message, daemon=True).start()

    # 4. Start Flask
    logger.info("Starting Flask on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
