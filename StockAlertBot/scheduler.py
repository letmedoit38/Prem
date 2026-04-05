"""
APScheduler jobs that run automatically:

  Mon-Fri IST
  ───────────
  09:00   Pre-market briefing
  09:15, 10:15, 11:15 ... 15:15   Hourly price check (market hours)
  Every 30 min (09:00-16:00)      News scan
  16:00   Post-market digest
"""
import logging
from datetime import datetime, time as dtime

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from news_monitor import fetch_news, format_news
from stock_monitor import fetch_snapshots, make_alert_messages, make_status_report
from watchlist_manager import get_all_symbols
from whatsapp import send, send_chunks

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def _in_market_hours() -> bool:
    now = datetime.now(IST).time()
    return dtime(9, 10) <= now <= dtime(15, 35)


# ── Jobs ───────────────────────────────────────────────────────────────────

def job_price_check() -> None:
    """Hourly price check — only fires if market is open."""
    if not _in_market_hours():
        return
    logger.info("Running hourly price check")
    snaps  = fetch_snapshots(get_all_symbols())
    alerts = make_alert_messages(snaps)
    ts     = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    if alerts:
        for msg in alerts:
            send(f"[Stock Alert Bot] {ts}\n\n{msg}")
    else:
        logger.info("Price check: no alerts triggered")


def job_news_check() -> None:
    """News scan every 30 minutes."""
    logger.info("Running news scan")
    sectors = list({v["sector"] for v in get_all_symbols().values()})
    items   = fetch_news(watched_sectors=sectors)
    for item in items:
        send(f"[Stock Alert Bot]\n\n{format_news(item)}")


def job_pre_market() -> None:
    """09:00 IST — pre-market briefing."""
    logger.info("Sending pre-market briefing")
    snaps  = fetch_snapshots(get_all_symbols())
    report = make_status_report(snaps)
    date   = datetime.now(IST).strftime("%d %b %Y")
    send_chunks(f"[Stock Alert Bot] Pre-Market Briefing — {date}\n\n{report}")


def job_post_market() -> None:
    """16:00 IST — post-market digest with any drop alerts."""
    logger.info("Sending post-market digest")
    snaps  = fetch_snapshots(get_all_symbols())
    report = make_status_report(snaps)
    alerts = make_alert_messages(snaps)
    date   = datetime.now(IST).strftime("%d %b %Y")
    body   = report
    if alerts:
        body += "\n\n=== DROP ALERTS ===\n\n" + "\n\n".join(alerts)
    send_chunks(f"[Stock Alert Bot] Post-Market Digest — {date}\n\n{body}")


# ── Scheduler factory ──────────────────────────────────────────────────────

def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=IST)

    # Pre-market briefing — 09:00
    scheduler.add_job(
        job_pre_market,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=IST),
        id="pre_market", replace_existing=True,
    )

    # Hourly price check — :15 past each hour, 09–15
    scheduler.add_job(
        job_price_check,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute=15, timezone=IST),
        id="price_check", replace_existing=True,
    )

    # News scan — every 30 min, Mon–Fri 09:00–16:00
    scheduler.add_job(
        job_news_check,
        CronTrigger(day_of_week="mon-fri", hour="9-16", minute="*/30", timezone=IST),
        id="news_check", replace_existing=True,
    )

    # Post-market digest — 16:00
    scheduler.add_job(
        job_post_market,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=IST),
        id="post_market", replace_existing=True,
    )

    return scheduler
