# Prem – Automated Intraday Trading Bot (Zerodha / NSE)

A fully automated intraday trading system for NSE India via Zerodha KiteConnect.
Starts at 9:00 AM on every market working day, runs 3 concurrent strategy bots,
enforces a hard 5% daily stop loss, and squares off all positions by 15:15 IST.

---

## Architecture

```
main.py                         ← Entry point (scheduler or immediate mode)
scheduler/
  task_scheduler.py             ← APScheduler: triggers at 9 AM Mon–Fri
  market_calendar.py            ← NSE holiday / weekend check
core/
  session_manager.py            ← Zerodha TOTP auto-login, token caching
  risk_manager.py               ← Capital tracking, 5% daily SL, position sizing
  order_manager.py              ← Order status, emergency square-off
data/
  market_data.py                ← OHLCV candles, LTP, technical indicators
strategies/
  base_strategy.py              ← Abstract base class for all bots
  bot1_ema_crossover.py         ← Bot 1: EMA 9/21/50 momentum
  bot2_rsi_reversal.py          ← Bot 2: RSI mean reversion
  bot3_vwap_scalper.py          ← Bot 3: VWAP deviation scalper
utils/
  logger.py                     ← Loguru rotating logs per bot
  notifier.py                   ← Telegram alerts (optional)
config/
  settings.py                   ← All configuration (loaded from .env)
```

---

## The 3 Bots

| Bot | Strategy | Candle | Instruments |
|-----|----------|--------|-------------|
| **Bot 1** EMA Crossover | Fast EMA (9) crosses above slow EMA (21) above 50 EMA trend filter. ATR-based SL & target with trailing stop. | 5m | RELIANCE, INFY, TCS |
| **Bot 2** RSI Reversal | RSI dips below 35 in an uptrend, waits for RSI to turn up, enters. Exits at RSI 65 or ATR-based target. | 15m | HDFCBANK, ICICIBANK, SBIN |
| **Bot 3** VWAP Scalper | Enters when price is 0.5%+ below VWAP with momentum returning and volume confirmation. Target = VWAP. Tight SL. | 1m | NIFTYBEES, BANKBEES (ETFs) |

---

## Risk Management

- **Starting capital**: ₹5,000
- **Daily stop loss**: 5% of capital = **₹250**. When hit, ALL bots halt immediately.
- **Per-trade risk**: 1% of capital (~₹50) — sized via ATR
- **Max capital per trade**: 40% of total capital
- **Max open positions**: 3 simultaneous
- **Force square-off**: 15:15 IST every day (market closes 15:30)

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get Zerodha API credentials
1. Log in to [kite.trade](https://kite.trade) → My Apps → Create App
2. Note your **API Key** and **API Secret**
3. Enable TOTP in your Zerodha account (Profile → Security → Enable TOTP)
4. Save the **Base32 TOTP secret** shown during setup

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your credentials
```

Required `.env` fields:
```
ZERODHA_API_KEY=xxxx
ZERODHA_API_SECRET=xxxx
ZERODHA_USER_ID=AB1234
ZERODHA_PASSWORD=yourpassword
ZERODHA_TOTP_SECRET=BASE32TOTPSECRET
TOTAL_CAPITAL=5000
```

### 4. Validate credentials
```bash
python main.py --check
```

---

## Running

### Auto-scheduler mode (recommended)
```bash
python main.py
```
The process runs 24/7. At 9:00 AM on every NSE trading day it authenticates,
starts all bots, and at 15:15 it squares everything off.

### Immediate mode (testing during market hours)
```bash
python main.py --now
```

### Emergency square-off
```bash
python main.py --squareoff
```

---

## Logs

All logs are written to `logs/`:
- `Bot1_EMA_Crossover_YYYY-MM-DD.log`
- `Bot2_RSI_Reversal_YYYY-MM-DD.log`
- `Bot3_VWAP_Scalper_YYYY-MM-DD.log`
- `combined_YYYY-MM-DD.log`
- `trade_audit.csv` — CSV audit trail of every trade

---

## Telegram Alerts (optional)

Add to `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```
You'll receive alerts on: trade entry/exit, stop loss hit, daily summary.

---

## Important Disclaimers

- This is an experimental system for paper/real trading with minimal capital.
- Past strategy performance does not guarantee future results.
- Ensure your Zerodha account has sufficient margin for MIS intraday orders.
- The TOTP auto-login stores credentials in `.env` — keep this file secure.
- Always monitor the first few sessions manually before leaving fully unattended.
