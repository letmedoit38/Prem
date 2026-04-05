"""
Stock price monitor for the alert bot.

Checks each symbol in the watchlist against two alert conditions:
  1. Price has fallen >= 20% below its 52-week high  → buy-opportunity alert
  2. Price is within 5% of the 52-week low           → deep-value alert

Uses yfinance to fetch data (NSE symbols end with .NS).
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yfinance as yf

from alerts.watchlist_manager import get_all_symbols

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
DROP_FROM_52W_HIGH_PCT = 20.0   # alert when price is this % below 52-week high
NEAR_52W_LOW_PCT       = 5.0    # alert when within this % of 52-week low


@dataclass
class StockSnapshot:
    symbol: str
    name: str
    sector: str
    current_price: float
    high_52w: float
    low_52w: float
    prev_close: float
    day_change_pct: float
    drop_from_high_pct: float       # how far below 52-week high (positive = drop)
    alert_20pct_drop: bool = False  # True if >= 20 % below 52w high
    alert_near_52w_low: bool = False
    error: Optional[str] = None


def _fetch_snapshot(symbol: str, meta: dict) -> StockSnapshot:
    """Fetch latest data for one symbol via yfinance."""
    base = StockSnapshot(
        symbol=symbol,
        name=meta.get("name", symbol),
        sector=meta.get("sector", ""),
        current_price=0.0,
        high_52w=0.0,
        low_52w=0.0,
        prev_close=0.0,
        day_change_pct=0.0,
        drop_from_high_pct=0.0,
    )
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info          # lightweight call

        current  = float(info.last_price or 0)
        high_52w = float(info.year_high  or 0)
        low_52w  = float(info.year_low   or 0)
        prev_close = float(info.previous_close or current)

        if current <= 0 or high_52w <= 0:
            base.error = "No price data"
            return base

        day_chg  = ((current - prev_close) / prev_close * 100) if prev_close else 0.0
        drop_pct = ((high_52w - current)   / high_52w   * 100) if high_52w  else 0.0

        base.current_price       = round(current,  2)
        base.high_52w            = round(high_52w, 2)
        base.low_52w             = round(low_52w,  2)
        base.prev_close          = round(prev_close, 2)
        base.day_change_pct      = round(day_chg,  2)
        base.drop_from_high_pct  = round(drop_pct, 2)
        base.alert_20pct_drop    = drop_pct >= DROP_FROM_52W_HIGH_PCT
        base.alert_near_52w_low  = (
            low_52w > 0 and
            abs(current - low_52w) / low_52w * 100 <= NEAR_52W_LOW_PCT
        )
    except Exception as exc:
        base.error = str(exc)
        logger.warning("Failed to fetch %s: %s", symbol, exc)

    return base


def fetch_all_snapshots(symbols: Optional[Dict[str, dict]] = None) -> List[StockSnapshot]:
    """Fetch snapshots for all (or given) symbols. Returns list sorted by symbol."""
    if symbols is None:
        symbols = get_all_symbols()
    snapshots = []
    for sym, meta in symbols.items():
        snap = _fetch_snapshot(sym, meta)
        snapshots.append(snap)
    snapshots.sort(key=lambda s: s.symbol)
    return snapshots


def build_alert_messages(snapshots: List[StockSnapshot]) -> List[str]:
    """
    Return a list of Telegram-formatted alert strings for any snapshot
    that has triggered an alert condition.
    """
    messages = []
    for s in snapshots:
        if s.error:
            continue
        if s.alert_20pct_drop:
            msg = (
                f"🔔 *PRICE DROP ALERT*\n"
                f"*{s.name}* (`{s.symbol}`)\n"
                f"Sector: {s.sector}\n\n"
                f"📉 Current Price: ₹{s.current_price:,.2f}\n"
                f"📊 52-Week High:  ₹{s.high_52w:,.2f}\n"
                f"📉 52-Week Low:   ₹{s.low_52w:,.2f}\n"
                f"⬇️  Drop from High: *{s.drop_from_high_pct:.1f}%*\n"
                f"📆 Today's Change: {_sign(s.day_change_pct)}{abs(s.day_change_pct):.2f}%"
            )
            messages.append(msg)
        elif s.alert_near_52w_low:
            msg = (
                f"⚠️ *NEAR 52-WEEK LOW*\n"
                f"*{s.name}* (`{s.symbol}`)\n"
                f"Sector: {s.sector}\n\n"
                f"💰 Current Price: ₹{s.current_price:,.2f}\n"
                f"📉 52-Week Low:   ₹{s.low_52w:,.2f}\n"
                f"📊 52-Week High:  ₹{s.high_52w:,.2f}\n"
                f"📆 Today's Change: {_sign(s.day_change_pct)}{abs(s.day_change_pct):.2f}%"
            )
            messages.append(msg)
    return messages


def build_status_report(snapshots: List[StockSnapshot]) -> str:
    """Build a compact portfolio status message."""
    lines = ["📊 *Market Snapshot*\n"]
    for s in snapshots:
        if s.error:
            lines.append(f"  ❌ `{s.symbol}` — data unavailable")
            continue
        arrow = "🟢" if s.day_change_pct >= 0 else "🔴"
        flag  = " 🔔" if s.alert_20pct_drop else (" ⚠️" if s.alert_near_52w_low else "")
        lines.append(
            f"{arrow} `{s.symbol}` ₹{s.current_price:,.2f} "
            f"({_sign(s.day_change_pct)}{abs(s.day_change_pct):.1f}%)"
            f"  ↓{s.drop_from_high_pct:.0f}% from 52wH{flag}"
        )
    return "\n".join(lines)


def _sign(val: float) -> str:
    return "+" if val >= 0 else "-"
