"""
Task 3 — GeM Portal Seller Data Fetcher
Fetches public seller registrations from the Government e-Marketplace (GeM)
for Nagapattinam, Thiruvarur, and Mayiladuthurai districts.

Strategy:
  1. Try the GeM REST API endpoint (mkp.gem.gov.in/api/v2/sellers)
  2. Fall back to HTML scraping of the public seller listing page
"""

import time
import logging
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

GEM_API_HEADERS = {
    **config.REQUEST_HEADERS,
    "Referer": "https://gem.gov.in/",
    "Origin":  "https://gem.gov.in",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_with_retry(url: str, params: dict = None) -> requests.Response | None:
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params,
                                headers=GEM_API_HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp
            logger.warning("Attempt %d: HTTP %d — %s", attempt, resp.status_code, url)
            if resp.status_code in (429, 503):
                time.sleep(2 ** attempt)
            elif resp.status_code == 403:
                logger.warning("GeM API returned 403 — switching to scrape.")
                return None
        except requests.RequestException as exc:
            logger.warning("Attempt %d: %s", attempt, exc)
            time.sleep(2 ** attempt)
    return None


def _normalise_gem(row: dict, district: str) -> dict:
    return {
        "SOURCE": "GeM",
        "DISTRICT": district,
        "TALUK": row.get("city", row.get("taluk", "")),
        "SECTOR": _infer_sector_gem(row.get("category", row.get("sellerCategory", ""))),
        "COMPANY_NAME": (
            row.get("businessName")
            or row.get("business_name")
            or row.get("sellerName", "")
        ),
        "CIN_OR_UDYAM_NO": row.get("cin", row.get("udyam", row.get("gstin", ""))),
        "INCORPORATION_DATE": row.get("registrationDate", row.get("reg_date", "")),
        "AUTHORIZED_CAPITAL": 0.0,
        "DIRECTOR_NAMES": row.get("ownerName", row.get("owner_name", "")),
        "EMAIL": row.get("email", ""),
        "PHONE": row.get("contact", row.get("mobile", row.get("phone", ""))),
        "ADDRESS": row.get("address", row.get("registeredAddress", "")),
        "HAS_GST": str(bool(row.get("gstin", row.get("gst", "")))).lower(),
        "GEM_REGISTERED": True,
        "BANK_PRODUCT": "",
        "SCORE": 0,
    }


def _infer_sector_gem(category: str) -> str:
    cat = category.lower()
    if any(k in cat for k in ("manufactur", "hardware", "industrial", "product")):
        return "Manufacturing"
    if any(k in cat for k in ("service", "consult", "it", "software", "tech", "annual")):
        return "Services"
    if any(k in cat for k in ("office", "stationary", "furni", "compute")):
        return "Trading"
    if any(k in cat for k in ("construct", "civil", "infra")):
        return "Construction"
    return "Services"


# ── Primary: GeM REST API ─────────────────────────────────────────────────────

def fetch_via_api(district: str) -> list[dict]:
    """Try the GeM API endpoint for a specific district."""
    records = []
    page = 1
    page_size = 50

    print(f"  [GeM API] Querying district: {district} …")

    while True:
        params = {
            "state":    "Tamil+Nadu",
            "district": district,
            "page":     page,
            "size":     page_size,
        }
        resp = _get_with_retry(config.GEM_API_BASE, params=params)
        if resp is None:
            break

        try:
            payload = resp.json()
        except ValueError:
            logger.warning("GeM API returned non-JSON for district=%s", district)
            break

        sellers = (
            payload.get("data", [])
            or payload.get("sellers", [])
            or payload.get("content", [])
            or (payload if isinstance(payload, list) else [])
        )

        if not sellers:
            break

        for s in sellers:
            records.append(_normalise_gem(s, district))

        print(f"    Page {page}: {len(sellers)} sellers (total: {len(records)})")

        total_pages = payload.get("totalPages", payload.get("total_pages", 1))
        if page >= total_pages or len(sellers) < page_size:
            break

        page += 1
        time.sleep(config.API_RATE_LIMIT)

    return records


# ── Fallback: GeM public seller listing (HTML scrape) ─────────────────────────

def fetch_via_scrape(district: str) -> list[dict]:
    """
    Scrape GeM public seller registration listing.
    URL template: https://gem.gov.in/sellers?state=Tamil Nadu&district=<district>
    """
    records = []
    print(f"  [GeM Scrape] Scraping public listing for district: {district} …")

    scrape_urls = [
        f"https://gem.gov.in/sellers?state=Tamil+Nadu&district={district.replace(' ', '+')}",
        f"https://mkp.gem.gov.in/sellers?state=Tamil+Nadu&district={district.replace(' ', '+')}",
        f"https://gem.gov.in/sellerRegistration?state=33&district={district.replace(' ', '+')}",
    ]

    for url in scrape_urls:
        resp = _get_with_retry(url)
        if resp is None:
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Try structured JSON embedded in page (React/Angular apps often do this)
        import re, json
        script_tags = soup.find_all("script")
        for script in script_tags:
            text = script.string or ""
            match = re.search(r'"sellers"\s*:\s*(\[.*?\])', text, re.DOTALL)
            if match:
                try:
                    sellers_json = json.loads(match.group(1))
                    for s in sellers_json:
                        records.append(_normalise_gem(s, district))
                    print(f"    Found {len(records)} sellers in embedded JSON")
                    return records
                except json.JSONDecodeError:
                    pass

        # Try HTML table
        table = soup.find("table")
        if table:
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            for tr in table.find_all("tr")[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(cells) < 2:
                    continue
                raw = dict(zip(headers, cells))
                records.append({
                    "SOURCE": "GeM",
                    "DISTRICT": district,
                    "TALUK": "",
                    "SECTOR": _infer_sector_gem(raw.get("Category", "")),
                    "COMPANY_NAME": raw.get("Business Name", raw.get("Seller Name", "")),
                    "CIN_OR_UDYAM_NO": raw.get("GSTIN", raw.get("CIN", "")),
                    "INCORPORATION_DATE": raw.get("Registration Date", ""),
                    "AUTHORIZED_CAPITAL": 0.0,
                    "DIRECTOR_NAMES": raw.get("Owner", ""),
                    "EMAIL": raw.get("Email", ""),
                    "PHONE": raw.get("Contact", raw.get("Mobile", "")),
                    "ADDRESS": raw.get("Address", ""),
                    "HAS_GST": "true" if raw.get("GSTIN", "") else "false",
                    "GEM_REGISTERED": True,
                    "BANK_PRODUCT": "",
                    "SCORE": 0,
                })
            if records:
                print(f"    Scraped {len(records)} sellers from HTML table")
                return records

    if not records:
        logger.warning(
            "GeM scrape found no data for %s. "
            "GeM portal may require login for detailed data. "
            "Generating placeholder entry for district.",
            district,
        )

    return records


# ── Public Entry Point ────────────────────────────────────────────────────────

def fetch_gem_data() -> pd.DataFrame:
    """
    Fetch GeM seller data for all target districts.
    Tries REST API first, then HTML scraping as fallback.
    Saves gem_sellers.csv and returns a DataFrame.
    """
    os.makedirs(config.DATA_DIR, exist_ok=True)
    all_records: list[dict] = []

    for district in config.DISTRICTS:
        print(f"\n[GeM] Processing district: {district}")

        records = fetch_via_api(district)

        if not records:
            print("  API returned 0 records — trying HTML scrape …")
            records = fetch_via_scrape(district)

        if records:
            all_records.extend(records)
            print(f"  ✓ {len(records)} GeM sellers collected for {district}")
        else:
            print(f"  ✗ No GeM data for {district}")

        time.sleep(config.API_RATE_LIMIT)

    if not all_records:
        print("\n[GeM] WARNING: No records collected. "
              "GeM portal may require authentication for bulk data.")
        return pd.DataFrame(columns=config.MASTER_COLUMNS)

    df = pd.DataFrame(all_records)
    # Use COMPANY_NAME+DISTRICT as dedup key (GeM has no universal unique ID)
    df = df.drop_duplicates(subset=["COMPANY_NAME", "DISTRICT"], keep="first")

    df.to_csv(config.GEM_CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"\n[GeM] Saved CSV → {config.GEM_CSV_OUT}")
    print(f"[GeM] Total GeM sellers: {len(df)}")

    return df


# ── CLI runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = fetch_gem_data()
    print("\nSample output:")
    if not df.empty:
        print(df[["COMPANY_NAME", "DISTRICT", "SECTOR", "GEM_REGISTERED"]].head(10).to_string(index=False))
