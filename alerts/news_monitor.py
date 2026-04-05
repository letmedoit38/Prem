"""
News / market event monitor.

Pulls headlines from multiple RSS feeds covering Indian equity markets.
Filters stories relevant to the symbols in the watchlist and flags
them as "important" based on keyword scoring.

No API key required — pure RSS / HTTP.
Uses stdlib xml.etree.ElementTree to parse RSS (no feedparser dependency).
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

# ── RSS feeds ──────────────────────────────────────────────────────────────
RSS_FEEDS = [
    # Economic Times – Markets
    "https://economictimes.indiatimes.com/markets/rss.cms",
    # Moneycontrol – Markets
    "https://www.moneycontrol.com/rss/marketreports.xml",
    # LiveMint – Markets
    "https://www.livemint.com/rss/markets",
    # Business Standard
    "https://www.business-standard.com/rss/markets-106.rss",
    # NDTV Profit
    "https://www.ndtvprofit.com/markets/rss",
]

# ── Keyword scoring: higher score → more important ─────────────────────────
HIGH_IMPORTANCE_KEYWORDS = [
    "rbi", "sebi", "budget", "rate hike", "rate cut", "repo rate",
    "gdp", "inflation", "recession", "market crash", "circuit breaker",
    "interest rate", "fed", "federal reserve", "nifty crash",
    "sensex crash", "halt trading", "circuit limit",
]

MEDIUM_IMPORTANCE_KEYWORDS = [
    "quarterly results", "earnings", "q1", "q2", "q3", "q4",
    "merger", "acquisition", "ipo", "rights issue", "buyback",
    "dividend", "bonus", "split", "fii", "dii", "foreign investors",
    "crude oil", "rupee", "dollar", "usd/inr",
    "nifty", "sensex", "bank nifty",
]

SECTOR_KEYWORDS = {
    "IT":          ["it sector", "tech", "infosys", "tcs", "wipro", "hcl"],
    "Banking":     ["bank", "hdfc", "icici", "sbi", "axis", "rbi", "npa", "credit"],
    "Pharma":      ["pharma", "drug", "fda", "usfda", "healthcare", "sun pharma"],
    "Energy":      ["reliance", "oil", "gas", "crude", "petrol", "energy"],
    "Auto":        ["maruti", "tata motors", "bajaj", "auto", "vehicle", "ev", "electric"],
    "FMCG":        ["itc", "fmcg", "consumer", "nestle", "hindustan unilever", "hul"],
    "Gold/Silver": ["gold", "silver", "precious metal", "mcx"],
    "Infra":       ["l&t", "larsen", "infrastructure", "capex", "pli"],
    "Power":       ["ntpc", "power", "electricity", "renewable", "solar"],
}

# ── Seen-stories cache (avoid duplicate alerts) ────────────────────────────
_SEEN_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "seen_news.json")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (StockAlertBot/1.0; +https://github.com/letmedoit38/prem)"
}


def _load_seen() -> set:
    try:
        with open(_SEEN_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_seen(seen: set) -> None:
    os.makedirs(os.path.dirname(_SEEN_FILE), exist_ok=True)
    trimmed = list(seen)[-500:]   # cap at 500 to prevent unbounded growth
    with open(_SEEN_FILE, "w") as f:
        json.dump(trimmed, f)


def _story_id(title: str, link: str) -> str:
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()


def _parse_rss(xml_text: str) -> List[dict]:
    """Parse RSS 2.0 / Atom XML into a list of {title, summary, link, published}."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        # Support both RSS 2.0 (<item>) and Atom (<entry>)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
        for entry in entries:
            def _text(tag: str) -> str:
                el = entry.find(tag) or entry.find(f"atom:{tag}", ns)
                return (el.text or "").strip() if el is not None else ""

            link_el = entry.find("link") or entry.find("atom:link", ns)
            link = ""
            if link_el is not None:
                link = link_el.get("href") or link_el.text or ""

            items.append({
                "title":     _text("title"),
                "summary":   (_text("description") or _text("summary"))[:400],
                "link":      link.strip(),
                "published": _text("pubDate") or _text("updated"),
            })
    except ET.ParseError as exc:
        logger.debug("XML parse error: %s", exc)
    return items


# ── Public API ─────────────────────────────────────────────────────────────

@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    source: str
    importance: str           # "high" | "medium" | "sector"
    sectors: List[str] = field(default_factory=list)
    published: str = ""


def fetch_important_news(
    watched_sectors: Optional[List[str]] = None,
    max_per_feed: int = 10,
) -> List[NewsItem]:
    """
    Fetch and return important news items not yet seen.
    Updates the seen-stories cache.
    """
    seen      = _load_seen()
    new_items: List[NewsItem] = []

    for feed_url in RSS_FEEDS:
        source = _feed_source_name(feed_url)
        try:
            resp = requests.get(feed_url, headers=_HEADERS, timeout=10)
            resp.raise_for_status()
            raw_entries = _parse_rss(resp.text)[:max_per_feed]
        except Exception as exc:
            logger.warning("RSS fetch failed for %s: %s", feed_url, exc)
            continue

        for entry in raw_entries:
            title   = entry["title"]
            summary = entry["summary"]
            link    = entry["link"]
            pub     = entry["published"]

            if not title:
                continue

            story_id = _story_id(title, link)
            if story_id in seen:
                continue

            text_lower = (title + " " + summary).lower()
            importance, matched_sectors = _score(text_lower, watched_sectors)
            if importance is None:
                seen.add(story_id)
                continue

            new_items.append(NewsItem(
                title=title,
                summary=summary,
                link=link,
                source=source,
                importance=importance,
                sectors=matched_sectors,
                published=pub,
            ))
            seen.add(story_id)

    _save_seen(seen)
    return new_items


def _score(text: str, watched_sectors: Optional[List[str]]) -> tuple:
    """Return (importance_level, matched_sectors) or (None, [])."""
    for kw in HIGH_IMPORTANCE_KEYWORDS:
        if kw in text:
            return "high", []

    matched_sectors = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        if watched_sectors and sector not in watched_sectors:
            continue
        if any(kw in text for kw in keywords):
            matched_sectors.append(sector)

    if matched_sectors:
        return "sector", matched_sectors

    for kw in MEDIUM_IMPORTANCE_KEYWORDS:
        if kw in text:
            return "medium", []

    return None, []


def format_news_alert(item: NewsItem) -> str:
    """Return a Telegram-formatted string for one news item."""
    icon = {"high": "🚨", "medium": "📰", "sector": "📌"}.get(item.importance, "📰")
    sectors_str = ", ".join(item.sectors) if item.sectors else ""
    sector_line = f"\nSectors: {sectors_str}" if sectors_str else ""

    return (
        f"{icon} *{item.title}*\n"
        f"_{item.source}_{sector_line}\n\n"
        f"{item.summary}\n"
        f"[Read more]({item.link})"
    )


def _feed_source_name(url: str) -> str:
    host = urlparse(url).netloc.replace("www.", "")
    name_map = {
        "economictimes.indiatimes.com": "Economic Times",
        "moneycontrol.com":             "Moneycontrol",
        "ndtvprofit.com":               "NDTV Profit",
        "livemint.com":                 "LiveMint",
        "business-standard.com":        "Business Standard",
    }
    for domain, name in name_map.items():
        if domain in host:
            return name
    return host
