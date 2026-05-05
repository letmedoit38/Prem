"""
Task 1 — MCA21 Company Data Fetcher
Fetches new company registrations for Nagapattinam, Thiruvarur, Mayiladuthurai
from the MCA V3 public API with BeautifulSoup fallback.
"""

import json
import time
import logging
import os
import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_with_retry(url: str, params: dict = None, headers: dict = None,
                    retries: int = None) -> requests.Response | None:
    retries = retries or config.MAX_RETRIES
    headers = headers or config.REQUEST_HEADERS
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp
            logger.warning("Attempt %d: HTTP %d for %s", attempt, resp.status_code, url)
            if resp.status_code in (429, 503):
                time.sleep(2 ** attempt)
        except requests.RequestException as exc:
            logger.warning("Attempt %d: %s", attempt, exc)
            time.sleep(2 ** attempt)
    return None


def _normalise_company(raw: dict, district: str) -> dict:
    """Map MCA API field names → our unified schema."""
    return {
        "SOURCE": "MCA21",
        "DISTRICT": district,
        "TALUK": raw.get("registeredOfficeCity", ""),
        "SECTOR": _infer_sector(raw.get("mainDivisionDescription", "")),
        "COMPANY_NAME": raw.get("companyName", raw.get("company_name", "")),
        "CIN_OR_UDYAM_NO": raw.get("cin", raw.get("CIN", "")),
        "INCORPORATION_DATE": raw.get(
            "dateOfIncorporation",
            raw.get("date_of_incorporation", "")
        ),
        "AUTHORIZED_CAPITAL": _parse_capital(
            raw.get("authorisedCapital", raw.get("authorized_capital", 0))
        ),
        "DIRECTOR_NAMES": raw.get("directors", raw.get("directorNames", "")),
        "EMAIL": raw.get("email", raw.get("emailId", "")),
        "PHONE": raw.get("phone", ""),
        "ADDRESS": raw.get(
            "registeredAddress",
            raw.get("registered_address", "")
        ),
        "HAS_GST": "",    # populated by score_leads
        "GEM_REGISTERED": False,
        "BANK_PRODUCT": "",
        "SCORE": 0,
    }


def _infer_sector(division_desc: str) -> str:
    desc = division_desc.lower()
    if any(k in desc for k in ("manufactur", "production", "processing", "fabricat")):
        return "Manufacturing"
    if any(k in desc for k in ("service", "consult", "it ", "software", "tech")):
        return "Services"
    if any(k in desc for k in ("trade", "wholesale", "retail", "import", "export")):
        return "Trading"
    if any(k in desc for k in ("construct", "infra", "civil", "build")):
        return "Construction"
    return "Other"


