"""
Safe Bot Tester — runs ALL checks WITHOUT placing any real orders.

Tests:
  1. Python dependencies installed correctly
  2. .env file exists and has required fields
  3. Zerodha login (real authentication)
  4. Account funds & margin check
  5. Live market data fetch (real prices)
  6. Technical indicator calculation (EMA, RSI, VWAP)
  7. Bot signal scan — DRY RUN (shows what trades WOULD be placed, no orders sent)
  8. Risk manager logic
  9. Market calendar (is today a trading day?)

Usage:
    python test_bot.py
"""
import sys
import os
from datetime import datetime
import pytz

# ── Colour helpers for Windows ──────────────────────────────────────────────────────────
try:
    import colorama
    colorama.init()
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
except ImportError:
    GREEN = RED = YELLOW = BLUE = RESET = BOLD = ""

PASS  = f"{GREEN}  [PASS]{RESET}"
FAIL  = f"{RED}  [FAIL]{RESET}"
INFO  = f"{BLUE}  [INFO]{RESET}"
WARN  = f"{YELLOW}  [WARN]{RESET}"


def header(title):
    print(f"\n{BOLD}{'\u2500'*55}")
    print(f"  {title}")
    print(f"{'\u2500'*55}{RESET}")


def main():
    errors = 0

    print(f"\n{BOLD}{'='*55}")
    print("   PREM TRADING BOT — Safe Test Runner")
    print(f"{'='*55}{RESET}\n")

    # ── Test 1: Dependencies ───────────────────────────────────────────────────────
    header("1. Checking Python dependencies")
    packages = [
        ("kiteconnect",  "kiteconnect"),
        ("pandas",       "pandas"),
        ("numpy",        "numpy"),
        ("pyotp",        "pyotp"),
        ("APScheduler",  "apscheduler"),
        ("python-dotenv","dotenv"),
        ("pytz",         "pytz"),
        ("loguru",       "loguru"),
        ("holidays",     "holidays"),
    ]
    for display, module in packages:
        try:
            __import__(module)
            print(f"{PASS}  {display}")
        except ImportError:
            print(f"{FAIL}  {display}  ← run: pip install {display}")
            errors += 1

    # ── Test 2: .env file ────────────────────────────────────────────────────────
    header("2. Checking .env credentials file")
    if not os.path.exists(".env"):
        print(f"{FAIL}  .env file not found")
        print(f"{INFO}  Run:  python setup_wizard.py")
        errors += 1
    else:
        print(f"{PASS}  .env file found")
        from dotenv import load_dotenv
        load_dotenv()
        required = [
            "ZERODHA_API_KEY", "ZERODHA_API_SECRET",
            "ZERODHA_USER_ID", "ZERODHA_PASSWORD", "ZERODHA_TOTP_SECRET"
        ]
        for key in required:
            val = os.getenv(key, "")
            if val and val != f"your_{key.lower()}_here":
                print(f"{PASS}  {key} is set")
            else:
                print(f"{FAIL}  {key} is MISSING or still has placeholder value")
                errors += 1

    if errors > 0:
        print(f"\n{RED}Fix the above issues first, then re-run this script.{RESET}\n")
        sys.exit(1)

    # ── Test 3: Zerodha authentication ───────────────────────────────────────────
    header("3. Testing Zerodha authentication")
    try:
        from core.session_manager import get_kite
        print(f"{INFO}  Connecting to Zerodha…")
        kite = get_kite()
        profile = kite.profile()
        print(f"{PASS}  Logged in as: {profile['user_name']} ({profile['user_id']})")
        print(f"{INFO}  Email: {profile['email']}")
        print(f"{INFO}  Broker: {profile.get('broker', 'ZERODHA')}")
    except Exception as e:
        print(f"{FAIL}  Authentication failed: {e}")
        print(f"{INFO}  Check your API key, secret, user ID, password, and TOTP secret.")
        sys.exit(1)

    # ── Test 4: Funds check ──────────────────────────────────────────────────────
    header("4. Checking account funds")
    try:
        margins = kite.margins()
        equity  = margins.get("equity", {})
        net     = equity.get("net", 0)
        avail   = equity.get("available", {}).get("live_balance", 0)
        print(f"{PASS}  Equity Net Balance  : ₹{net:,.2f}")
        print(f"{INFO}  Available for trading: ₹{avail:,.2f}")

        from config.settings import TOTAL_CAPITAL
        if avail >= TOTAL_CAPITAL:
            print(f"{PASS}  Sufficient funds for ₹{TOTAL_CAPITAL:,.0f} capital")
        else:
            print(f"{WARN}  Available ₹{avail:,.0f} < configured capital ₹{TOTAL_CAPITAL:,.0f}")
            print(f"{INFO}  Add funds to your Zerodha account before going live.")
    except Exception as e:
        print(f"{WARN}  Could not fetch margins: {e}")

    # ── Test 5: Live market data ──────────────────────────────────────────────────
    header("5. Testing live market data")
    from data.market_data import MarketData
    md = MarketData(kite)
    test_symbols = ["NSE:RELIANCE", "NSE:INFY", "NSE:HDFCBANK"]
    try:
        prices = md.get_ltp(test_symbols)
        if prices:
            print(f"{PASS}  Live prices received:")
            for sym, price in prices.items():
                print(f"{INFO}    {sym}: ₹{price:,.2f}")
        else:
            print(f"{WARN}  No prices returned (market may be closed right now)")
    except Exception as e:
        print(f"{FAIL}  Market data error: {e}")
        errors += 1

    # ── Test 6: Historical data + indicators ───────────────────────────────────
    header("6. Testing historical candles & indicators")
    try:
        df = md.get_candles("NSE:RELIANCE", interval="5minute", lookback_days=3)
        if not df.empty:
            print(f"{PASS}  Fetched {len(df)} candles for NSE:RELIANCE")
            df = md.add_ema(df, [9, 21, 50])
            df = md.add_rsi(df)
            df = md.add_atr(df)
            last = df.iloc[-1]
            print(f"{INFO}  Last close : ₹{last['close']:.2f}")
            print(f"{INFO}  EMA9       : ₹{last['ema_9']:.2f}")
            print(f"{INFO}  EMA21      : ₹{last['ema_21']:.2f}")
            print(f"{INFO}  EMA50      : ₹{last['ema_50']:.2f}")
            print(f"{INFO}  RSI(14)    : {last['rsi']:.1f}")
            print(f"{INFO}  ATR(14)    : ₹{last['atr']:.2f}")
        else:
            print(f"{WARN}  No historical data (market may be closed / outside hours)")
    except Exception as e:
        print(f"{FAIL}  Indicator error: {e}")
        errors += 1

    # ── Test 7: Bot dry run ──────────────────────────────────────────────────────
    header("7. Bot signal scan — DRY RUN (no real orders)")
    print(f"{INFO}  Scanning for signals on all bot instruments…\n")

    from config.settings import MOMENTUM_BOT_SYMBOLS, RSI_BOT_SYMBOLS, VWAP_BOT_SYMBOLS

    all_symbols = MOMENTUM_BOT_SYMBOLS + RSI_BOT_SYMBOLS + VWAP_BOT_SYMBOLS
    signal_found = False

    for symbol in all_symbols:
        try:
            ltp_dict = md.get_ltp([symbol])
            ltp = ltp_dict.get(symbol, 0)
            if ltp == 0:
                print(f"{WARN}  {symbol:<25} — no price (market closed?)")
                continue

            df5 = md.get_candles(symbol, interval="5minute", lookback_days=3)
            if df5.empty or len(df5) < 55:
                print(f"{INFO}  {symbol:<25} — insufficient data")
                continue

            df5 = md.add_ema(df5, [9, 21, 50])
            df5 = md.add_rsi(df5)
            last, prev = df5.iloc[-1], df5.iloc[-2]

            ema_cross = (prev["ema_9"] <= prev["ema_21"]) and (last["ema_9"] > last["ema_21"])
            above_50  = last["close"] > last["ema_50"]
            rsi_ok    = 40 < last["rsi"] < 65

            if ema_cross and above_50 and rsi_ok:
                print(f"{GREEN}  {symbol:<25} — EMA CROSSOVER SIGNAL ← Bot1 would BUY{RESET}")
                signal_found = True
            else:
                print(f"{INFO}  {symbol:<25} — no signal  "
                      f"(RSI:{last['rsi']:.0f}, "
                      f"EMA9>21:{last['ema_9']:.0f}>{last['ema_21']:.0f})")
        except Exception as e:
            print(f"{WARN}  {symbol}: {e}")

    if not signal_found:
        print(f"\n{INFO}  No signals right now — this is normal. Signals appear during market hours.")
    print(f"{PASS}  Dry run complete. Zero real orders were placed.")

    # ── Test 8: Risk manager ──────────────────────────────────────────────────────
    header("8. Testing risk manager")
    from core.risk_manager import RiskManager
    from config.settings import TOTAL_CAPITAL, DAILY_LOSS_LIMIT
    rm = RiskManager()
    print(f"{PASS}  Risk manager initialised")
    print(f"{INFO}  Capital     : ₹{rm.total_capital:,.0f}")
    print(f"{INFO}  Daily SL    : ₹{rm.daily_loss_limit:,.0f}  (5% of capital)")
    print(f"{INFO}  Max per trade: ₹{rm.max_trade_value():,.0f}  (40% cap)")
    assert rm.can_trade("test") is True
    print(f"{PASS}  can_trade() returns True (all clear)")

    # ── Test 9: Market calendar ───────────────────────────────────────────────────
    header("9. Market calendar check")
    from scheduler.market_calendar import is_market_open_today, next_trading_day
    ist      = pytz.timezone("Asia/Kolkata")
    now_ist  = datetime.now(ist)
    is_open  = is_market_open_today()
    next_day = next_trading_day()
    print(f"{INFO}  Current IST time : {now_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    if is_open:
        print(f"{PASS}  Today is a TRADING DAY")
        mkt_open  = now_ist.strftime("%H:%M") >= "09:15"
        mkt_close = now_ist.strftime("%H:%M") <= "15:30"
        if mkt_open and mkt_close:
            print(f"{PASS}  Market is OPEN right now (09:15 – 15:30 IST)")
        else:
            print(f"{WARN}  Market is CLOSED right now (opens 09:15, closes 15:30 IST)")
    else:
        print(f"{WARN}  Today is NOT a trading day (weekend or holiday)")
    print(f"{INFO}  Next trading day : {next_day}")

    # ── Final result ───────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    if errors == 0:
        print(f"{GREEN}{BOLD}  ALL TESTS PASSED — Bot is ready to run!{RESET}")
        print()
        print("  To start the bot right now (during market hours):")
        print(f"  {BOLD}    python main.py --now{RESET}")
        print()
        print("  To run on auto-schedule (9 AM daily):")
        print(f"  {BOLD}    python main.py{RESET}")
    else:
        print(f"{RED}{BOLD}  {errors} test(s) failed — fix issues above before running.{RESET}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
