"""
Task 2 — Udyam MSME Data Fetcher
Fetches district-wise MSME registrations from data.gov.in Open Government Data
for both Manufacturing and Services categories.
"""

import time
import logging
import os
import requests
import pandas as pd

import config

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_with_retry(url: str, params: dict) -> requests.Response | None:
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params,
                                headers=config.REQUEST_HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp
            logger.warning("Attempt %d: HTTP %d — %s", attempt, resp.status_code, url)
            if resp.status_code in (429, 503):
                time.sleep(2 ** attempt)
            elif resp.status_code == 403:
                logger.error(
                    "403 Forbidden — check DATA_GOV_API_KEY in .env "
                    "(register at https://data.gov.in/user/register)"
                )
                return None
        except requests.RequestException as exc:
            logger.warning("Attempt %d: %s", attempt, exc)
            time.sleep(2 ** attempt)
    return None


def _normalise_msme(row: dict, district: str, sector: str) -> dict:
    """Map data.gov.in field names → our unified schema."""
    name    = (
        row.get("enterprise_name")
        or row.get("name_of_enterprise")
        or row.get("enterprise_name_in_english")
        or row.get("enterpriseName", "")
    )
    udyam   = (
        row.get("udyam_registration_number")
        or row.get("udyam_no")
        or row.get("registration_number", "")
    )
    address = (
        row.get("address")
        or row.get("registered_address")
        or row.get("office_address", "")
    )
    email   = row.get("email") or row.get("email_id", "")
    phone   = row.get("mobile") or row.get("phone") or row.get("contact_number", "")
    date    = (
        row.get("date_of_commencement_of_production")
        or row.get("registration_date")
        or row.get("date_of_registration", "")
    )
    return {
        "SOURCE": "Udyam",
        "DISTRICT": district,
        "TALUK": row.get("taluk", row.get("block", "")),
        "SECTOR": sector,
        "COMPANY_NAME": name,
        "CIN_OR_UDYAM_NO": udyam,
        "INCORPORATION_DATE": date,
        "AUTHORIZED_CAPITAL": 0.0,     # not available in Udyam dataset
        "DIRECTOR_NAMES": row.get("name_of_entrepreneur", row.get("owner_name", "")),
        "EMAIL": email,
        "PHONE": phone,
        "ADDRESS": address,
        "HAS_GST": str(row.get("gst_number", row.get("gstin", "")) != "").lower(),
        "GEM_REGISTERED": False,
        "BANK_PRODUCT": "",
        "SCORE": 0,
    }


# ── Fetcher ───────────────────────────────────────────────────────────────────

def _fetch_resource(resource_id: str, sector: str) -> pd.DataFrame:
    """
    Page through a data.gov.in resource and return records matching our
    three target districts.
    """
    if not config.DATA_GOV_API_KEY:
        logger.error(
            "DATA_GOV_API_KEY not set. "
            "Register at https://data.gov.in/user/register and add it to .env"
        )
        return pd.DataFrame()

    print(f"\n  [Udyam] Fetching {sector} resource: {resource_id}")

    all_records: list[dict] = []
    offset = 0
    limit  = 500

    while True:
        params = {
            "api-key":  config.DATA_GOV_API_KEY,
            "format":   "json",
            "offset":   offset,
            "limit":    limit,
            "filters[state]": config.STATE,
        }

        resp = _get_with_retry(
            config.DATA_GOV_API_BASE + resource_id, params
        )
        if resp is None:
            break

        try:
            payload = resp.json()
        except ValueError:
            logger.warning("Non-JSON response for resource %s", resource_id)
            break

        records = payload.get("records", [])
        total   = int(payload.get("total", 0))

        for row in records:
            district_field = (
                row.get("district")
                or row.get("district_name")
                or row.get("districtName", "")
            ).strip().title()

            for target in config.DISTRICTS:
                if target.lower() in district_field.lower():
                    all_records.append(
                        _normalise_msme(row, target, sector)
                    )
                    break

        fetched_so_far = offset + len(records)
        print(
            f"    [{sector}] offset={offset}: got {len(records)} rows "
            f"| matching so far: {len(all_records)} / {total} total"
        )

        if fetched_so_far >= total or len(records) == 0:
            break

        offset += limit
        time.sleep(config.API_RATE_LIMIT)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["CIN_OR_UDYAM_NO"], keep="first")
    return df


# ── District-level filter helper ──────────────────────────────────────────────

def _fetch_by_district(resource_id: str, sector: str,
                        district: str) -> pd.DataFrame:
    """Try district-specific filter parameter if bulk fetch yields nothing."""
    if not config.DATA_GOV_API_KEY:
        return pd.DataFrame()

    print(f"    [{sector}] Trying district-specific query for: {district}")

    all_records: list[dict] = []
    offset = 0
    limit  = 500

    while True:
        params = {
            "api-key":           config.DATA_GOV_API_KEY,
            "format":            "json",
            "offset":            offset,
            "limit":             limit,
            "filters[state]":    config.STATE,
            "filters[district]": district,
        }

        resp = _get_with_retry(
            config.DATA_GOV_API_BASE + resource_id, params
        )
        if resp is None:
            break

        try:
            payload = resp.json()
        except ValueError:
            break

        records = payload.get("records", [])
        total   = int(payload.get("total", 0))

        for row in records:
            all_records.append(_normalise_msme(row, district, sector))

        fetched_so_far = offset + len(records)
        if fetched_so_far >= total or len(records) == 0:
            break
        offset += limit
        time.sleep(config.API_RATE_LIMIT)

    return pd.DataFrame(all_records) if all_records else pd.DataFrame()


# ── Public Entry Point ────────────────────────────────────────────────────────

def fetch_udyam_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch Udyam MSME data for Manufacturing and Services.
    Saves msme_manufacturing.csv and msme_services.csv.
    Returns (df_manufacturing, df_services).
    """
    os.makedirs(config.DATA_DIR, exist_ok=True)

    results = {}
    for sector, resource_id, out_path in [
        ("Manufacturing", config.UDYAM_MANUFACTURING_RESOURCE, config.UDYAM_MFG_CSV_OUT),
        ("Services",      config.UDYAM_SERVICES_RESOURCE,      config.UDYAM_SVC_CSV_OUT),
    ]:
        print(f"\n[Udyam] === {sector} ===")

        df = _fetch_resource(resource_id, sector)

        if df.empty:
            print(f"  Bulk fetch empty — trying per-district fallback …")
            frames = []
            for district in config.DISTRICTS:
                dfd = _fetch_by_district(resource_id, sector, district)
                if not dfd.empty:
                    frames.append(dfd)
                time.sleep(config.API_RATE_LIMIT)
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        if df.empty:
            print(f"  ✗ No {sector} MSME data retrieved. "
                  "Check DATA_GOV_API_KEY and resource IDs in config.py")
        else:
            df = df.drop_duplicates(subset=["CIN_OR_UDYAM_NO"], keep="first")
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            print(f"  ✓ {len(df)} records → {out_path}")

        results[sector] = df

    return results.get("Manufacturing", pd.DataFrame()), \
           results.get("Services",      pd.DataFrame())


# ── CLI runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df_mfg, df_svc = fetch_udyam_data()

    print("\n[Manufacturing] Sample:")
    if not df_mfg.empty:
        print(df_mfg[["COMPANY_NAME", "CIN_OR_UDYAM_NO", "DISTRICT"]].head(5).to_string(index=False))

    print("\n[Services] Sample:")
    if not df_svc.empty:
        print(df_svc[["COMPANY_NAME", "CIN_OR_UDYAM_NO", "DISTRICT"]].head(5).to_string(index=False))
