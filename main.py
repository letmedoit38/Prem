#!/usr/bin/env python3
"""
Prem Trading Bot – Entry Point.

Usage:
    python main.py              # Run scheduler (auto-starts at 9 AM on market days)
    python main.py --now        # Start a trading session immediately (for testing)
    python main.py --check      # Just validate credentials and show account info
    python main.py --squareoff  # Emergency: close all open positions now
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Prem Automated Trading Bot")
    parser.add_argument("--now",      action="store_true",
                        help="Start a trading session immediately (bypass scheduler)")
    parser.add_argument("--check",    action="store_true",
                        help="Validate Zerodha credentials and print account info")
    parser.add_argument("--squareoff", action="store_true",
                        help="Emergency: close all open MIS positions now")
    args = parser.parse_args()

    if args.check:
        _check_credentials()
    elif args.squareoff:
        _emergency_squareoff()
    elif args.now:
        _run_now()
    else:
        _run_scheduler()


def _check_credentials():
    from core.session_manager import get_kite
    from utils.logger import setup_logger
    log = setup_logger("main")
    log.info("Validating Zerodha credentials…")
    try:
        kite = get_kite()
        profile = kite.profile()
        funds = kite.margins()
        log.info(f"User    : {profile['user_name']} ({profile['user_id']})")
        log.info(f"Email   : {profile['email']}")
        equity  = funds.get("equity", {})
        log.info(f"Equity  : Net ₹{equity.get('net', 0):.2f} | "
                 f"Available ₹{equity.get('available', {}).get('live_balance', 0):.2f}")
        print("\n✓ Credentials valid. Account connected successfully.")
    except Exception as e:
        print(f"\n✗ Authentication failed: {e}")
        sys.exit(1)


def _emergency_squareoff():
    from core.session_manager import get_kite
    from core.order_manager import OrderManager
    from utils.logger import setup_logger
    log = setup_logger("main")
    log.warning("MANUAL EMERGENCY SQUARE-OFF requested.")
    kite = get_kite()
    order_mgr = OrderManager(kite)
    order_mgr.emergency_square_off()


def _run_now():
    """Start session immediately – useful for testing during market hours."""
    from scheduler.task_scheduler import start_trading_session, stop_trading_session
    from utils.logger import setup_logger
    import time, signal, sys
    log = setup_logger("main")
    log.info("Starting immediate trading session (--now mode)…")
    start_trading_session()

    def _stop(signum, frame):
        log.info("Interrupt received – stopping session.")
        stop_trading_session()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    log.info("Bots running. Press Ctrl+C to stop and square off.")
    try:
        while True:
            time.sleep(30)
    except (KeyboardInterrupt, SystemExit):
        stop_trading_session()


def _run_scheduler():
    from scheduler.task_scheduler import run_scheduler
    print(
        "\n"
        "╔══════════════════════════════════════════╗\n"
        "║       PREM AUTOMATED TRADING BOT         ║\n"
        "║  Capital: ₹5,000 | Stop Loss: 5%        ║\n"
        "║  Bots: EMA Crossover | RSI | VWAP        ║\n"
        "╚══════════════════════════════════════════╝\n"
    )
    run_scheduler()


if __name__ == "__main__":
    main()
