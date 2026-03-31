#!/usr/bin/env python3
"""
Start the Telegram Stock Alert Bot.

    python run.py

The bot will:
  - Respond to commands from your Telegram chat
  - Send automatic price alerts when a stock drops >= 20% below its 52-week high
  - Push market news from Indian financial feeds
  - Send a pre-market briefing at 09:00 IST and a post-market digest at 16:00 IST
"""
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

os.makedirs("logs", exist_ok=True)

# Minimal logging — important messages only
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
# Silence noisy third-party libraries
for lib in ("httpx", "httpcore", "apscheduler", "telegram"):
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main() -> None:
    # Late imports so env is loaded first
    from bot import build_app, build_scheduler

    token   = os.getenv("BOT_TOKEN", "")
    chat_id = os.getenv("CHAT_ID", "")

    if not token:
        print(
            "\n❌  BOT_TOKEN is missing from .env\n"
            "   1. Open Telegram and message @BotFather\n"
            "   2. Send /newbot and follow the prompts\n"
            "   3. Copy the token and paste it into .env as:\n"
            "      BOT_TOKEN=123456789:ABCdefGHI...\n"
        )
        sys.exit(1)

    if not chat_id:
        print(
            "\n⚠️  CHAT_ID is not set — the bot will answer commands but\n"
            "   will NOT send automatic price/news push alerts.\n"
            "   To enable push alerts:\n"
            "   1. Message @userinfobot on Telegram\n"
            "   2. It will reply with your numeric chat ID\n"
            "   3. Add it to .env as:  CHAT_ID=123456789\n"
        )

    app       = build_app()
    scheduler = build_scheduler(app)

    async with app:
        scheduler.start()
        jobs = [j.id for j in scheduler.get_jobs()]
        logger.info("Scheduled jobs active: %s", jobs)

        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is polling. Press Ctrl+C to stop.")

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()

    logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
