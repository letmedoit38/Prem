"""
Watchlist manager for the Telegram stock alert bot.
Manages default large-cap stocks, ETFs, and user-added custom symbols.
Persists data to a JSON file so the watchlist survives restarts.
"""
import json
import os
from typing import Dict, Optional

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "alert_watchlist.json")

# ── Default 10 large-cap Indian stocks (mixed sectors) ───────────────────────
DEFAULT_STOCKS: Dict[str, dict] = {
    "RELIANCE.NS": {"name": "Reliance Industries",         "sector": "Energy/Conglomerate", "custom": False},
    "TCS.NS":       {"name": "Tata Consultancy Services",  "sector": "IT",                  "custom": False},
    "INFY.NS":      {"name": "Infosys",                    "sector": "IT",                  "custom": False},
    "HDFCBANK.NS":  {"name": "HDFC Bank",                  "sector": "Banking",             "custom": False},
    "ICICIBANK.NS": {"name": "ICICI Bank",                 "sector": "Banking",             "custom": False},
    "MARUTI.NS":    {"name": "Maruti Suzuki",              "sector": "Auto",                "custom": False},
    "ITC.NS":       {"name": "ITC Ltd",                    "sector": "FMCG",               "custom": False},
    "SUNPHARMA.NS": {"name": "Sun Pharmaceutical",         "sector": "Pharma",              "custom": False},
    "NTPC.NS":      {"name": "NTPC",                       "sector": "Power/Utilities",     "custom": False},
    "LT.NS":        {"name": "Larsen & Toubro",            "sector": "Infrastructure",      "custom": False},
}

# ── Default 5 ETFs (Gold, Silver, Pharma, IT, Index) ─────────────────────────
DEFAULT_ETFS: Dict[str, dict] = {
    "GOLDBEES.NS":    {"name": "Nippon India Gold ETF",    "sector": "Gold ETF",    "custom": False},
    "SILVERBEES.NS":  {"name": "Nippon India Silver ETF",  "sector": "Silver ETF",  "custom": False},
    "PHARMIBEES.NS":  {"name": "Nippon India Pharma ETF",  "sector": "Pharma ETF",  "custom": False},
    "ICICITECHU.NS":  {"name": "ICICI Pru Technology ETF", "sector": "IT ETF",      "custom": False},
    "NIFTYBEES.NS":   {"name": "Nippon India Nifty 50 ETF","sector": "Index ETF",   "custom": False},
}


def _load_raw() -> dict:
    """Load raw JSON from file, or return empty structure."""
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"stocks": {}, "etfs": {}, "custom": {}}


def _save_raw(data: dict) -> None:
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_watchlist() -> dict:
    """
    Return the merged watchlist: defaults + any user additions.
    Structure: {"stocks": {...}, "etfs": {...}, "custom": {...}}
    """
    saved = _load_raw()
    return {
        "stocks": {**DEFAULT_STOCKS, **saved.get("stocks", {})},
        "etfs":   {**DEFAULT_ETFS,   **saved.get("etfs", {})},
        "custom": saved.get("custom", {}),
    }


def get_all_symbols() -> Dict[str, dict]:
    """Flat dict of all symbols (stocks + ETFs + custom)."""
    wl = load_watchlist()
    return {**wl["stocks"], **wl["etfs"], **wl["custom"]}


def add_symbol(ticker: str, name: str = "", sector: str = "Custom", is_etf: bool = False) -> bool:
    """
    Add a symbol to the custom watchlist.
    Returns True if added, False if already present.
    """
    ticker = ticker.upper().strip()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"

    all_syms = get_all_symbols()
    if ticker in all_syms:
        return False  # already present

    saved = _load_raw()
    entry = {"name": name or ticker.replace(".NS", "").replace(".BO", ""),
             "sector": sector,
             "custom": True}
    if is_etf:
        saved.setdefault("etfs", {})[ticker] = entry
    else:
        saved.setdefault("custom", {})[ticker] = entry
    _save_raw(saved)
    return True


def remove_symbol(ticker: str) -> bool:
    """
    Remove a custom symbol. Default stocks/ETFs cannot be removed.
    Returns True if removed, False otherwise.
    """
    ticker = ticker.upper().strip()
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"

    saved = _load_raw()
    for section in ("stocks", "etfs", "custom"):
        if ticker in saved.get(section, {}):
            del saved[section][ticker]
            _save_raw(saved)
            return True

    # It's a default symbol — cannot remove
    if ticker in DEFAULT_STOCKS or ticker in DEFAULT_ETFS:
        return False
    return False


def get_watchlist_summary() -> str:
    """Return a human-readable summary of the full watchlist."""
    wl = load_watchlist()
    lines = ["📋 *Current Watchlist*\n"]

    lines.append("*🏦 Large-Cap Stocks:*")
    for sym, info in wl["stocks"].items():
        tag = " _(custom)_" if info.get("custom") else ""
        lines.append(f"  • `{sym}` — {info['name']} [{info['sector']}]{tag}")

    lines.append("\n*📊 ETFs:*")
    for sym, info in wl["etfs"].items():
        tag = " _(custom)_" if info.get("custom") else ""
        lines.append(f"  • `{sym}` — {info['name']} [{info['sector']}]{tag}")

    if wl["custom"]:
        lines.append("\n*⚡ Custom / Small-Cap:*")
        for sym, info in wl["custom"].items():
            lines.append(f"  • `{sym}` — {info['name']} [{info['sector']}]")

    return "\n".join(lines)
