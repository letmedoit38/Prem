"""
Market news monitor.

Polls Indian financial RSS feeds. Scores each headline by importance
and deduplicates via a hash cache so the same story is never sent twice.

No API key required — standard library XML + requests only.
"""
import hashlib
import json
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/rss.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.livemint.com/rss/markets",
    "https://www.business-standard.com/rss/markets-106.rss",
]

HIGH_KEYWORDS = [
    "rbi", "sebi", "budget", "rate hike", "rate cut", "repo rate",
    "gdp", "inflation", "recession", "market crash", "circuit breaker",
    "interest rate", "federal reserve", "nifty crash", "sensex crash",
    "halt trading", "circuit limit", "emergency",
]

MEDIUM_KEYWORDS = [
    "quarterly results", "earnings", "q1", "q2", "q3", "q4",
    "merger", "acquisition", "ipo", "rights issue", "buyback",
    "dividend", "bonus", "split", "fii", "dii",
    "crude oil", "rupee", "nifty", "sensex", "bank nifty",
]

SECTOR_KEYWORDS = {
    "IT":          ["it sector", "tech", "infosys", "tcs", "wipro", "hcl"],
    "Banking":     ["bank", "hdfc", "icici", "sbi", "axis", "npa", "credit"],
    "Pharma":      ["pharma", "drug", "fda", "usfda", "healthcare", "sun pharma"],
    "Energy":      ["reliance", "oil", "gas", "crude", "petrol", "energy"],
    "Auto":        ["maruti", "tata motors", "bajaj", "auto", "vehicle", "ev", "electric"],
    "FMCG":        ["itc", "fmcg", "nestle", "hindustan unilever", "hul"],
    "Gold/Silver": ["gold", "silver", "precious metal", "mcx"],
    "Infra":       ["l&t", "larsen", "infrastructure", "capex"],
    "Power":       ["ntpc", "power", "electricity", "renewable", "solar"],
}

_SEEN_FILE = os.path.join(os.path.dirname(__file__), "data", "seen_news.json")
_HEADERS   = {"User-Agent": "StockAlertBot/1.0"}


@dataclass
class NewsItem:
    title:      str
    summary:    str
    link:       str
    source:     str
    importance: str             # "high" | "medium" | "sector"
    sectors:    List[str] = field(default_factory=list)


def fetch_news(watched_sectors: Optional[List[str]] = None,
               max_per_feed: int = 10) -> List[NewsItem]:
    """Return important unseen news items, update seen cache."""
    seen  = _load_seen()
    items = []

    for url in RSS_FEEDS:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            resp.raise_for_status()
            entries = _parse_rss(resp.text)[:max_per_feed]
        except Exception as e:
            logger.warning("RSS %s failed: %s", url, e)
            continue

        source = _source_name(url)
        for e in entries:
            sid = _sid(e["title"], e["link"])
            if sid in seen:
                continue

            text = (e["title"] + " " + e["summary"]).lower()
            level, secs = _score(text, watched_sectors)
            seen.add(sid)
            if level is None:
                continue
            items.append(NewsItem(
                title=e["title"], summary=e["summary"], link=e["link"],
                source=source, importance=level, sectors=secs,
            ))

    _save_seen(seen)
    return items


def format_news(item: NewsItem) -> str:
    icon = {"high": "🚨", "medium": "📰", "sector": "📌"}.get(item.importance, "📰")
    sec  = f"\nSectors: {', '.join(item.sectors)}" if item.sectors else ""
    # Escape special MarkdownV2 chars in dynamic content
    title   = _esc(item.title)
    summary = _esc(item.summary[:300])
    source  = _esc(item.source)
    return (
        f"{icon} *{title}*\n"
        f"_{source}_{sec}\n\n"
        f"{summary}\n"
        f"[Read more]({item.link})"
    )


# ── Internals ──────────────────────────────────────────────────────────────

def _score(text: str, watched: Optional[List[str]]):
    for kw in HIGH_KEYWORDS:
        if kw in text:
            return "high", []
    secs = [s for s, kws in SECTOR_KEYWORDS.items()
            if (watched is None or s in watched) and any(k in text for k in kws)]
    if secs:
        return "sector", secs
    for kw in MEDIUM_KEYWORDS:
        if kw in text:
            return "medium", []
    return None, []


def _parse_rss(xml_text: str) -> List[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
        ns   = {"a": "http://www.w3.org/2005/Atom"}
        for e in (root.findall(".//item") or root.findall(".//a:entry", ns)):
            def g(tag):
                el = e.find(tag) or e.find(f"a:{tag}", ns)
                return (el.text or "").strip() if el is not None else ""
            lel  = e.find("link") or e.find("a:link", ns)
            link = (lel.get("href") or lel.text or "").strip() if lel is not None else ""
            items.append({
                "title":   g("title"),
                "summary": (g("description") or g("summary"))[:400],
                "link":    link,
            })
    except ET.ParseError:
        pass
    return items


def _sid(title: str, link: str) -> str:
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()


def _load_seen() -> set:
    try:
        with open(_SEEN_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_seen(seen: set) -> None:
    os.makedirs(os.path.dirname(_SEEN_FILE), exist_ok=True)
    with open(_SEEN_FILE, "w") as f:
        json.dump(list(seen)[-500:], f)


def _source_name(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    for domain, name in [
        ("economictimes", "Economic Times"),
        ("moneycontrol",  "Moneycontrol"),
        ("livemint",      "LiveMint"),
        ("business-standard", "Business Standard"),
    ]:
        if domain in host:
            return name
    return host


def _esc(text: str) -> str:
    """Escape MarkdownV2 special characters (backslash first to avoid double-escaping)."""
    # Backslash must be processed before other chars
    text = text.replace("\\", "\\\\")
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text
