#!/usr/bin/env python3
"""
Stock Alert Bot — WhatsApp Edition
===================================
Runs a blocking scheduler that automatically sends WhatsApp alerts to
your number whenever a stock drops >= 20% below its 52-week high, or
when important market events occur.

    python run.py

Schedule (Mon-Fri, IST)
───────────────────────
  09:00              Pre-market briefing
  09:15, 10:15 ...   Hourly price check (market hours)
  Every 30 min       Market news scan
  16:00              Post-market digest
"""
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

os.makedirs("logs",  exist_ok=True)
os.makedirs("data",  exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
for lib in ("apscheduler", "yfinance", "urllib3", "peewee"):
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _check_env() -> bool:
    ok = True
    if not os.getenv("WHATSAPP_PHONE"):
        print("\n  ERROR: WHATSAPP_PHONE is not set in .env")
        ok = False
    if not os.getenv("CALLMEBOT_APIKEY"):
        print(
            "\n  ERROR: CALLMEBOT_APIKEY is not set in .env\n"
            "\n  One-time setup:"
            "\n    1. Save +34 644 21 84 22 as a contact on WhatsApp"
            "\n    2. Send:  I allow callmebot to send me messages"
            "\n    3. You will receive your API key via WhatsApp"
            "\n    4. Add it to .env as:  CALLMEBOT_APIKEY=xxxxxxxx\n"
        )
        ok = False
    return ok


def main() -> None:
    if not _check_env():
        sys.exit(1)

    from scheduler import build_scheduler
    from whatsapp import send

    scheduler = build_scheduler()
    jobs = [(j.id, str(j.next_run_time)) for j in scheduler.get_jobs()]

    logger.info("Stock Alert Bot starting — %d scheduled jobs", len(jobs))
    for jid, nxt in jobs:
        logger.info("  %-15s  next run: %s", jid, nxt)

    # Startup notification
    send(
        "Stock Alert Bot started!\n"
        "Watching 10 stocks + 5 ETFs on NSE.\n"
        "You will receive:\n"
        "  - Pre-market briefing at 09:00 IST\n"
        "  - Hourly price checks (market hours)\n"
        "  - News alerts every 30 min\n"
        "  - Post-market digest at 16:00 IST\n"
        "Price drop alert threshold: 20% below 52-week high"
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
