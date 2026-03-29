"""
Central configuration for the trading bot system.
All values are loaded from environment variables (.env file).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Zerodha credentials ──────────────────────────────────────────────────────
ZERODHA_API_KEY    = os.getenv("ZERODHA_API_KEY", "")
ZERODHA_API_SECRET = os.getenv("ZERODHA_API_SECRET", "")
ZERODHA_USER_ID    = os.getenv("ZERODHA_USER_ID", "")
ZERODHA_PASSWORD   = os.getenv("ZERODHA_PASSWORD", "")
ZERODHA_TOTP_SECRET= os.getenv("ZERODHA_TOTP_SECRET", "")

# ── Capital & Risk ───────────────────────────────────────────────────────────
TOTAL_CAPITAL          = float(os.getenv("TOTAL_CAPITAL", 5000))
STOP_LOSS_PCT          = float(os.getenv("STOP_LOSS_PCT", 5.0))   # 5% of capital
MAX_TRADE_CAPITAL_PCT  = float(os.getenv("MAX_TRADE_CAPITAL_PCT", 40))  # 40% per trade max
MAX_OPEN_POSITIONS     = int(os.getenv("MAX_OPEN_POSITIONS", 4))

# Derived
DAILY_LOSS_LIMIT = TOTAL_CAPITAL * (STOP_LOSS_PCT / 100)   # ₹250 for ₹5k capital

# ── Market timing (IST) ──────────────────────────────────────────────────────
MARKET_OPEN_TIME   = "09:15"   # NSE market open
MARKET_CLOSE_TIME  = "15:25"   # Stop new trades before closing
BOT_START_TIME     = "09:00"   # Bots initialise, fetch data, prepare
SQUARE_OFF_TIME    = "15:15"   # Force-close all positions before market close
TIMEZONE           = "Asia/Kolkata"

# ── Instruments watched by each bot ─────────────────────────────────────────
# NSE:SYMBOL  – highly liquid, low spread instruments suitable for ₹5k capital
MOMENTUM_BOT_SYMBOLS  = ["NSE:RELIANCE", "NSE:INFY", "NSE:TCS"]
RSI_BOT_SYMBOLS       = ["NSE:HDFCBANK", "NSE:ICICIBANK", "NSE:SBIN"]
VWAP_BOT_SYMBOLS      = ["NSE:NIFTY 50", "NSE:BANKNIFTY"]   # Indices via futures/ETF
MTC_BOT_SYMBOLS       = ["NSE:BAJFINANCE", "NSE:AXISBANK", "NSE:WIPRO"]  # Bot 4 – non-overlapping

# ── Strategy parameters ──────────────────────────────────────────────────────
# Bot 1 – EMA Crossover Momentum
EMA_FAST   = 9
EMA_SLOW   = 21
EMA_TREND  = 50

# Bot 2 – RSI Mean Reversion
RSI_PERIOD   = 14
RSI_OVERSOLD  = 35
RSI_OVERBOUGHT= 65

# Bot 3 – VWAP Scalping
VWAP_DEVIATION_PCT = 0.5   # Enter when price is 0.5% away from VWAP

# Bot 4 – Multi-Timeframe Confluence (MTC)
MTC_HTF_EMA_FAST     = 20         # 15m fast EMA for trend structure
MTC_HTF_EMA_SLOW     = 50         # 15m slow EMA for trend structure
MTC_RSI_LOW          = 50         # RSI lower bound (momentum zone entry)
MTC_RSI_HIGH         = 70         # RSI upper bound (not overbought)
MTC_VOLUME_MULTIPLIER = 1.5       # Volume must be 1.5× 20-bar rolling average
MTC_STOP_LOSS_ATR    = 1.5        # Hard stop loss at 1.5×ATR below entry
MTC_PARTIAL_EXIT_ATR = 1.0        # Stage-1 partial exit at 1×ATR profit
MTC_TARGET_ATR       = 2.5        # Stage-2 full target at 2.5×ATR

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR   = "logs"
LOG_LEVEL = "INFO"

# ── Telegram alerts (optional) ───────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