def _parse_capital(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return 0.0


# ── Primary: MCA V3 API ───────────────────────────────────────────────────────

def fetch_via_api(district: str) -> list[dict]:
    """Call the MCA V3 CompanyMasterData public endpoint."""
    records = []
    page = 1
    page_size = 100

    print(f"  [MCA API] Querying district: {district} …")

    while True:
        params = {
            "state": config.STATE,
            "district": district,
            "offset": (page - 1) * page_size,
            "limit": page_size,
        }
        resp = _get_with_retry(config.MCA_API_BASE, params=params)
        if resp is None:
            logger.warning("MCA API unreachable for district=%s page=%d", district, page)
            break

        try:
            payload = resp.json()
        except ValueError:
            logger.warning("MCA API returned non-JSON for district=%s", district)
            break

        # Handle different MCA response shapes
        companies = (
            payload.get("data", [])
            or payload.get("companyDetails", [])
            or (payload if isinstance(payload, list) else [])
        )

        if not companies:
            break

        for company in companies:
            records.append(_normalise_company(company, district))

        print(f"    Page {page}: fetched {len(companies)} records (total so far: {len(records)})")

        if len(companies) < page_size:
            break
        page += 1
        time.sleep(config.API_RATE_LIMIT)

    return records


# ── Fallback: MCA public search portal (HTML scrape) ─────────────────────────

def fetch_via_scrape(district: str) -> list[dict]:
    """
    Scrape MCA company search portal as fallback when the API is gated.
    Uses POST to the public master-data search form.
    """
    records = []
    print(f"  [MCA Scrape] Falling back to HTML scrape for district: {district} …")

    search_url = "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do"
    payload = {
        "companyState": config.STATE_CODE,
        "district": district,
        "act": "1",       # Companies Act 2013
        "companyType": "",
        "companyCategory": "",
        "companySubCategory": "",
    }

    headers = {
        **config.REQUEST_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.mca.gov.in/",
    }

    resp = _get_with_retry(search_url, headers=headers)
    if resp is None:
        logger.error("MCA scrape portal unreachable for %s", district)
        return records

    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "CompanyList"}) or soup.find("table")

    if not table:
        logger.warning("MCA scrape: no data table found for %s", district)
        return records

    headers_row = [th.get_text(strip=True) for th in table.find_all("th")]
    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 3:
            continue
        raw = dict(zip(headers_row, cells))
        records.append({
            "SOURCE": "MCA21",
            "DISTRICT": district,
            "TALUK": "",
            "SECTOR": _infer_sector(raw.get("Main Division Description", "")),
            "COMPANY_NAME": raw.get("Company Name", ""),
            "CIN_OR_UDYAM_NO": raw.get("CIN", ""),
            "INCORPORATION_DATE": raw.get("Date of Incorporation", ""),
            "AUTHORIZED_CAPITAL": _parse_capital(
                raw.get("Authorized Capital (Rs)", 0)
            ),
            "DIRECTOR_NAMES": raw.get("Director Names", ""),
            "EMAIL": raw.get("Email", ""),
            "PHONE": raw.get("Phone", ""),
            "ADDRESS": raw.get("Registered Address", ""),
            "HAS_GST": "",
            "GEM_REGISTERED": False,
            "BANK_PRODUCT": "",
            "SCORE": 0,
        })

    print(f"    Scraped {len(records)} records for {district}")
    return records


# ── Public Entry Point ────────────────────────────────────────────────────────

def fetch_mca_data() -> pd.DataFrame:
    """
    Fetch MCA company data for all target districts.
    Tries the V3 API first; falls back to HTML scraping on failure/empty result.
    Saves companies.json and companies.csv and returns a DataFrame.
    """
    os.makedirs(config.DATA_DIR, exist_ok=True)
    all_records: list[dict] = []

    for district in config.DISTRICTS:
        print(f"\n[MCA] Processing district: {district}")

        records = fetch_via_api(district)

        if not records:
            print(f"  API returned 0 records — trying HTML scrape …")
            records = fetch_via_scrape(district)

        if records:
            all_records.extend(records)
            print(f"  ✓ {len(records)} companies collected for {district}")
        else:
            print(f"  ✗ No data retrieved for {district} (API and scrape both failed)")

        time.sleep(config.API_RATE_LIMIT)

    if not all_records:
        print("\n[MCA] WARNING: No records collected from any district.")
        return pd.DataFrame(columns=config.MASTER_COLUMNS)

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["CIN_OR_UDYAM_NO"], keep="first")
    df = df[df["CIN_OR_UDYAM_NO"] != ""]

    # Save JSON
    df.to_json(config.MCA_JSON_OUT, orient="records", indent=2, force_ascii=False)
    print(f"\n[MCA] Saved JSON → {config.MCA_JSON_OUT}")

    # Save CSV
    df.to_csv(config.MCA_CSV_OUT, index=False, encoding="utf-8-sig")
    print(f"[MCA] Saved CSV  → {config.MCA_CSV_OUT}")
    print(f"[MCA] Total companies: {len(df)}")

    return df


# ── CLI runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = fetch_mca_data()
    print("\nSample output:")
    print(df[["COMPANY_NAME", "CIN_OR_UDYAM_NO", "DISTRICT", "SECTOR",
              "AUTHORIZED_CAPITAL"]].head(10).to_string(index=False))
