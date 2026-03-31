"""
Watchlist manager.
Manages default large-cap NSE stocks, ETFs, and user-added custom symbols.
All additions/removals persist to data/watchlist.json.
"""
import json
import os
from typing import Dict

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "data", "watchlist.json")

# ── Default 10 large-cap Indian stocks — mixed sectors ────────────────────
DEFAULT_STOCKS: Dict[str, dict] = {
    "RELIANCE.NS":  {"name": "Reliance Industries",        "sector": "Energy/Conglomerate"},
    "TCS.NS":       {"name": "Tata Consultancy Services",  "sector": "IT"},
    "INFY.NS":      {"name": "Infosys",                    "sector": "IT"},
    "HDFCBANK.NS":  {"name": "HDFC Bank",                  "sector": "Banking"},
    "ICICIBANK.NS": {"name": "ICICI Bank",                 "sector": "Banking"},
    "MARUTI.NS":    {"name": "Maruti Suzuki",              "sector": "Auto"},
    "ITC.NS":       {"name": "ITC Ltd",                    "sector": "FMCG"},
    "SUNPHARMA.NS": {"name": "Sun Pharmaceutical",         "sector": "Pharma"},
    "NTPC.NS":      {"name": "NTPC",                       "sector": "Power/Utilities"},
    "LT.NS":        {"name": "Larsen & Toubro",            "sector": "Infrastructure"},
}

# ── Default 5 ETFs — Gold, Silver, Pharma, IT, Index ─────────────────────
DEFAULT_ETFS: Dict[str, dict] = {
    "GOLDBEES.NS":   {"name": "Nippon India Gold ETF",     "sector": "Gold ETF"},
    "SILVERBEES.NS": {"name": "Nippon India Silver ETF",   "sector": "Silver ETF"},
    "PHARMIBEES.NS": {"name": "Nippon India Pharma ETF",   "sector": "Pharma ETF"},
    "ICICITECHU.NS": {"name": "ICICI Pru Technology ETF",  "sector": "IT ETF"},
    "NIFTYBEES.NS":  {"name": "Nippon India Nifty 50 ETF", "sector": "Index ETF"},
}


# ── Persistence helpers ────────────────────────────────────────────────────

def _load() -> dict:
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"custom": {}}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Public API ─────────────────────────────────────────────────────────────

def get_all_symbols() -> Dict[str, dict]:
    """Return flat dict of all symbols: defaults + custom."""
    saved = _load()
    return {**DEFAULT_STOCKS, **DEFAULT_ETFS, **saved.get("custom", {})}


def add_symbol(ticker: str, name: str = "", sector: str = "Custom") -> tuple[bool, str]:
    """
    Add a custom symbol (small-cap / user pick).
    Returns (success, message).
    """
    ticker = ticker.upper().strip()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker += ".NS"

    if ticker in get_all_symbols():
        return False, f"`{ticker}` is already in the watchlist."

    saved = _load()
    saved.setdefault("custom", {})[ticker] = {
        "name":   name or ticker.replace(".NS", "").replace(".BO", ""),
        "sector": sector,
        "custom": True,
    }
    _save(saved)
    return True, f"Added `{ticker}` to the watchlist."


def remove_symbol(ticker: str) -> tuple[bool, str]:
    """
    Remove a custom symbol. Default stocks/ETFs are protected.
    Returns (success, message).
    """
    ticker = ticker.upper().strip()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker += ".NS"

    if ticker in DEFAULT_STOCKS or ticker in DEFAULT_ETFS:
        return False, f"`{ticker}` is a default symbol and cannot be removed."

    saved = _load()
    if ticker in saved.get("custom", {}):
        del saved["custom"][ticker]
        _save(saved)
        return True, f"Removed `{ticker}` from the watchlist."

    return False, f"`{ticker}` not found in custom watchlist."


def get_watchlist_text() -> str:
    """Human-readable watchlist for Telegram."""
    saved   = _load()
    custom  = saved.get("custom", {})
    lines   = ["📋 *Watchlist*\n"]

    lines.append("*🏦 Large-Cap Stocks:*")
    for sym, info in DEFAULT_STOCKS.items():
        lines.append(f"  • `{sym}` — {info['name']} \\[{info['sector']}\\]")

    lines.append("\n*📊 ETFs:*")
    for sym, info in DEFAULT_ETFS.items():
        lines.append(f"  • `{sym}` — {info['name']} \\[{info['sector']}\\]")

    if custom:
        lines.append("\n*⚡ Custom / Small-Cap:*")
        for sym, info in custom.items():
            lines.append(f"  • `{sym}` — {info['name']} \\[{info['sector']}\\]")

    return "\n".join(lines)
