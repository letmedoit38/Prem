"""
Telegram Stock Alert Bot.

Commands
────────
/start       — welcome + instructions
/watchlist   — show all watched symbols
/add SYMBOL [Name] [Sector]  — add a custom / small-cap stock
/remove SYM  — remove a custom symbol
/check       — run a price check right now
/news        — pull latest market news
/status      — live price snapshot for all symbols
/help        — command list

Automated schedule (IST, Mon–Fri)
──────────────────────────────────
 09:00  Pre-market briefing
 09:15–15:15  Hourly price check (only during market hours)
 Every 30 min  News scan
 16:00  Post-market digest
"""
import asyncio
import logging
import os
from datetime import datetime, time as dtime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from news_monitor import fetch_news, format_news
from stock_monitor import fetch_snapshots, make_alert_messages, make_status_report
from watchlist_manager import (
    add_symbol, get_all_symbols, get_watchlist_text,
    remove_symbol,
)

logger = logging.getLogger(__name__)
IST    = pytz.timezone("Asia/Kolkata")

MD = ParseMode.MARKDOWN_V2


# ── Helpers ────────────────────────────────────────────────────────────────

def _token() -> str:
    t = os.getenv("BOT_TOKEN", "")
    if not t:
        raise EnvironmentError("BOT_TOKEN not set in .env")
    return t


def _chat_id() -> str:
    return os.getenv("CHAT_ID", "")


def _in_market_hours() -> bool:
    now = datetime.now(IST).time()
    return dtime(9, 10) <= now <= dtime(15, 35)


async def _send(bot: Bot, chat_id: str, text: str) -> None:
    """Send MarkdownV2 message, split if > 4000 chars."""
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try:
            await bot.send_message(chat_id=chat_id, text=chunk,
                                   parse_mode=MD,
                                   disable_web_page_preview=True)
        except Exception as e:
            logger.error("send failed: %s", e)


# ── Scheduled jobs ─────────────────────────────────────────────────────────

async def job_price_check(bot: Bot, chat_id: str) -> None:
    if not _in_market_hours():
        return
    snaps  = fetch_snapshots(get_all_symbols())
    alerts = make_alert_messages(snaps)
    ts     = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    for a in alerts:
        await _send(bot, chat_id, f"🔔 *Price Alert* — {ts}\n\n" + a)


async def job_news_check(bot: Bot, chat_id: str) -> None:
    sectors = list({v["sector"] for v in get_all_symbols().values()})
    for item in fetch_news(watched_sectors=sectors):
        await _send(bot, chat_id, format_news(item))


async def job_pre_market(bot: Bot, chat_id: str) -> None:
    snaps  = fetch_snapshots(get_all_symbols())
    report = make_status_report(snaps)
    date   = datetime.now(IST).strftime("%d %b %Y")
    await _send(bot, chat_id, f"🌅 *Pre\\-Market Briefing — {date}*\n\n" + report)


async def job_post_market(bot: Bot, chat_id: str) -> None:
    snaps  = fetch_snapshots(get_all_symbols())
    report = make_status_report(snaps)
    alerts = make_alert_messages(snaps)
    date   = datetime.now(IST).strftime("%d %b %Y")
    body   = report + ("\n\n" + "\n\n".join(alerts) if alerts else "")
    await _send(bot, chat_id, f"📅 *Post\\-Market Digest — {date}*\n\n" + body)


# ── Command handlers ───────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Stock Alert Bot*\n\n"
        "I monitor 10 blue\\-chip NSE stocks \\+ 5 ETFs and alert you when:\n"
        "  • Price drops ≥ 20% below 52\\-week high\n"
        "  • An important market event occurs\n\n"
        "*Commands:*\n"
        "`/watchlist` — view all symbols\n"
        "`/add SYMBOL` — add custom/small\\-cap stock\n"
        "`/remove SYM` — remove a custom symbol\n"
        "`/check` — run price check now\n"
        "`/news` — latest market news\n"
        "`/status` — live price snapshot\n"
        "`/help` — this message",
        parse_mode=MD,
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_watchlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(get_watchlist_text(), parse_mode=MD)


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text(
            "Usage: `/add SYMBOL \\[Name\\] \\[Sector\\]`\n"
            "Example: `/add ZOMATO Zomato Internet`",
            parse_mode=MD,
        )
        return
    ticker = ctx.args[0]
    name   = ctx.args[1] if len(ctx.args) > 1 else ""
    sector = ctx.args[2] if len(ctx.args) > 2 else "Custom"
    ok, msg = add_symbol(ticker, name=name, sector=sector)
    icon    = "✅" if ok else "ℹ️"
    await update.message.reply_text(f"{icon} {msg}", parse_mode=MD)


async def cmd_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not ctx.args:
        await update.message.reply_text("Usage: `/remove SYMBOL`", parse_mode=MD)
        return
    ok, msg = remove_symbol(ctx.args[0])
    icon    = "🗑️" if ok else "⚠️"
    await update.message.reply_text(f"{icon} {msg}", parse_mode=MD)


async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔍 Checking prices…")
    snaps  = fetch_snapshots(get_all_symbols())
    alerts = make_alert_messages(snaps)
    if alerts:
        for a in alerts:
            await update.message.reply_text(a, parse_mode=MD)
    else:
        await update.message.reply_text(
            "✅ No alerts\\. All stocks are within normal range\\.", parse_mode=MD
        )


async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📰 Fetching news…")
    sectors = list({v["sector"] for v in get_all_symbols().values()})
    items   = fetch_news(watched_sectors=sectors, max_per_feed=5)
    if items:
        for item in items[:5]:
            await update.message.reply_text(
                format_news(item), parse_mode=MD, disable_web_page_preview=True
            )
    else:
        await update.message.reply_text(
            "ℹ️ No new important news at this time\\.", parse_mode=MD
        )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📊 Fetching prices…")
    snaps  = fetch_snapshots(get_all_symbols())
    report = make_status_report(snaps)
    await update.message.reply_text(report, parse_mode=MD)


# ── App factory ────────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(_token()).build()
    for cmd, fn in [
        ("start",     cmd_start),
        ("help",      cmd_help),
        ("watchlist", cmd_watchlist),
        ("add",       cmd_add),
        ("remove",    cmd_remove),
        ("check",     cmd_check),
        ("news",      cmd_news),
        ("status",    cmd_status),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    return app


def build_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=IST)
    chat_id   = _chat_id()

    if not chat_id:
        logger.warning(
            "CHAT_ID not set — scheduled push alerts disabled. "
            "Bot will still respond to commands."
        )
        return scheduler

    bot = app.bot

    # Hourly price check during market hours (Mon–Fri)
    scheduler.add_job(job_price_check, CronTrigger(
        day_of_week="mon-fri", hour="9-15", minute="15", timezone=IST),
        args=[bot, chat_id], id="price_check")

    # News every 30 min (Mon–Fri)
    scheduler.add_job(job_news_check, CronTrigger(
        day_of_week="mon-fri", minute="*/30", timezone=IST),
        args=[bot, chat_id], id="news_check")

    # Pre-market briefing at 09:00
    scheduler.add_job(job_pre_market, CronTrigger(
        day_of_week="mon-fri", hour=9, minute=0, timezone=IST),
        args=[bot, chat_id], id="pre_market")

    # Post-market digest at 16:00
    scheduler.add_job(job_post_market, CronTrigger(
        day_of_week="mon-fri", hour=16, minute=0, timezone=IST),
        args=[bot, chat_id], id="post_market")

    return scheduler
