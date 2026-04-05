"""
Background scheduler for automatic WhatsApp alerts.

Jobs (Mon-Fri IST):
  09:00              Pre-market briefing
  09:15, 10:15 ...   Hourly price check (fires alerts if drop >= 20%)
  Every 30 min       News scan
  16:00              Post-market digest
"""
import logging
from datetime import datetime, time as dtime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def _in_market_hours() -> bool:
    now = datetime.now(IST).time()
    return dtime(9, 10) <= now <= dtime(15, 35)


# ── Jobs ───────────────────────────────────────────────────────────────────

def job_price_check() -> None:
    if not _in_market_hours():
        return
    logger.info("Running hourly price check")
    from stock_monitor import fetch_snapshots, make_alert_messages
    from watchlist_manager import get_all_symbols
    from whatsapp import send

    snaps  = fetch_snapshots(get_all_symbols())
    alerts = make_alert_messages(snaps)
    ts     = datetime.now(IST).strftime("%d %b %Y %H:%M IST")
    for msg in alerts:
        send(f"[Price Alert] {ts}\n\n{msg}\n\nReply 1/2/3 for options.")


def job_news_check() -> None:
    logger.info("Running news scan")
    from news_monitor import fetch_news, format_news
    from watchlist_manager import get_all_symbols
    from whatsapp import send

    sectors = list({v["sector"] for v in get_all_symbols().values()})
    for item in fetch_news(watched_sectors=sectors):
        send(f"{format_news(item)}\n\nReply 1/2/3 for options.")


def job_pre_market() -> None:
    logger.info("Sending pre-market briefing")
    from stock_monitor import fetch_snapshots, make_status_report
    from watchlist_manager import get_all_symbols
    from whatsapp import send_chunks

    snaps  = fetch_snapshots(get_all_symbols())
    report = make_status_report(snaps)
    date   = datetime.now(IST).strftime("%d %b %Y")
    send_chunks(
        f"Good morning! Pre-Market Briefing - {date}\n\n{report}\n\n"
        "Reply 1/2/3 for options."
    )


def job_post_market() -> None:
    logger.info("Sending post-market digest")
    from stock_monitor import fetch_snapshots, make_status_report, make_alert_messages
    from watchlist_manager import get_all_symbols
    from whatsapp import send_chunks

    snaps  = fetch_snapshots(get_all_symbols())
    report = make_status_report(snaps)
    alerts = make_alert_messages(snaps)
    date   = datetime.now(IST).strftime("%d %b %Y")
    body   = report
    if alerts:
        body += "\n\n=== DROP ALERTS ===\n\n" + "\n\n".join(alerts)
    send_chunks(
        f"Post-Market Digest - {date}\n\n{body}\n\n"
        "Reply 1/2/3 for options."
    )


# ── Factory ────────────────────────────────────────────────────────────────

def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=IST)

    scheduler.add_job(
        job_pre_market,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=0, timezone=IST),
        id="pre_market", replace_existing=True,
    )
    scheduler.add_job(
        job_price_check,
        CronTrigger(day_of_week="mon-fri", hour="9-15", minute=15, timezone=IST),
        id="price_check", replace_existing=True,
    )
    scheduler.add_job(
        job_news_check,
        CronTrigger(day_of_week="mon-fri", hour="9-16", minute="*/30", timezone=IST),
        id="news_check", replace_existing=True,
    )
    scheduler.add_job(
        job_post_market,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=0, timezone=IST),
        id="post_market", replace_existing=True,
    )

    return scheduler
