"""
Stock price monitor.

Alert conditions:
  1. Price drops >= 20% below 52-week high  ->  buy-opportunity alert
  2. Price within 5% of 52-week low         ->  near-bottom warning
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

DROP_ALERT_PCT = 20.0   # alert when price is this % below 52-week high
NEAR_LOW_PCT   =  5.0   # warn when within this % of 52-week low


@dataclass
class Snapshot:
    symbol:         str
    name:           str
    sector:         str
    price:          float
    high_52w:       float
    low_52w:        float
    prev_close:     float
    day_chg_pct:    float
    drop_from_high: float   # positive = % below 52-week high
    alert_drop:     bool = False
    alert_near_low: bool = False
    error:          Optional[str] = None


def fetch_snapshots(symbols: Dict[str, dict]) -> List[Snapshot]:
    """Fetch live data for every symbol. Returns list sorted by symbol."""
    return sorted(
        [_fetch(sym, meta) for sym, meta in symbols.items()],
        key=lambda s: s.symbol,
    )


def _fetch(symbol: str, meta: dict) -> Snapshot:
    base = Snapshot(
        symbol=symbol, name=meta.get("name", symbol),
        sector=meta.get("sector", ""), price=0,
        high_52w=0, low_52w=0, prev_close=0,
        day_chg_pct=0, drop_from_high=0,
    )
    try:
        info  = yf.Ticker(symbol).fast_info
        price = float(info.last_price     or 0)
        h52   = float(info.year_high      or 0)
        l52   = float(info.year_low       or 0)
        prev  = float(info.previous_close or price)

        if price <= 0 or h52 <= 0:
            base.error = "no data"
            return base

        drop = (h52 - price) / h52 * 100
        day  = (price - prev) / prev * 100 if prev else 0

        base.price          = round(price, 2)
        base.high_52w       = round(h52,   2)
        base.low_52w        = round(l52,   2)
        base.prev_close     = round(prev,  2)
        base.day_chg_pct    = round(day,   2)
        base.drop_from_high = round(drop,  2)
        base.alert_drop     = drop >= DROP_ALERT_PCT
        base.alert_near_low = l52 > 0 and abs(price - l52) / l52 * 100 <= NEAR_LOW_PCT

    except Exception as e:
        base.error = str(e)
        logger.warning("fetch failed %s: %s", symbol, e)
    return base


# ── Plain-text message builders (for WhatsApp) ─────────────────────────────

def make_alert_messages(snaps: List[Snapshot]) -> List[str]:
    msgs = []
    for s in snaps:
        if s.error:
            continue
        sign = "+" if s.day_chg_pct >= 0 else ""
        if s.alert_drop:
            msgs.append(
                f"PRICE DROP ALERT\n"
                f"{s.name} ({s.symbol})\n"
                f"Sector: {s.sector}\n"
                f"-----------------------------\n"
                f"Current Price : Rs {s.price:,.2f}\n"
                f"52-Week High  : Rs {s.high_52w:,.2f}\n"
                f"52-Week Low   : Rs {s.low_52w:,.2f}\n"
                f"Drop from High: {s.drop_from_high:.1f}%  <<< ALERT\n"
                f"Today         : {sign}{s.day_chg_pct:.2f}%"
            )
        elif s.alert_near_low:
            msgs.append(
                f"NEAR 52-WEEK LOW WARNING\n"
                f"{s.name} ({s.symbol})\n"
                f"Sector: {s.sector}\n"
                f"-----------------------------\n"
                f"Current Price : Rs {s.price:,.2f}\n"
                f"52-Week Low   : Rs {s.low_52w:,.2f}\n"
                f"52-Week High  : Rs {s.high_52w:,.2f}\n"
                f"Today         : {sign}{s.day_chg_pct:.2f}%"
            )
    return msgs


def make_status_report(snaps: List[Snapshot]) -> str:
    lines = ["--- Market Snapshot ---"]
    for s in snaps:
        if s.error:
            lines.append(f"  {s.symbol}: unavailable")
            continue
        dot  = "UP" if s.day_chg_pct >= 0 else "DN"
        sign = "+" if s.day_chg_pct >= 0 else ""
        flag = " [DROP ALERT]" if s.alert_drop else (" [NEAR LOW]" if s.alert_near_low else "")
        lines.append(
            f"  [{dot}] {s.symbol}: Rs {s.price:,.2f} "
            f"({sign}{s.day_chg_pct:.1f}%) "
            f"| -{s.drop_from_high:.0f}% from 52wH{flag}"
        )
    return "\n".join(lines)
