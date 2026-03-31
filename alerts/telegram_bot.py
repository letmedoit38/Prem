"""
Telegram Stock Alert Bot — main application.

Commands:
  /start       — welcome message & instructions
  /watchlist   — show current watchlist
  /add SYMBOL  — add a symbol (custom / small-cap)
  /remove SYM  — remove a custom symbol
  /check       — manually trigger a price check right now
  /news        — fetch latest important market news
  /status      — short summary of all watched prices
  /help        — command reference

Automated schedule (while bot is running):
  • Price check  — every 60 min during NSE market hours (09:15–15:30 IST)
  • News check   — every 30 min (all day)
  • Pre-market   — summary at 09:00 IST
  • Post-market  — daily digest at 16:00 IST
"""

import asyncio
import logging
import os
from datetime import datetime, time as dtime
from typing import Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from alerts.news_monitor import fetch_important_news, format_news_alert
from alerts.stock_monitor import (
    build_alert_messages,
    build_status_report,
    fetch_all_snapshots,
)
from alerts.watchlist_manager import (
    add_symbol,
    get_all_symbols,
    get_watchlist_summary,
    load_watchlist,
    remove_symbol,
)

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

# ── Helpers ────────────────────────────────────────────────────────────────

def _get_bot_token() -> str:
    token = os.getenv("ALERT_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise EnvironmentError(
            "ALERT_BOT_TOKEN (or TELEGRAM_BOT_TOKEN) is not set in .env"
        )
    return token


def _get_chat_id() -> Optional[str]:
    return os.getenv("ALERT_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or None


async def _send(bot: Bot, chat_id: str, text: str) -> None:
    """Send a markdown message, splitting if > 4096 chars."""
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        await bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )


def _is_market_hours() -> bool:
    now = datetime.now(IST).time()
    return dtime(9, 10) <= now <= dtime(15, 35)


# ── Scheduled jobs ─────────────────────────────────────────────────────────

async def job_price_check(bot: Bot, chat_id: str) -> None:
    """Run during market hours — alert if any stock crossed the 20% threshold."""
    if not _is_market_hours():
        return
    logger.info("Running scheduled price check…")
    snapshots = fetch_all_snapshots()
    alerts    = build_alert_messages(snapshots)
    if alerts:
        header = f"🔔 *Price Alerts — {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}*\n"
        for alert in alerts:
            await _send(bot, chat_id, header + "\n" + alert)
    else:
        logger.info("No price alerts triggered.")


async def job_news_check(bot: Bot, chat_id: str) -> None:
    """Fetch important news and push to Telegram."""
    logger.info("Running scheduled news check…")
    wl = load_watchlist()
    all_sectors = list({
        info["sector"]
        for info in {**wl["stocks"], **wl["etfs"], **wl["custom"]}.values()
    })
    items = fetch_important_news(watched_sectors=all_sectors)
    for item in items:
        await _send(bot, chat_id, format_news_alert(item))


async def job_pre_market_summary(bot: Bot, chat_id: str) -> None:
    """09:00 IST — morning briefing."""
    logger.info("Sending pre-market summary…")
    snapshots = fetch_all_snapshots()
    report    = build_status_report(snapshots)
    header    = f"🌅 *Pre-Market Briefing — {datetime.now(IST).strftime('%d %b %Y')}*\n\n"
    await _send(bot, chat_id, header + report)


async def job_post_market_digest(bot: Bot, chat_id: str) -> None:
    """16:00 IST — end-of-day digest."""
    logger.info("Sending post-market digest…")
    snapshots = fetch_all_snapshots()
    report    = build_status_report(snapshots)
    alerts    = build_alert_messages(snapshots)
    header    = f"📅 *Post-Market Digest — {datetime.now(IST).strftime('%d %b %Y')}*\n\n"
    body      = report
    if alerts:
        body += "\n\n" + "\n\n".join(alerts)
    await _send(bot, chat_id, header + body)


