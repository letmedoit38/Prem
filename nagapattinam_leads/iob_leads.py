#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   Indian Overseas Bank — Nagapattinam Regional Office        ║
║   Automated Lead Generation Pipeline  •  Single-File Edition ║
║   Districts: Nagapattinam | Thiruvarur | Mayiladuthurai       ║
║                                                              ║
║   HOW TO RUN:                                                ║
║     python iob_leads.py                                      ║
║   or double-click this file (Windows)                        ║
╚══════════════════════════════════════════════════════════════╝
"""

# ┌─────────────────────────────────────────────────────────────┐
# │  STEP 1 — FILL IN YOUR CREDENTIALS BELOW BEFORE RUNNING    │
# └─────────────────────────────────────────────────────────────┘

DATA_GOV_API_KEY = "579b464db66ec23bdd000001700d8e38f4594084504affde913115ef"

GOOGLE_SHEET_NAME = "Nagapattinam RO - Live Leads"

# Paste the full path to your service_account.json file here
# (or keep "service_account.json" and put the file next to this script)
GOOGLE_SERVICE_ACCOUNT_JSON = "service_account.json"

# ── Optional: Email alerts (leave blank to skip) ──────────────
ALERT_EMAIL_SENDER    = ""          # your Gmail / IOB email
ALERT_EMAIL_PASSWORD  = ""          # Gmail App Password
ALERT_EMAIL_RECIPIENT = ""          # who receives the report
SMTP_HOST             = "smtp.gmail.com"
SMTP_PORT             = 587

# ── Pipeline settings ─────────────────────────────────────────
DISTRICTS      = ["Nagapattinam", "Thiruvarur", "Mayiladuthurai"]
STATE          = "Tamil Nadu"
STATE_CODE     = "33"
API_SLEEP      = 2      # seconds between API calls
MAX_RETRIES    = 3
SCHEDULE_HOUR  = 6      # 6 AM IST daily (if you start the scheduler)

# ┌─────────────────────────────────────────────────────────────┐
# │  STEP 2 — NOTHING ELSE TO CHANGE. JUST RUN THE FILE.       │
# └─────────────────────────────────────────────────────────────┘


# ══════════════════════════════════════════════════════════════
#  AUTO-INSTALL MISSING PACKAGES
# ══════════════════════════════════════════════════════════════
import subprocess, sys, os

REQUIRED_PACKAGES = {
    "requests":          "requests",
    "pandas":            "pandas",
    "gspread":           "gspread",
    "google.oauth2":     "google-auth",
    "openpyxl":          "openpyxl",
    "bs4":               "beautifulsoup4",
    "lxml":              "lxml",
    "dotenv":            "python-dotenv",
    "apscheduler":       "apscheduler",
    "colorama":          "colorama",
}

def _install(package_name):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", package_name, "-q"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

print("Checking dependencies ...")
for import_name, pip_name in REQUIRED_PACKAGES.items():
    try:
        __import__(import_name)
    except ImportError:
        print(f"  Installing {pip_name} ...", end=" ", flush=True)
        _install(pip_name)
        print("done")

print("All dependencies ready.\n")

# ══════════════════════════════════════════════════════════════
#  IMPORTS
# ══════════════════════════════════════════════════════════════
import json, time, logging, re, smtplib, traceback
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import requests
import pandas as pd
from bs4 import BeautifulSoup
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    GREEN  = Fore.GREEN
    RED    = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN   = Fore.CYAN
    BOLD   = Style.BRIGHT
    RESET  = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = BOLD = RESET = ""

# ══════════════════════════════════════════════════════════════
#  PATHS  (all output goes next to this script)
# ══════════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

LOG_FILE          = LOGS_DIR / "pipeline.log"
MCA_CSV           = DATA_DIR / "companies.csv"
MCA_JSON          = DATA_DIR / "companies.json"
UDYAM_MFG_CSV     = DATA_DIR / "msme_manufacturing.csv"
UDYAM_SVC_CSV     = DATA_DIR / "msme_services.csv"
GEM_CSV           = DATA_DIR / "gem_sellers.csv"
MASTER_CSV        = DATA_DIR / "master_leads.csv"
MASTER_XLSX       = DATA_DIR / "master_leads.xlsx"

# ══════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("iob_pipeline")

# ══════════════════════════════════════════════════════════════
#  SCORING RULES
# ══════════════════════════════════════════════════════════════
SCORING = {
    "authorized_capital_above_10L": 20,
    "incorporated_after_jan_2024":  25,
    "has_gst":                      15,
    "sector_manufacturing":         20,
    "sector_services":              10,
    "gem_registered":               20,
    "has_contact_info":             10,
}
SCORE_RAW_MAX = sum(SCORING.values())   # 120 → normalise to 100

BANK_PRODUCTS = {
    "Manufacturing": "MSME-TL; CC; Machinery Loan",
    "Services":      "MSME-CC; OD; GeM Finance",
    "Technology":    "MSME-CC; OD; GeM Finance",
    "Trading":       "CC; GeM Order Finance; Current Account",
    "Construction":  "Project Finance; CC; BG",
    "Other":         "MSME-CC; Current Account",
}

MASTER_COLUMNS = [
    "SOURCE", "DISTRICT", "TALUK", "SECTOR", "COMPANY_NAME",
    "CIN_OR_UDYAM_NO", "INCORPORATION_DATE", "AUTHORIZED_CAPITAL",
    "DIRECTOR_NAMES", "EMAIL", "PHONE", "ADDRESS",
    "HAS_GST", "GEM_REGISTERED", "BANK_PRODUCT", "SCORE",
]

UDYAM_MFG_RESOURCE = "091a8776-fa68-4f36-9b8c-8c3b3e4d8b2a"
UDYAM_SVC_RESOURCE = "district-wise-services-msme"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html,*/*",
}

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _print_section(title):
    bar = "═" * 60
    print(f"\n{BOLD}{CYAN}{bar}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{bar}{RESET}")


def _ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def _warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def _err(msg):  print(f"  {RED}✗{RESET} {msg}")
def _info(msg): print(f"  {CYAN}→{RESET} {msg}")


def _get(url, params=None, retries=MAX_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r
            _warn(f"Attempt {attempt}: HTTP {r.status_code} — {url[:70]}")
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt)
            elif r.status_code == 403:
                _warn("403 Forbidden — server is blocking this request.")
                return None
        except requests.RequestException as e:
            _warn(f"Attempt {attempt}: {e}")
            time.sleep(2 ** attempt)
    return None


def _infer_sector(text):
    t = (text or "").lower()
    if any(k in t for k in ("manufactur","production","processing","fabricat","mill","pack")):
        return "Manufacturing"
    if any(k in t for k in ("service","consult","it ","software","tech","digital","health","edu")):
        return "Services"
    if any(k in t for k in ("trade","wholesale","retail","import","export","distribut","merchant")):
        return "Trading"
    if any(k in t for k in ("construct","infra","civil","build","contract")):
        return "Construction"
    return "Other"


def _parse_capital(val):
    try:
        return float(str(val).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _parse_date(val):
    if not val or str(val).strip() in ("", "nan", "NaT", "None"):
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y",
                "%Y/%m/%d", "%b %d, %Y", "%d %b %Y", "%d/%m/%y"):
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except ValueError:
            pass
    return None


# ══════════════════════════════════════════════════════════════
#  TASK 1 — MCA21 COMPANY DATA
# ══════════════════════════════════════════════════════════════

def _normalise_mca(raw, district):
    return {
        "SOURCE":             "MCA21",
        "DISTRICT":           district,
        "TALUK":              raw.get("registeredOfficeCity", ""),
        "SECTOR":             _infer_sector(raw.get("mainDivisionDescription", "")),
        "COMPANY_NAME":       raw.get("companyName", raw.get("company_name", "")),
        "CIN_OR_UDYAM_NO":    raw.get("cin", raw.get("CIN", "")),
        "INCORPORATION_DATE": raw.get("dateOfIncorporation", raw.get("date_of_incorporation", "")),
        "AUTHORIZED_CAPITAL": _parse_capital(raw.get("authorisedCapital", raw.get("authorized_capital", 0))),
        "DIRECTOR_NAMES":     raw.get("directors", raw.get("directorNames", "")),
        "EMAIL":              raw.get("email", raw.get("emailId", "")),
        "PHONE":              raw.get("phone", ""),
        "ADDRESS":            raw.get("registeredAddress", raw.get("registered_address", "")),
        "HAS_GST":            "",
        "GEM_REGISTERED":     False,
        "BANK_PRODUCT":       "",
        "SCORE":              0,
    }


def fetch_mca():
    _print_section("TASK 1 — MCA21 Company Registrations")
    all_records = []

    for district in DISTRICTS:
        _info(f"Fetching district: {district}")
        records = []

        # Try V3 API
        page, size = 1, 100
        while True:
            params = {"state": STATE, "district": district,
                      "offset": (page - 1) * size, "limit": size}
            r = _get("https://api.mca.gov.in/MCA21_SFTP/V2/MasterData/CompanyMasterData", params)
            if r is None:
                break
            try:
                payload = r.json()
            except Exception:
                break
            companies = (payload.get("data") or payload.get("companyDetails")
                         or (payload if isinstance(payload, list) else []))
            if not companies:
                break
            for c in companies:
                records.append(_normalise_mca(c, district))
            if len(companies) < size:
                break
            page += 1
            time.sleep(API_SLEEP)

        # Fallback: public MCA search portal scrape
        if not records:
            _warn("API empty — trying portal scrape ...")
            r = _get("https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do")
            if r:
                soup = BeautifulSoup(r.text, "lxml")
                table = soup.find("table", {"id": "CompanyList"}) or soup.find("table")
                if table:
                    hdrs = [th.get_text(strip=True) for th in table.find_all("th")]
                    for tr in table.find_all("tr")[1:]:
                        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                        if len(cells) < 3:
                            continue
                        raw = dict(zip(hdrs, cells))
                        records.append({
                            "SOURCE": "MCA21", "DISTRICT": district,
                            "TALUK": "", "SECTOR": _infer_sector(raw.get("Main Division Description", "")),
                            "COMPANY_NAME": raw.get("Company Name", ""),
                            "CIN_OR_UDYAM_NO": raw.get("CIN", ""),
                            "INCORPORATION_DATE": raw.get("Date of Incorporation", ""),
                            "AUTHORIZED_CAPITAL": _parse_capital(raw.get("Authorized Capital (Rs)", 0)),
                            "DIRECTOR_NAMES": raw.get("Director Names", ""),
                            "EMAIL": raw.get("Email", ""), "PHONE": raw.get("Phone", ""),
                            "ADDRESS": raw.get("Registered Address", ""),
                            "HAS_GST": "", "GEM_REGISTERED": False,
                            "BANK_PRODUCT": "", "SCORE": 0,
                        })

        if records:
            all_records.extend(records)
            _ok(f"{len(records)} companies — {district}")
        else:
            _err(f"No data for {district} (API + scrape both failed)")

        time.sleep(API_SLEEP)

    if not all_records:
        _warn("No MCA records collected.")
        return pd.DataFrame(columns=MASTER_COLUMNS)

    df = pd.DataFrame(all_records).drop_duplicates(subset=["CIN_OR_UDYAM_NO"], keep="first")
    df = df[df["CIN_OR_UDYAM_NO"].str.strip() != ""]
    df.to_csv(MCA_CSV, index=False, encoding="utf-8-sig")
    df.to_json(MCA_JSON, orient="records", indent=2, force_ascii=False)
    _ok(f"Saved {len(df)} companies → {MCA_CSV.name}")
    return df


# ══════════════════════════════════════════════════════════════
#  TASK 2 — UDYAM MSME DATA
# ══════════════════════════════════════════════════════════════

def _normalise_udyam(row, district, sector):
    name  = (row.get("enterprise_name") or row.get("name_of_enterprise")
             or row.get("enterpriseName", ""))
    udyam = (row.get("udyam_registration_number") or row.get("udyam_no")
             or row.get("registration_number", ""))
    email = row.get("email") or row.get("email_id", "")
    phone = row.get("mobile") or row.get("phone") or row.get("contact_number", "")
    date  = (row.get("date_of_commencement_of_production")
             or row.get("registration_date") or row.get("date_of_registration", ""))
    return {
        "SOURCE": "Udyam", "DISTRICT": district,
        "TALUK": row.get("taluk", row.get("block", "")),
        "SECTOR": sector, "COMPANY_NAME": name,
        "CIN_OR_UDYAM_NO": udyam, "INCORPORATION_DATE": date,
        "AUTHORIZED_CAPITAL": 0.0,
        "DIRECTOR_NAMES": row.get("name_of_entrepreneur", row.get("owner_name", "")),
        "EMAIL": email, "PHONE": phone,
        "ADDRESS": row.get("address", row.get("registered_address", "")),
        "HAS_GST": str(bool(row.get("gst_number", row.get("gstin", "")))).lower(),
        "GEM_REGISTERED": False, "BANK_PRODUCT": "", "SCORE": 0,
    }


def _fetch_udyam_resource(resource_id, sector):
    if not DATA_GOV_API_KEY:
        _err("DATA_GOV_API_KEY not set — skipping Udyam")
        return pd.DataFrame()

    all_records, offset, limit = [], 0, 500
    while True:
        params = {
            "api-key": DATA_GOV_API_KEY, "format": "json",
            "offset": offset, "limit": limit,
            "filters[state]": STATE,
        }
        r = _get(f"https://api.data.gov.in/resource/{resource_id}", params)
        if r is None:
            break
        try:
            payload = r.json()
        except Exception:
            break

        records = payload.get("records", [])
        total   = int(payload.get("total", 0))

        for row in records:
            dist_field = (row.get("district") or row.get("district_name", "")).strip().title()
            for target in DISTRICTS:
                if target.lower() in dist_field.lower():
                    all_records.append(_normalise_udyam(row, target, sector))
                    break

        _info(f"[{sector}] offset={offset}: {len(records)} rows | matched: {len(all_records)}/{total}")
        if offset + len(records) >= total or not records:
            break
        offset += limit
        time.sleep(API_SLEEP)

    return pd.DataFrame(all_records) if all_records else pd.DataFrame()


def fetch_udyam():
    _print_section("TASK 2 — Udyam MSME Registrations")
    results = {}

    for sector, resource_id, out_path in [
        ("Manufacturing", UDYAM_MFG_RESOURCE, UDYAM_MFG_CSV),
        ("Services",      UDYAM_SVC_RESOURCE, UDYAM_SVC_CSV),
    ]:
        _info(f"Fetching {sector} ...")
        df = _fetch_udyam_resource(resource_id, sector)

        if df.empty:
            # Per-district fallback
            frames = []
            for district in DISTRICTS:
                params = {
                    "api-key": DATA_GOV_API_KEY, "format": "json",
                    "limit": 500, "filters[state]": STATE,
                    "filters[district]": district,
                }
                r = _get(f"https://api.data.gov.in/resource/{resource_id}", params)
                if r:
                    try:
                        rows = r.json().get("records", [])
                        for row in rows:
                            frames.append(_normalise_udyam(row, district, sector))
                    except Exception:
                        pass
                time.sleep(API_SLEEP)
            df = pd.DataFrame(frames) if frames else pd.DataFrame()

        if not df.empty:
            df = df.drop_duplicates(subset=["CIN_OR_UDYAM_NO"], keep="first")
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            _ok(f"{len(df)} records → {out_path.name}")
        else:
            _err(f"No {sector} MSME data — check API key / IP whitelist")

        results[sector] = df

    return results.get("Manufacturing", pd.DataFrame()), results.get("Services", pd.DataFrame())


# ══════════════════════════════════════════════════════════════
#  TASK 3 — GeM PORTAL SELLERS
# ══════════════════════════════════════════════════════════════

def _normalise_gem(row, district):
    return {
        "SOURCE": "GeM", "DISTRICT": district,
        "TALUK": row.get("city", row.get("taluk", "")),
        "SECTOR": _infer_sector(row.get("category", row.get("sellerCategory", ""))),
        "COMPANY_NAME": (row.get("businessName") or row.get("business_name")
                         or row.get("sellerName", "")),
        "CIN_OR_UDYAM_NO": row.get("cin", row.get("udyam", row.get("gstin", ""))),
        "INCORPORATION_DATE": row.get("registrationDate", row.get("reg_date", "")),
        "AUTHORIZED_CAPITAL": 0.0,
        "DIRECTOR_NAMES": row.get("ownerName", row.get("owner_name", "")),
        "EMAIL": row.get("email", ""),
        "PHONE": row.get("contact", row.get("mobile", row.get("phone", ""))),
        "ADDRESS": row.get("address", row.get("registeredAddress", "")),
        "HAS_GST": str(bool(row.get("gstin", row.get("gst", "")))).lower(),
        "GEM_REGISTERED": True, "BANK_PRODUCT": "", "SCORE": 0,
    }


def fetch_gem():
    _print_section("TASK 3 — GeM Portal Sellers")
    all_records = []

    for district in DISTRICTS:
        _info(f"Fetching district: {district}")
        records = []

        # Try REST API
        page, size = 1, 50
        while True:
            params = {"state": "Tamil+Nadu", "district": district,
                      "page": page, "size": size}
            r = _get("https://mkp.gem.gov.in/api/v2/sellers", params)
            if r is None:
                break
            try:
                payload = r.json()
            except Exception:
                break
            sellers = (payload.get("data") or payload.get("sellers")
                       or payload.get("content")
                       or (payload if isinstance(payload, list) else []))
            if not sellers:
                break
            for s in sellers:
                records.append(_normalise_gem(s, district))
            total_pages = payload.get("totalPages", payload.get("total_pages", 1))
            if page >= total_pages or len(sellers) < size:
                break
            page += 1
            time.sleep(API_SLEEP)

        # Fallback: scrape public listing
        if not records:
            _warn("API empty — trying HTML scrape ...")
            scrape_urls = [
                f"https://gem.gov.in/sellers?state=Tamil+Nadu&district={district.replace(' ', '+')}",
                f"https://mkp.gem.gov.in/sellers?state=Tamil+Nadu&district={district.replace(' ', '+')}",
            ]
            for url in scrape_urls:
                r = _get(url)
                if r is None:
                    continue
                soup = BeautifulSoup(r.text, "lxml")
                # Check for embedded JSON
                for script in soup.find_all("script"):
                    text = script.string or ""
                    match = re.search(r'"sellers"\s*:\s*(\[.*?\])', text, re.DOTALL)
                    if match:
                        try:
                            for s in json.loads(match.group(1)):
                                records.append(_normalise_gem(s, district))
                            break
                        except json.JSONDecodeError:
                            pass
                # Check for HTML table
                table = soup.find("table")
                if table and not records:
                    hdrs = [th.get_text(strip=True) for th in table.find_all("th")]
                    for tr in table.find_all("tr")[1:]:
                        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                        if len(cells) < 2:
                            continue
                        raw = dict(zip(hdrs, cells))
                        records.append({
                            "SOURCE": "GeM", "DISTRICT": district, "TALUK": "",
                            "SECTOR": _infer_sector(raw.get("Category", "")),
                            "COMPANY_NAME": raw.get("Business Name", raw.get("Seller Name", "")),
                            "CIN_OR_UDYAM_NO": raw.get("GSTIN", raw.get("CIN", "")),
                            "INCORPORATION_DATE": raw.get("Registration Date", ""),
                            "AUTHORIZED_CAPITAL": 0.0,
                            "DIRECTOR_NAMES": raw.get("Owner", ""),
                            "EMAIL": raw.get("Email", ""), "PHONE": raw.get("Contact", ""),
                            "ADDRESS": raw.get("Address", ""),
                            "HAS_GST": "true" if raw.get("GSTIN") else "false",
                            "GEM_REGISTERED": True, "BANK_PRODUCT": "", "SCORE": 0,
                        })
                if records:
                    break

        if records:
            all_records.extend(records)
            _ok(f"{len(records)} sellers — {district}")
        else:
            _err(f"No GeM data for {district}")

        time.sleep(API_SLEEP)

    if not all_records:
        _warn("No GeM records collected.")
        return pd.DataFrame(columns=MASTER_COLUMNS)

    df = pd.DataFrame(all_records).drop_duplicates(
        subset=["COMPANY_NAME", "DISTRICT"], keep="first"
    )
    df.to_csv(GEM_CSV, index=False, encoding="utf-8-sig")
    _ok(f"Saved {len(df)} GeM sellers → {GEM_CSV.name}")
    return df


# ══════════════════════════════════════════════════════════════
#  TASK 4 — SCORE & MERGE
# ══════════════════════════════════════════════════════════════

def _score(row):
    s = 0
    cap = _parse_capital(row.get("AUTHORIZED_CAPITAL", 0))
    if cap > 1_000_000:
        s += SCORING["authorized_capital_above_10L"]
    d = _parse_date(row.get("INCORPORATION_DATE", ""))
    if d and d >= datetime(2024, 1, 1):
        s += SCORING["incorporated_after_jan_2024"]
    if str(row.get("HAS_GST", "")).strip().lower() in ("true", "yes", "1", "y"):
        s += SCORING["has_gst"]
    sector = str(row.get("SECTOR", "")).lower()
    if "manufactur" in sector:
        s += SCORING["sector_manufacturing"]
    elif sector in ("services", "technology", "it"):
        s += SCORING["sector_services"]
    gem = row.get("GEM_REGISTERED", False)
    if gem is True or str(gem).lower() in ("true", "yes", "1"):
        s += SCORING["gem_registered"]
    has_email = str(row.get("EMAIL", "")).strip() not in ("", "nan", "None")
    has_phone = str(row.get("PHONE", "")).strip() not in ("", "nan", "None")
    if has_email or has_phone:
        s += SCORING["has_contact_info"]
    return round(min(s / SCORE_RAW_MAX * 100, 100))


def _product(row):
    sector = str(row.get("SECTOR", "")).title()
    for key in BANK_PRODUCTS:
        if key.lower() in sector.lower():
            return BANK_PRODUCTS[key]
    return BANK_PRODUCTS["Other"]


def _export_xlsx(df):
    df.to_excel(MASTER_XLSX, index=False, engine="openpyxl")
    wb = openpyxl.load_workbook(MASTER_XLSX)
    ws = wb.active
    ws.title = "Master Leads"

    header_fill = PatternFill("solid", fgColor="003366")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, col in enumerate(df.columns, 1):
        max_len = max(len(str(col)),
                      df[col].astype(str).str.len().max() if len(df) > 0 else 0)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 45)

    score_col = list(df.columns).index("SCORE") + 1
    score_letter = get_column_letter(score_col)
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for row_idx in range(2, ws.max_row + 1):
        cell = ws[f"{score_letter}{row_idx}"]
        try:
            val = int(cell.value or 0)
        except (ValueError, TypeError):
            val = 0
        if val >= 75:
            cell.fill = PatternFill("solid", fgColor="00B050")
            cell.font = Font(bold=True, color="FFFFFF")
        elif val >= 50:
            cell.fill = PatternFill("solid", fgColor="FFC000")
        else:
            cell.fill = PatternFill("solid", fgColor="FF4444")
            cell.font = Font(color="FFFFFF")
        for c in ws[row_idx]:
            c.border = border
            if c.column != score_col:
                c.alignment = Alignment(wrap_text=True, vertical="top")

    ws.freeze_panes = "A2"
    wb.save(MASTER_XLSX)


def score_and_merge(df_mca, df_mfg, df_svc, df_gem):
    _print_section("TASK 4 — Scoring & Building Master Leads")

    frames = []
    for label, df in [("MCA", df_mca), ("MFG", df_mfg), ("SVC", df_svc), ("GeM", df_gem)]:
        if df is not None and not df.empty:
            frames.append(df)
            _ok(f"{label}: {len(df)} records added")
        else:
            _warn(f"{label}: 0 records")

    if not frames:
        _err("No data from any source.")
        return pd.DataFrame(columns=MASTER_COLUMNS)

    master = pd.concat(frames, ignore_index=True)
    for col in MASTER_COLUMNS:
        if col not in master.columns:
            master[col] = ""

    master = master[master["COMPANY_NAME"].astype(str).str.strip() != ""]
    master = master.drop_duplicates(subset=["CIN_OR_UDYAM_NO", "DISTRICT"], keep="first")

    _info(f"Scoring {len(master)} leads ...")
    master["SCORE"]        = master.apply(_score, axis=1)
    master["BANK_PRODUCT"] = master.apply(_product, axis=1)
    master = master.sort_values("SCORE", ascending=False).reset_index(drop=True)

    extra = [c for c in master.columns if c not in MASTER_COLUMNS]
    master = master[MASTER_COLUMNS + extra]

    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    _ok(f"Saved CSV  → {MASTER_CSV.name}")

    _export_xlsx(master)
    _ok(f"Saved XLSX → {MASTER_XLSX.name}")

    high   = (master["SCORE"] >= 75).sum()
    medium = ((master["SCORE"] >= 50) & (master["SCORE"] < 75)).sum()
    low    = (master["SCORE"] < 50).sum()

    bar = "─" * 58
    print(f"\n{BOLD}  LEAD SUMMARY{RESET}")
    print(f"  {bar}")
    print(f"  Total leads      : {BOLD}{len(master)}{RESET}")
    print(f"  {GREEN}High  (≥75){RESET}      : {high}")
    print(f"  {YELLOW}Medium (50-74){RESET}   : {medium}")
    print(f"  {RED}Low   (<50){RESET}      : {low}")
    print(f"  {bar}")
    print(f"  By district:")
    for d in DISTRICTS:
        print(f"    {d:<22} {(master['DISTRICT']==d).sum()}")
    print(f"  {bar}")
    print(f"  {BOLD}TOP 5 LEADS:{RESET}")
    for i, (_, r) in enumerate(master.head(5).iterrows(), 1):
        color = GREEN if r["SCORE"] >= 75 else YELLOW
        print(f"  {i}. {color}{r['SCORE']:>3}/100{RESET}  "
              f"{r['COMPANY_NAME'][:38]:<38}  "
              f"{r['DISTRICT']:<16}  {r['SECTOR']}")
    print(f"  {bar}\n")

    return master


# ══════════════════════════════════════════════════════════════
#  TASK 5 — GOOGLE SHEETS PUSH
# ══════════════════════════════════════════════════════════════

def push_to_sheets(df):
    _print_section("TASK 5 — Pushing to Google Sheets")

    sa_path = Path(GOOGLE_SERVICE_ACCOUNT_JSON)
    if not sa_path.exists():
        # Also check next to this script
        sa_path = BASE_DIR / "service_account.json"
    if not sa_path.exists():
        _err(
            f"service_account.json not found.\n"
            f"    Put it next to this script: {BASE_DIR / 'service_account.json'}"
        )
        return 0

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        _err("gspread not installed — run pip install gspread google-auth")
        return 0

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        creds  = Credentials.from_service_account_file(str(sa_path), scopes=scopes)
        client = gspread.authorize(creds)
        _ok(f"Authenticated as {creds.service_account_email}")
    except Exception as e:
        _err(f"Auth failed: {e}")
        return 0

    # Open or create sheet
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
        _ok(f"Opened sheet: \"{GOOGLE_SHEET_NAME}\"")
    except gspread.SpreadsheetNotFound:
        _info("Sheet not found — creating ...")
        sh = client.create(GOOGLE_SHEET_NAME)
        sh.share("", perm_type="anyone", role="reader")
        _ok(f"Created sheet: {sh.url}")

    try:
        ws = sh.worksheet("Leads")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Leads", rows=10000, cols=30)

    # Timestamp in A1
    now_str = datetime.now().strftime("Last sync: %d-%b-%Y %I:%M %p")
    ws.update([[now_str]], "A1")

    # Headers in row 2
    headers = list(df.columns)
    existing_headers = ws.row_values(2)
    if existing_headers != headers:
        ws.update("A2", [headers])

    # Existing CINs to skip duplicates
    try:
        existing_hdrs = ws.row_values(2)
        cin_col = (existing_hdrs.index("CIN_OR_UDYAM_NO") + 1
                   if "CIN_OR_UDYAM_NO" in existing_hdrs else 6)
        known = set(v.strip() for v in ws.col_values(cin_col)[2:] if v.strip())
    except Exception:
        known = set()

    _info(f"Sheet already has {len(known)} known IDs")

    new_df = df[~df["CIN_OR_UDYAM_NO"].astype(str).str.strip().isin(known)]
    if new_df.empty:
        _ok("No new rows — sheet is already up to date.")
        return 0

    rows = new_df.fillna("").astype(str).values.tolist()
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    _ok(f"{len(rows)} new rows pushed to \"{GOOGLE_SHEET_NAME}\"")
    print(f"\n  {BOLD}{CYAN}Sheet URL:{RESET} {sh.url}\n")
    return len(rows)


# ══════════════════════════════════════════════════════════════
#  TASK 6 — EMAIL ALERT
# ══════════════════════════════════════════════════════════════

def send_email(summary):
    if not all([ALERT_EMAIL_SENDER, ALERT_EMAIL_PASSWORD, ALERT_EMAIL_RECIPIENT]):
        _warn("Email alert skipped — fill ALERT_EMAIL_SENDER/PASSWORD/RECIPIENT at top of file")
        return

    date_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    top5_text = "\n".join(
        f"  {i+1}. {r.get('COMPANY_NAME','')[:40]} | {r.get('DISTRICT','')} | Score: {r.get('SCORE',0)}"
        for i, r in enumerate(summary.get("top5", []))
    ) or "  (no data)"

    body = (
        f"IOB Nagapattinam RO — Daily Lead Sync  |  {date_str}\n"
        f"{'─'*60}\n"
        f"New MCA Companies : {summary['mca']}\n"
        f"New Udyam MSMEs   : {summary['msme']}\n"
        f"New GeM Sellers   : {summary['gem']}\n"
        f"Total Master Leads: {summary['total']}\n\n"
        f"TOP 5 LEADS:\n{top5_text}\n\n"
        f"Open Google Sheet: {GOOGLE_SHEET_NAME}\n"
        f"{'─'*60}\n"
        f"This is an automated message from the IOB Lead Generation System."
    )

    msg = MIMEMultipart()
    msg["From"]    = ALERT_EMAIL_SENDER
    msg["To"]      = ALERT_EMAIL_RECIPIENT
    msg["Subject"] = (f"IOB Nagapattinam RO — Lead Sync: "
                      f"{summary['mca']} MCA + {summary['msme']} MSME "
                      f"+ {summary['gem']} GeM  [{date_str}]")
    msg.attach(MIMEText(body, "plain"))

    # Attach master_leads.csv
    if MASTER_CSV.exists():
        with open(MASTER_CSV, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f'attachment; filename="master_leads_{datetime.now().strftime("%Y%m%d")}.csv"')
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo(); s.starttls(); s.login(ALERT_EMAIL_SENDER, ALERT_EMAIL_PASSWORD)
            s.sendmail(ALERT_EMAIL_SENDER, ALERT_EMAIL_RECIPIENT, msg.as_string())
        _ok(f"Email sent to {ALERT_EMAIL_RECIPIENT}")
    except Exception as e:
        _err(f"Email failed: {e}")


# ══════════════════════════════════════════════════════════════
#  MAIN — RUN FULL PIPELINE
# ══════════════════════════════════════════════════════════════

BANNER = f"""
{BOLD}{CYAN}
╔══════════════════════════════════════════════════════════════╗
║   Indian Overseas Bank — Nagapattinam Regional Office        ║
║          Automated Lead Generation Pipeline                  ║
║   Districts: Nagapattinam | Thiruvarur | Mayiladuthurai       ║
╚══════════════════════════════════════════════════════════════╝
{RESET}"""


def run():
    print(BANNER)
    logger.info("Pipeline started — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    start = time.time()

    try:
        df_mca              = fetch_mca()
        df_mfg, df_svc      = fetch_udyam()
        df_gem              = fetch_gem()
        master              = score_and_merge(df_mca, df_mfg, df_svc, df_gem)
        sheets_new          = push_to_sheets(master)
    except Exception as e:
        _err(f"Pipeline error: {e}")
        traceback.print_exc()
        logger.exception("Pipeline crashed: %s", e)
        input("\nPress Enter to exit ...")
        return

    elapsed = round(time.time() - start, 1)

    _print_section("TASK 6 — Email Alert")
    summary = {
        "mca":   len(df_mca),
        "msme":  len(df_mfg) + len(df_svc),
        "gem":   len(df_gem),
        "total": len(master),
        "top5":  master.head(5).to_dict("records") if not master.empty else [],
    }
    send_email(summary)

    logger.info(
        "Pipeline complete in %ss — MCA:%d MSME:%d GeM:%d Total:%d Sheets_new:%d",
        elapsed, summary["mca"], summary["msme"],
        summary["gem"], summary["total"], sheets_new,
    )

    bar = "═" * 60
    print(f"\n{BOLD}{GREEN}{bar}{RESET}")
    print(f"{BOLD}{GREEN}  PIPELINE COMPLETE  —  {elapsed}s{RESET}")
    print(f"{BOLD}{GREEN}{bar}{RESET}")
    print(f"  CSV  : {MASTER_CSV}")
    print(f"  XLSX : {MASTER_XLSX}")
    print(f"  Log  : {LOG_FILE}")
    print(f"{BOLD}{GREEN}{bar}{RESET}\n")

    try:
        input("Press Enter to exit ...")
    except (EOFError, KeyboardInterrupt):
        pass


# ══════════════════════════════════════════════════════════════
#  SCHEDULER — OPTIONAL (runs pipeline daily at 6 AM)
# ══════════════════════════════════════════════════════════════

def start_scheduler():
    """Call this instead of run() if you want the 6 AM daily scheduler."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        _install("apscheduler")
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        run,
        trigger=CronTrigger(hour=SCHEDULE_HOUR, minute=0, timezone="Asia/Kolkata"),
        id="iob_leads",
        misfire_grace_time=3600,
        coalesce=True,
    )
    print(f"\n{BOLD}Scheduler started — pipeline runs daily at {SCHEDULE_HOUR:02d}:00 IST.{RESET}")
    print("Press Ctrl+C to stop.\n")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler stopped.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="IOB Nagapattinam Lead Pipeline")
    parser.add_argument("--schedule", action="store_true",
                        help="Run as 6AM daily scheduler instead of one-shot")
    args = parser.parse_args()

    if args.schedule:
        start_scheduler()
    else:
        run()
