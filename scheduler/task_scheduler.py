"""
Task Scheduler – triggers the trading bot session at 9:00 AM IST
on every market working day.

Uses APScheduler with a cron trigger. The scheduler runs in the
foreground and the individual bots run as daemon threads.

Lifecycle per trading day:
  09:00  → authenticate Zerodha, initialise all bots
  09:15  → market opens, bots start scanning
  15:15  → bots forced to close all positions (square-off time)
  15:30  → bots stopped, daily summary logged & sent

The process itself keeps running (perpetually) so it wakes up
automatically next trading day without needing an external cron job.
"""
import signal
import sys
import threading
import time
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import (
    MARKET_CLOSE_TIME, SQUARE_OFF_TIME, BOT_START_TIME, TIMEZONE,
    MOMENTUM_BOT_SYMBOLS, RSI_BOT_SYMBOLS, VWAP_BOT_SYMBOLS,
)
from core.session_manager import get_kite
from core.order_manager import OrderManager
from core.risk_manager import get_risk_manager
from scheduler.market_calendar import is_market_open_today
from strategies.bot1_ema_crossover import EMACrossoverBot
from strategies.bot2_rsi_reversal import RSIReversalBot
from strategies.bot3_vwap_scalper import VWAPScalperBot
from utils.logger import setup_logger
from utils.notifier import notify_daily_summary

log = setup_logger("scheduler")

# Global state for the current trading session
_active_bots: list = []
_bot_threads: list = []
_session_date = None


def start_trading_session() -> None:
    """
    Called at BOT_START_TIME every market day.
    Authenticates, initialises all bots, and starts their run loops.
    """
    global _active_bots, _bot_threads, _session_date

    ist = pytz.timezone(TIMEZONE)
    today = datetime.now(ist).date()

    if not is_market_open_today(today):
        log.info(f"{today} is not a trading day – skipping session.")
        return

    if _session_date == today:
        log.warning("Session already running for today – ignoring duplicate trigger.")
        return

    _session_date = today
    log.info(f"=== Starting trading session for {today} ===")

    try:
        # Authenticate with Zerodha
        kite = get_kite()
        profile = kite.profile()
        log.info(f"Authenticated as: {profile['user_name']} ({profile['user_id']})")
    except Exception as e:
        log.critical(f"Authentication failed: {e} – session aborted.")
        return

    # Reset risk manager for the new day
    from core import risk_manager as rm_module
    rm_module._risk_manager = None   # Force fresh instance
    risk = get_risk_manager()
    log.info(f"Risk manager reset | Capital: ₹{risk.total_capital:.0f} | "
             f"Daily SL limit: ₹{risk.daily_loss_limit:.0f}")

    # Reconcile any existing positions (crash recovery)
    order_mgr = OrderManager(kite)
    existing = order_mgr.get_open_positions()
    if existing:
        log.warning(f"Found {len(existing)} pre-existing open positions on startup!")
        for p in existing:
            log.warning(f"  {p['tradingsymbol']} qty={p['quantity']} pnl={p['pnl']}")

    # Instantiate bots
    bot1 = EMACrossoverBot(kite, MOMENTUM_BOT_SYMBOLS)
    bot2 = RSIReversalBot(kite, RSI_BOT_SYMBOLS)
    bot3 = VWAPScalperBot(kite, VWAP_BOT_SYMBOLS)
    _active_bots = [bot1, bot2, bot3]

    # Start bot threads
    _bot_threads = [bot.start_in_thread() for bot in _active_bots]
    log.info(f"All {len(_active_bots)} bots started. Market opens at 09:15.")


def stop_trading_session() -> None:
    """
    Called at SQUARE_OFF_TIME.
    Signals all bots to stop and ensures all positions are closed.
    """
    global _active_bots, _bot_threads

    log.info("=== Square-off time reached – stopping all bots ===")

    for bot in _active_bots:
        bot.stop()

    # Give bots 30 seconds to gracefully close positions
    for t in _bot_threads:
        t.join(timeout=30)

    # Emergency square-off for anything still open
    try:
        kite = get_kite()
        order_mgr = OrderManager(kite)
        remaining = order_mgr.get_open_positions()
        if remaining:
            log.warning(f"{len(remaining)} positions still open – initiating emergency square-off.")
            order_mgr.emergency_square_off()
    except Exception as e:
        log.error(f"Emergency square-off error: {e}")

    # Daily summary
    risk = get_risk_manager()
    summary = risk.daily_summary()
    log.info(
        f"=== Daily Summary ===\n"
        f"  PnL       : ₹{summary['daily_pnl']:+.2f}\n"
        f"  Trades    : {summary['trade_count']}\n"
        f"  Capital   : ₹{summary['available_capital']:.2f} remaining\n"
        f"  Halted    : {summary['halted']}"
    )
    notify_daily_summary(
        summary["daily_pnl"],
        summary["trade_count"],
        summary["total_capital"] - summary["available_capital"],
    )

    _active_bots = []
    _bot_threads = []


def run_scheduler() -> None:
    """
    Entry point: starts APScheduler with cron jobs and blocks forever.
    Handles SIGINT/SIGTERM for clean shutdown.
    """
    scheduler = BackgroundScheduler(timezone=TIMEZONE)

    # Parse start time
    start_h, start_m = BOT_START_TIME.split(":")
    # Parse square-off time
    sq_h, sq_m = SQUARE_OFF_TIME.split(":")

    # Trigger at BOT_START_TIME Mon–Fri (market calendar check is inside the job)
    scheduler.add_job(
        start_trading_session,
        CronTrigger(day_of_week="mon-fri", hour=start_h, minute=start_m,
                    timezone=TIMEZONE),
        id="start_session",
        name="Start trading session",
        misfire_grace_time=300,   # Allow up to 5 min late start
    )

    # Trigger square-off Mon–Fri
    scheduler.add_job(
        stop_trading_session,
        CronTrigger(day_of_week="mon-fri", hour=sq_h, minute=sq_m,
                    timezone=TIMEZONE),
        id="stop_session",
        name="Square off and stop bots",
        misfire_grace_time=60,
    )

    scheduler.start()
    log.info(
        f"Scheduler running | Start: {BOT_START_TIME} | Square-off: {SQUARE_OFF_TIME} | "
        f"Timezone: {TIMEZONE}"
    )

    # Graceful shutdown on SIGINT / SIGTERM
    def _shutdown(signum, frame):
        log.info("Shutdown signal received. Stopping scheduler…")
        stop_trading_session()
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Keep the main thread alive
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        pass
