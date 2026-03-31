#!/usr/bin/env python3
"""
Entry point for the Telegram Stock Alert Bot.

Usage:
    python run_alerts.py

Make sure .env contains:
    ALERT_BOT_TOKEN=<your telegram bot token>
    ALERT_CHAT_ID=<your telegram chat id>

Run in the background (Linux/Mac):
    nohup python run_alerts.py > logs/alerts.log 2>&1 &

Run as a Windows service / background task:
    pythonw run_alerts.py
"""
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# ── Logging setup ──────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logger.add("logs/alerts.log", rotation="10 MB", retention="30 days", level="INFO")
logging.basicConfig(level=logging.WARNING)   # silence noisy third-party libs

# ── Import after env is loaded ─────────────────────────────────────────────
from alerts.telegram_bot import build_application, register_scheduler


async def main() -> None:
    logger.info("Starting Telegram Stock Alert Bot…")

    # Validate token early
    token = os.getenv("ALERT_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error(
            "No bot token found. Set ALERT_BOT_TOKEN in your .env file.\n"
            "Get a token from @BotFather on Telegram."
        )
        sys.exit(1)

    chat_id = os.getenv("ALERT_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        logger.warning(
            "ALERT_CHAT_ID not set — the bot will respond to commands but "
            "WILL NOT send proactive price/news push alerts.\n"
            "Set ALERT_CHAT_ID in .env to enable scheduled alerts."
        )

    app       = build_application()
    scheduler = register_scheduler(app)

    async with app:
        scheduler.start()
        logger.info(
            "Bot is running. Scheduled jobs: %s",
            [job.name for job in scheduler.get_jobs()],
        )
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Polling started. Press Ctrl+C to stop.")

        # Keep running until interrupted
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown signal received.")
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()

    logger.info("Alert bot stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