# ── Command handlers ───────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 *Stock Alert Bot*\n\n"
        "I watch 10 blue-chip stocks + 5 ETFs and alert you when:\n"
        "  • A price drops ≥ 20% below its 52-week high\n"
        "  • An important market or sector event occurs\n\n"
        "*Commands:*\n"
        "`/watchlist`  — view all watched symbols\n"
        "`/add SYMBOL` — add a stock/ETF (e.g. `/add ZOMATO`)\n"
        "`/remove SYM` — remove a custom symbol\n"
        "`/check`      — run price check now\n"
        "`/news`       — fetch latest market news\n"
        "`/status`     — quick price snapshot\n"
        "`/help`       — this message"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        get_watchlist_summary(),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: `/add SYMBOL` or `/add SYMBOL Name Sector`\n"
            "Example: `/add ZOMATO Zomato Internet`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = context.args[0].upper()
    name   = " ".join(context.args[1:-1]) if len(context.args) > 2 else ""
    sector = context.args[-1] if len(context.args) >= 2 else "Custom"

    added = add_symbol(ticker, name=name, sector=sector)
    if added:
        await update.message.reply_text(
            f"✅ Added `{ticker}` to watchlist.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            f"ℹ️ `{ticker}` is already in the watchlist.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: `/remove SYMBOL`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ticker = context.args[0].upper()
    removed = remove_symbol(ticker)
    if removed:
        await update.message.reply_text(
            f"🗑️ Removed `{ticker}` from watchlist.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            f"⚠️ `{ticker}` is either a default symbol (cannot remove) "
            f"or not in the watchlist.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔍 Checking prices…")
    snapshots = fetch_all_snapshots()
    alerts    = build_alert_messages(snapshots)
    if alerts:
        for alert in alerts:
            await update.message.reply_text(alert, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(
            "✅ No alerts at this time. All stocks are within normal range."
        )


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📰 Fetching latest market news…")
    wl = load_watchlist()
    all_sectors = list({
        info["sector"]
        for info in {**wl["stocks"], **wl["etfs"], **wl["custom"]}.values()
    })
    items = fetch_important_news(watched_sectors=all_sectors, max_per_feed=5)
    if items:
        for item in items[:5]:   # cap at 5 to avoid flood
            await update.message.reply_text(
                format_news_alert(item),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
    else:
        await update.message.reply_text(
            "ℹ️ No new important news found at this time."
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📊 Fetching prices…")
    snapshots = fetch_all_snapshots()
    report    = build_status_report(snapshots)
    await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)


# ── Application factory ────────────────────────────────────────────────────

def build_application() -> Application:
    token = _get_bot_token()
    app   = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("add",       cmd_add))
    app.add_handler(CommandHandler("remove",    cmd_remove))
    app.add_handler(CommandHandler("check",     cmd_check))
    app.add_handler(CommandHandler("news",      cmd_news))
    app.add_handler(CommandHandler("status",    cmd_status))

    return app


def register_scheduler(app: Application) -> AsyncIOScheduler:
    """
    Register all scheduled jobs and attach the scheduler to the app lifecycle.
    Jobs fire in IST timezone.
    """
    scheduler = AsyncIOScheduler(timezone=IST)
    chat_id   = _get_chat_id()

    if not chat_id:
        logger.warning(
            "ALERT_CHAT_ID / TELEGRAM_CHAT_ID not set — "
            "scheduled push alerts are disabled. Bot will still respond to commands."
        )
        return scheduler

    bot = app.bot

    # Price check every 60 min on weekdays, 09:15–15:30 IST
    scheduler.add_job(
        job_price_check,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute="15", timezone=IST),
        args=[bot, chat_id],
        id="price_check",
        name="Hourly price check",
    )

    # News check every 30 min on weekdays
    scheduler.add_job(
        job_news_check,
        CronTrigger(day_of_week="mon-fri", minute="*/30", timezone=IST),
        args=[bot, chat_id],
        id="news_check",
        name="30-min news check",
    )

    # Pre-market summary — 09:00 IST weekdays
    scheduler.add_job(
        job_pre_market_summary,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=IST),
        args=[bot, chat_id],
        id="pre_market",
        name="Pre-market summary",
    )

    # Post-market digest — 16:00 IST weekdays
    scheduler.add_job(
        job_post_market_digest,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=IST),
        args=[bot, chat_id],
        id="post_market",
        name="Post-market digest",
    )

    return scheduler
