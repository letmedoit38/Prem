#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║    Indian Overseas Bank — Nagapattinam Regional Office           ║
║    Lead Generation Pipeline  ·  STANDALONE SINGLE-FILE EDITION  ║
║    Districts: Nagapattinam | Thiruvarur | Mayiladuthurai          ║
║                                                                  ║
║    SETUP (one time only):                                        ║
║      1. Install Python 3.10+  →  python.org/downloads           ║
║         (tick "Add Python to PATH" during install)               ║
║      2. Save this file anywhere on your laptop                   ║
║      3. Double-click the file  OR  open Command Prompt and run:  ║
║           python iob_leads_standalone.py                         ║
║                                                                  ║
║    DAILY SCHEDULER (auto-run every 6 AM):                        ║
║      python iob_leads_standalone.py --schedule                   ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ════════════════════════════════════════════════════════════════════
#   SECTION A — YOUR CREDENTIALS  (already filled in)
# ════════════════════════════════════════════════════════════════════

DATA_GOV_API_KEY  = "579b464db66ec23bdd000001700d8e38f4594084504affde913115ef"
GOOGLE_SHEET_NAME = "Nagapattinam RO - Live Leads"

# Google service-account credentials — embedded directly (no separate file needed)
SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "iob-nagapattinam-ro",
    "private_key_id": "9ef19e9ac2bd72a8ac001c751b60e00ecf7b651a",
    "private_key": (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDd/Ku5P+oFHTEg\n"
        "JB0XTmiXulMLywqR/Ni5NvzZ9OleXEfHG0+K2rcEvt81oTYbuKUhSD6kPsFjgbnr\n"
        "00hKOftA0A06frECQBmTlPHguS7Yu+vg2B0HkmGlHgfokHc+YY2gwI5Rwdl99z68\n"
        "NFhb8cczkTqO3uPF6V6KEbp1fI1tbIqhkHHyPyI7K5L0m/CNvAWcFohS9Gz4M1Gw\n"
        "CmwyFWp6nlNdioeLZJa26MoUnoqRwwUmuaeLsFkF2HUJtGTurY2OvG6uC7E/Gi/O\n"
        "NzBM00a81xLUmmLEke1ZAmlUk+sXORimmkSmcnRP5CezyvJ/ZTSUDxVejEUB8HDD\n"
        "/34z1rodAgMBAAECggEANzhHxVy7S4tf8YVaQTZteTTNvLTEy9zwUl511ogAV0sw\n"
        "Rbyq9DkE5ubOIoqYKZwsY5OTlYrQ035tL9cOd/xlXlGCwObMBGnKkvYtlv+pwhs5\n"
        "CWTpD72fkZHfWMA7EWb18qODo53LivSqg+mngzOpIFBDl0+lrFEphcH0No6Fpc6w\n"
        "FYRJmU6iKld0JJ4J9z2rbXgfKHKr63AGDhQTqMPsTe1+TVvMmc+meudDkMHvNUhs\n"
        "klwMAzNF1syXA9lquyoh1oxyIU44wVVbZLAdC/+f26uSI0w236WVukODdCvPWBro\n"
        "HYCzzCQ6yQhdGeS+d0G5pfM52SJEzLTulcAxF4hbsQKBgQD447arpCSzZAdSv7rA\n"
        "qdmqyWcPS4WrSfb9Dt+mUpZmT75icVKyJRD4yy1aUVTB2W5VjuToW3EXXU8687Bg\n"
        "j84hBYsLSvtEbIvAX2DmTGCeOBVm8NT+zhQuf14qeGQLy8NzxwShustii9rV9nyL\n"
        "Ru4OXSJmuZzG5qd2/gfsczCmhQKBgQDkVDPAbDvfiL/yibB1gWpra0OTHmCoQWv9\n"
        "WZ0gi5fXgJfoRct/mqE3ky+z8gdOM3DuJFk2YwzPQpGpkjp3YwM+I2KbWVKc3YPx\n"
        "Kdxs4GktBE5h2AD/LrWAWqmUyN43P83MQBdCydvtXqOZq+DUP00XCOSRHeUPFgFT\n"
        "XVM1E7wUuQKBgQDqXAnzP6HrZcJbkfx5VLaI0hMAXP3mF8TB7xJ7nALRHj/IlKro\n"
        "4mxDyZXQGQt1aZcya1Zy0UABXzSu7y5jDqZrg7u1C4rkmE1T/LvSv5KvCWJlx1rZ\n"
        "ABYS3o498ZVLYjiOOZXL8Id5KPYMSYhm4Yhh8CLnldnhlOmV64hsht8FvQKBgBiS\n"
        "i0NBIqxq3iVu9gOfWuGWmJ4jncldyQ5p74QKIdw6ZZ7ErCLedE0z1OVrvaeH17Z5\n"
        "SPSWclF3249BQnOIv1eXnUwUr9Rb7pAsriE1gXwrw3e6NFlCIJxgpXFysJ+HiVFa\n"
        "8GXqrXV9QuQN4FNXQKei+F45tmYKOzhKieLjbdFZAoGBAMpInJPc/0qpzQ1h5h58\n"
        "g6+NNoqrfsEK4C+9DIAXdV+RgW5fpgOwGr4CnMTKJGZ+AB3bWqHcyoTCDKk9iFNx\n"
        "ZXnqFJTYro4EWhPgHJNLjJo3S+L6a6Sjh0fJnQlYIRMoXEi53lXeId8NTalD3kLm\n"
        "1QTivByJkgSPo676Q6yD1Qyj\n"
        "-----END PRIVATE KEY-----\n"
    ),
    "client_email": "iob-leads-bot@iob-nagapattinam-ro.iam.gserviceaccount.com",
    "client_id": "101541550809066138769",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": (
        "https://www.googleapis.com/robot/v1/metadata/x509/"
        "iob-leads-bot%40iob-nagapattinam-ro.iam.gserviceaccount.com"
    ),
    "universe_domain": "googleapis.com",
}

# ════════════════════════════════════════════════════════════════════
#   SECTION B — OPTIONAL EMAIL ALERTS  (fill in to enable)
# ════════════════════════════════════════════════════════════════════

ALERT_EMAIL_SENDER    = ""   # e.g. your.name@iob.in
ALERT_EMAIL_PASSWORD  = ""   # Gmail App Password (not your main password)
ALERT_EMAIL_RECIPIENT = ""   # who gets the daily report e.g. rm@iob.in
SMTP_HOST             = "smtp.gmail.com"
SMTP_PORT             = 587

# ════════════════════════════════════════════════════════════════════
#   SECTION C — PIPELINE SETTINGS  (no need to change)
# ════════════════════════════════════════════════════════════════════

DISTRICTS     = ["Nagapattinam", "Thiruvarur", "Mayiladuthurai"]
STATE         = "Tamil Nadu"
API_SLEEP     = 2        # polite delay between API calls (seconds)
MAX_RETRIES   = 3
SCHEDULE_HOUR = 6        # auto-run at 6:00 AM IST

UDYAM_MFG_RESOURCE = "091a8776-fa68-4f36-9b8c-8c3b3e4d8b2a"
UDYAM_SVC_RESOURCE = "district-wise-services-msme"

SCORING = {
    "authorized_capital_above_10L": 20,
    "incorporated_after_jan_2024":  25,
    "has_gst":                      15,
    "sector_manufacturing":         20,
    "sector_services":              10,
    "gem_registered":               20,
    "has_contact_info":             10,
}
SCORE_RAW_MAX = sum(SCORING.values())

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

# ════════════════════════════════════════════════════════════════════
#   AUTO-INSTALL PACKAGES  (runs silently on first launch)
# ════════════════════════════════════════════════════════════════════

import sys, os

_PKGS = {
    "requests":      "requests",
    "pandas":        "pandas",
    "gspread":       "gspread",
    "google.oauth2": "google-auth",
    "openpyxl":      "openpyxl",
    "bs4":           "beautifulsoup4",
    "lxml":          "lxml",
    "apscheduler":   "apscheduler",
}

print("Checking packages ...", flush=True)
_missing = []
for _imp, _pkg in _PKGS.items():
    try:
        __import__(_imp)
    except ImportError:
        _missing.append(_pkg)

if _missing:
    print("\nMissing required packages. Install them with:\n")
    print(f"    pip install {' '.join(_missing)}\n")
    sys.exit(1)

print("All packages ready.\n")

# ════════════════════════════════════════════════════════════════════
#   IMPORTS
# ════════════════════════════════════════════════════════════════════

import json, time, logging, re, smtplib, traceback
from datetime import datetime
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

G = R = Y = C = B = RS = ""

# ════════════════════════════════════════════════════════════════════
#   OUTPUT PATHS  (data/ and logs/ folders next to this script)
# ════════════════════════════════════════════════════════════════════

BASE  = Path(__file__).parent
DATA  = BASE / "data";   DATA.mkdir(exist_ok=True)
LOGS  = BASE / "logs";   LOGS.mkdir(exist_ok=True)

LOG_FILE      = LOGS / "pipeline.log"
MCA_CSV       = DATA / "companies.csv"
MCA_JSON      = DATA / "companies.json"
MFG_CSV       = DATA / "msme_manufacturing.csv"
SVC_CSV       = DATA / "msme_services.csv"
GEM_CSV       = DATA / "gem_sellers.csv"
MASTER_CSV    = DATA / "master_leads.csv"
MASTER_XLSX   = DATA / "master_leads.xlsx"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("iob")

# ════════════════════════════════════════════════════════════════════
#   TINY UI HELPERS
# ════════════════════════════════════════════════════════════════════

def sec(t):  print(f"\n{B}{C}{'═'*62}\n  {t}\n{'═'*62}{RS}")
def ok(m):   print(f"  {G}✓{RS} {m}")
def warn(m): print(f"  {Y}⚠{RS}  {m}")
def err(m):  print(f"  {R}✗{RS} {m}")
def info(m): print(f"  {C}→{RS} {m}")

# ════════════════════════════════════════════════════════════════════
#   SHARED UTILITIES
# ════════════════════════════════════════════════════════════════════

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-IN,en;q=0.9",
}

def _get(url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=30)
            if r.status_code == 200:
                return r
            warn(f"HTTP {r.status_code} (attempt {attempt}) — {url[:65]}")
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt)
            elif r.status_code == 403:
                return None
        except requests.RequestException as e:
            warn(f"Network error (attempt {attempt}): {e}")
            time.sleep(2 ** attempt)
    return None

def _sector(text):
    t = (text or "").lower()
    if any(k in t for k in ("manufactur","production","processing","fabricat","mill","pack","forge","cast")):
        return "Manufacturing"
    if any(k in t for k in ("service","consult","software","tech","digital","health","educat","it ")):
        return "Services"
    if any(k in t for k in ("trade","wholesale","retail","import","export","distribut","merchant","supply")):
        return "Trading"
    if any(k in t for k in ("construct","infra","civil","build","contract","erect")):
        return "Construction"
    return "Other"

def _cap(v):
    try:   return float(str(v).replace(",","").strip() or 0)
    except: return 0.0

def _date(v):
    if not v or str(v).strip() in ("","nan","NaT","None"): return None
    for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y","%d-%b-%Y","%Y/%m/%d","%d %b %Y","%d/%m/%y"):
        try: return datetime.strptime(str(v).strip(), fmt)
        except: pass
    return None

# ════════════════════════════════════════════════════════════════════
#   TASK 1 — MCA21 COMPANY REGISTRATIONS
# ════════════════════════════════════════════════════════════════════

def _norm_mca(r, district):
    return {
        "SOURCE": "MCA21", "DISTRICT": district,
        "TALUK":  r.get("registeredOfficeCity",""),
        "SECTOR": _sector(r.get("mainDivisionDescription","")),
        "COMPANY_NAME":       r.get("companyName", r.get("company_name","")),
        "CIN_OR_UDYAM_NO":    r.get("cin", r.get("CIN","")),
        "INCORPORATION_DATE": r.get("dateOfIncorporation", r.get("date_of_incorporation","")),
        "AUTHORIZED_CAPITAL": _cap(r.get("authorisedCapital", r.get("authorized_capital",0))),
        "DIRECTOR_NAMES":     r.get("directors", r.get("directorNames","")),
        "EMAIL":   r.get("email", r.get("emailId","")),
        "PHONE":   r.get("phone",""),
        "ADDRESS": r.get("registeredAddress", r.get("registered_address","")),
        "HAS_GST": "", "GEM_REGISTERED": False, "BANK_PRODUCT": "", "SCORE": 0,
    }

def fetch_mca():
    sec("TASK 1 — MCA21 Company Registrations")
    all_rows = []

    for dist in DISTRICTS:
        info(f"District: {dist}")
        rows = []

        # Primary: MCA V3 API
        page = 1
        while True:
            r = _get("https://api.mca.gov.in/MCA21_SFTP/V2/MasterData/CompanyMasterData",
                     {"state": STATE, "district": dist,
                      "offset": (page-1)*100, "limit": 100})
            if not r: break
            try:    data = r.json()
            except: break
            cos = data.get("data") or data.get("companyDetails") or (data if isinstance(data,list) else [])
            if not cos: break
            for c in cos: rows.append(_norm_mca(c, dist))
            if len(cos) < 100: break
            page += 1;  time.sleep(API_SLEEP)

        # Fallback: MCA portal HTML scrape
        if not rows:
            warn("API empty — trying HTML scrape ...")
            r = _get("https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do")
            if r:
                soup = BeautifulSoup(r.text, "lxml")
                tbl  = soup.find("table", {"id":"CompanyList"}) or soup.find("table")
                if tbl:
                    hdrs = [th.get_text(strip=True) for th in tbl.find_all("th")]
                    for tr in tbl.find_all("tr")[1:]:
                        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                        if len(cells) < 3: continue
                        raw = dict(zip(hdrs, cells))
                        rows.append({
                            "SOURCE":"MCA21","DISTRICT":dist,"TALUK":"",
                            "SECTOR":_sector(raw.get("Main Division Description","")),
                            "COMPANY_NAME":raw.get("Company Name",""),
                            "CIN_OR_UDYAM_NO":raw.get("CIN",""),
                            "INCORPORATION_DATE":raw.get("Date of Incorporation",""),
                            "AUTHORIZED_CAPITAL":_cap(raw.get("Authorized Capital (Rs)",0)),
                            "DIRECTOR_NAMES":raw.get("Director Names",""),
                            "EMAIL":raw.get("Email",""),"PHONE":raw.get("Phone",""),
                            "ADDRESS":raw.get("Registered Address",""),
                            "HAS_GST":"","GEM_REGISTERED":False,"BANK_PRODUCT":"","SCORE":0,
                        })

        if rows:
            all_rows.extend(rows);  ok(f"{len(rows)} companies — {dist}")
        else:
            err(f"No MCA data for {dist}")
        time.sleep(API_SLEEP)

    if not all_rows:
        warn("No MCA records."); return pd.DataFrame(columns=MASTER_COLUMNS)

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["CIN_OR_UDYAM_NO"], keep="first")
    df = df[df["CIN_OR_UDYAM_NO"].str.strip() != ""]
    df.to_csv(MCA_CSV, index=False, encoding="utf-8-sig")
    df.to_json(MCA_JSON, orient="records", indent=2, force_ascii=False)
    ok(f"Saved {len(df)} companies → {MCA_CSV.name}")
    return df

# ════════════════════════════════════════════════════════════════════
#   TASK 2 — UDYAM MSME DATA
# ════════════════════════════════════════════════════════════════════

def _norm_udyam(r, dist, sector):
    name  = r.get("enterprise_name") or r.get("name_of_enterprise") or r.get("enterpriseName","")
    udyam = r.get("udyam_registration_number") or r.get("udyam_no") or r.get("registration_number","")
    return {
        "SOURCE":"Udyam","DISTRICT":dist,
        "TALUK": r.get("taluk", r.get("block","")),
        "SECTOR":sector, "COMPANY_NAME":name,
        "CIN_OR_UDYAM_NO":udyam,
        "INCORPORATION_DATE": r.get("date_of_commencement_of_production",
                               r.get("registration_date", r.get("date_of_registration",""))),
        "AUTHORIZED_CAPITAL":0.0,
        "DIRECTOR_NAMES": r.get("name_of_entrepreneur", r.get("owner_name","")),
        "EMAIL": r.get("email", r.get("email_id","")),
        "PHONE": r.get("mobile", r.get("phone", r.get("contact_number",""))),
        "ADDRESS": r.get("address", r.get("registered_address","")),
        "HAS_GST": str(bool(r.get("gst_number", r.get("gstin","")))).lower(),
        "GEM_REGISTERED":False,"BANK_PRODUCT":"","SCORE":0,
    }

def _udyam_resource(res_id, sector):
    if not DATA_GOV_API_KEY:
        err("DATA_GOV_API_KEY missing"); return pd.DataFrame()
    rows, offset = [], 0
    while True:
        r = _get(f"https://api.data.gov.in/resource/{res_id}",
                 {"api-key":DATA_GOV_API_KEY,"format":"json",
                  "offset":offset,"limit":500,"filters[state]":STATE})
        if not r: break
        try:    payload = r.json()
        except: break
        records = payload.get("records",[])
        total   = int(payload.get("total",0))
        for rec in records:
            df_val = (rec.get("district") or rec.get("district_name","")).strip().title()
            for tgt in DISTRICTS:
                if tgt.lower() in df_val.lower():
                    rows.append(_norm_udyam(rec, tgt, sector)); break
        info(f"[{sector}] offset={offset} | fetched={len(records)} | matched={len(rows)}/{total}")
        if offset + len(records) >= total or not records: break
        offset += 500;  time.sleep(API_SLEEP)
    return pd.DataFrame(rows) if rows else pd.DataFrame()

def fetch_udyam():
    sec("TASK 2 — Udyam MSME Registrations")
    out = {}
    for sector, res_id, path in [
        ("Manufacturing", UDYAM_MFG_RESOURCE, MFG_CSV),
        ("Services",      UDYAM_SVC_RESOURCE, SVC_CSV),
    ]:
        info(f"Fetching {sector} ...")
        df = _udyam_resource(res_id, sector)

        # Per-district fallback if bulk fetch empty
        if df.empty:
            frames = []
            for dist in DISTRICTS:
                r = _get(f"https://api.data.gov.in/resource/{res_id}",
                         {"api-key":DATA_GOV_API_KEY,"format":"json","limit":500,
                          "filters[state]":STATE,"filters[district]":dist})
                if r:
                    try:
                        for rec in r.json().get("records",[]):
                            frames.append(_norm_udyam(rec, dist, sector))
                    except: pass
                time.sleep(API_SLEEP)
            df = pd.DataFrame(frames) if frames else pd.DataFrame()

        if not df.empty:
            df = df.drop_duplicates(subset=["CIN_OR_UDYAM_NO"], keep="first")
            df.to_csv(path, index=False, encoding="utf-8-sig")
            ok(f"{len(df)} records → {path.name}")
        else:
            err(f"No {sector} data — check API key / IP whitelist at data.gov.in")
        out[sector] = df

    return out.get("Manufacturing", pd.DataFrame()), out.get("Services", pd.DataFrame())

# ════════════════════════════════════════════════════════════════════
#   TASK 3 — GeM PORTAL SELLERS
# ════════════════════════════════════════════════════════════════════

def _norm_gem(r, dist):
    return {
        "SOURCE":"GeM","DISTRICT":dist,
        "TALUK": r.get("city", r.get("taluk","")),
        "SECTOR":_sector(r.get("category", r.get("sellerCategory",""))),
        "COMPANY_NAME": r.get("businessName") or r.get("business_name") or r.get("sellerName",""),
        "CIN_OR_UDYAM_NO": r.get("cin", r.get("udyam", r.get("gstin",""))),
        "INCORPORATION_DATE": r.get("registrationDate", r.get("reg_date","")),
        "AUTHORIZED_CAPITAL":0.0,
        "DIRECTOR_NAMES": r.get("ownerName", r.get("owner_name","")),
        "EMAIL": r.get("email",""),
        "PHONE": r.get("contact", r.get("mobile", r.get("phone",""))),
        "ADDRESS": r.get("address", r.get("registeredAddress","")),
        "HAS_GST": str(bool(r.get("gstin", r.get("gst","")))).lower(),
        "GEM_REGISTERED":True,"BANK_PRODUCT":"","SCORE":0,
    }

def fetch_gem():
    sec("TASK 3 — GeM Portal Sellers")
    all_rows = []
    for dist in DISTRICTS:
        info(f"District: {dist}")
        rows = []

        # Primary: GeM REST API
        page = 1
        while True:
            r = _get("https://mkp.gem.gov.in/api/v2/sellers",
                     {"state":"Tamil+Nadu","district":dist,"page":page,"size":50})
            if not r: break
            try:    payload = r.json()
            except: break
            sellers = payload.get("data") or payload.get("sellers") or payload.get("content") or (payload if isinstance(payload,list) else [])
            if not sellers: break
            for s in sellers: rows.append(_norm_gem(s, dist))
            if page >= payload.get("totalPages", payload.get("total_pages",1)) or len(sellers) < 50: break
            page += 1;  time.sleep(API_SLEEP)

        # Fallback: public HTML scrape
        if not rows:
            warn("API empty — trying HTML scrape ...")
            for url in [
                f"https://gem.gov.in/sellers?state=Tamil+Nadu&district={dist.replace(' ','+')}",
                f"https://mkp.gem.gov.in/sellers?state=Tamil+Nadu&district={dist.replace(' ','+')}",
            ]:
                r = _get(url)
                if not r: continue
                soup = BeautifulSoup(r.text, "lxml")
                for script in soup.find_all("script"):
                    m = re.search(r'"sellers"\s*:\s*(\[.*?\])', script.string or "", re.DOTALL)
                    if m:
                        try:
                            for s in json.loads(m.group(1)):
                                rows.append(_norm_gem(s, dist))
                        except: pass
                tbl = soup.find("table")
                if tbl and not rows:
                    hdrs = [th.get_text(strip=True) for th in tbl.find_all("th")]
                    for tr in tbl.find_all("tr")[1:]:
                        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                        if len(cells) < 2: continue
                        raw = dict(zip(hdrs, cells))
                        rows.append({
                            "SOURCE":"GeM","DISTRICT":dist,"TALUK":"",
                            "SECTOR":_sector(raw.get("Category","")),
                            "COMPANY_NAME":raw.get("Business Name", raw.get("Seller Name","")),
                            "CIN_OR_UDYAM_NO":raw.get("GSTIN", raw.get("CIN","")),
                            "INCORPORATION_DATE":raw.get("Registration Date",""),
                            "AUTHORIZED_CAPITAL":0.0,
                            "DIRECTOR_NAMES":raw.get("Owner",""),
                            "EMAIL":raw.get("Email",""),"PHONE":raw.get("Contact",""),
                            "ADDRESS":raw.get("Address",""),
                            "HAS_GST":"true" if raw.get("GSTIN") else "false",
                            "GEM_REGISTERED":True,"BANK_PRODUCT":"","SCORE":0,
                        })
                if rows: break

        if rows:
            all_rows.extend(rows); ok(f"{len(rows)} sellers — {dist}")
        else:
            err(f"No GeM data for {dist}")
        time.sleep(API_SLEEP)

    if not all_rows:
        warn("No GeM records."); return pd.DataFrame(columns=MASTER_COLUMNS)
    df = pd.DataFrame(all_rows).drop_duplicates(subset=["COMPANY_NAME","DISTRICT"], keep="first")
    df.to_csv(GEM_CSV, index=False, encoding="utf-8-sig")
    ok(f"Saved {len(df)} GeM sellers → {GEM_CSV.name}")
    return df

# ════════════════════════════════════════════════════════════════════
#   TASK 4 — SCORE & BUILD MASTER LEADS
# ════════════════════════════════════════════════════════════════════

def _score_row(row):
    s = 0
    if _cap(row.get("AUTHORIZED_CAPITAL",0)) > 1_000_000:
        s += SCORING["authorized_capital_above_10L"]
    d = _date(row.get("INCORPORATION_DATE",""))
    if d and d >= datetime(2024,1,1):
        s += SCORING["incorporated_after_jan_2024"]
    if str(row.get("HAS_GST","")).strip().lower() in ("true","yes","1","y"):
        s += SCORING["has_gst"]
    sector = str(row.get("SECTOR","")).lower()
    if "manufactur" in sector:        s += SCORING["sector_manufacturing"]
    elif sector in ("services","technology","it"): s += SCORING["sector_services"]
    gem = row.get("GEM_REGISTERED", False)
    if gem is True or str(gem).lower() in ("true","yes","1"):
        s += SCORING["gem_registered"]
    if (str(row.get("EMAIL","")).strip() not in ("","nan","None") or
        str(row.get("PHONE","")).strip() not in ("","nan","None")):
        s += SCORING["has_contact_info"]
    return round(min(s / SCORE_RAW_MAX * 100, 100))

def _product_row(row):
    s = str(row.get("SECTOR","")).title()
    for k,v in BANK_PRODUCTS.items():
        if k.lower() in s.lower(): return v
    return BANK_PRODUCTS["Other"]

def _xlsx(df):
    df.to_excel(MASTER_XLSX, index=False, engine="openpyxl")
    wb = openpyxl.load_workbook(MASTER_XLSX)
    ws = wb.active;  ws.title = "Master Leads"
    hf = PatternFill("solid", fgColor="003366")
    for cell in ws[1]:
        cell.fill = hf
        cell.font = Font(color="FFFFFF", bold=True, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, col in enumerate(df.columns, 1):
        mlen = max(len(str(col)), df[col].astype(str).str.len().max() if len(df)>0 else 0)
        ws.column_dimensions[get_column_letter(i)].width = min(mlen+4, 45)
    sc = list(df.columns).index("SCORE") + 1
    sl = get_column_letter(sc)
    thin = Side(style="thin", color="D0D0D0")
    bdr  = Border(left=thin, right=thin, top=thin, bottom=thin)
    for ri in range(2, ws.max_row+1):
        cell = ws[f"{sl}{ri}"]
        try: v = int(cell.value or 0)
        except: v = 0
        if v >= 75:   cell.fill = PatternFill("solid",fgColor="00B050"); cell.font = Font(bold=True,color="FFFFFF")
        elif v >= 50: cell.fill = PatternFill("solid",fgColor="FFC000")
        else:         cell.fill = PatternFill("solid",fgColor="FF4444"); cell.font = Font(color="FFFFFF")
        for c in ws[ri]:
            c.border = bdr
            if c.column != sc: c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    wb.save(MASTER_XLSX)

def score_and_merge(df_mca, df_mfg, df_svc, df_gem):
    sec("TASK 4 — Scoring & Building Master Leads Database")
    frames = []
    for label, df in [("MCA",df_mca),("MFG",df_mfg),("SVC",df_svc),("GeM",df_gem)]:
        if df is not None and not df.empty:
            frames.append(df); ok(f"{label}: {len(df)} records")
        else:
            warn(f"{label}: 0 records")

    if not frames:
        err("No data from any source — nothing to score."); return pd.DataFrame(columns=MASTER_COLUMNS)

    master = pd.concat(frames, ignore_index=True)
    for col in MASTER_COLUMNS:
        if col not in master.columns: master[col] = ""

    master = master[master["COMPANY_NAME"].astype(str).str.strip() != ""]
    master = master.drop_duplicates(subset=["CIN_OR_UDYAM_NO","DISTRICT"], keep="first")

    info(f"Scoring {len(master)} leads ...")
    master["SCORE"]        = master.apply(_score_row, axis=1)
    master["BANK_PRODUCT"] = master.apply(_product_row, axis=1)
    master = master.sort_values("SCORE", ascending=False).reset_index(drop=True)
    extra  = [c for c in master.columns if c not in MASTER_COLUMNS]
    master = master[MASTER_COLUMNS + extra]

    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    ok(f"CSV  saved → {MASTER_CSV}")
    _xlsx(master)
    ok(f"XLSX saved → {MASTER_XLSX}")

    hi = (master["SCORE"]>=75).sum()
    md = ((master["SCORE"]>=50)&(master["SCORE"]<75)).sum()
    lo = (master["SCORE"]<50).sum()
    bar = "─"*58
    print(f"\n{B}  LEAD SUMMARY{RS}")
    print(f"  {bar}")
    print(f"  Total leads   : {B}{len(master)}{RS}")
    print(f"  {G}High  (≥75){RS}  : {hi}")
    print(f"  {Y}Medium (50-74){RS}: {md}")
    print(f"  {R}Low   (<50){RS}  : {lo}")
    print(f"  {bar}")
    print(f"  By district:")
    for d in DISTRICTS:
        print(f"    {d:<22} {(master['DISTRICT']==d).sum()}")
    print(f"  {bar}")
    print(f"  {B}TOP 5 LEADS:{RS}")
    for i, (_, row) in enumerate(master.head(5).iterrows(), 1):
        cl = G if row["SCORE"]>=75 else Y
        print(f"  {i}. {cl}{row['SCORE']:>3}/100{RS}  {row['COMPANY_NAME'][:38]:<38}  {row['DISTRICT']:<16}  {row['SECTOR']}")
    print(f"  {bar}\n")
    return master

# ════════════════════════════════════════════════════════════════════
#   TASK 5 — PUSH TO GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════

def push_to_sheets(df):
    sec("TASK 5 — Push to Google Sheets")
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        err("gspread not installed."); return 0

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        creds  = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=scopes)
        client = gspread.authorize(creds)
        ok(f"Authenticated as  {creds.service_account_email}")
    except Exception as e:
        err(f"Auth failed: {e}"); return 0

    try:
        sh = client.open(GOOGLE_SHEET_NAME)
        ok(f'Opened sheet: "{GOOGLE_SHEET_NAME}"')
    except gspread.SpreadsheetNotFound:
        info("Sheet not found — creating ...")
        sh = client.create(GOOGLE_SHEET_NAME)
        sh.share("", perm_type="anyone", role="reader")
        ok(f"Created: {sh.url}")

    try:    ws = sh.worksheet("Leads")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Leads", rows=10000, cols=30)

    # Row 1 = timestamp, Row 2 = headers
    ws.update([[datetime.now().strftime("Last sync: %d-%b-%Y %I:%M %p")]], "A1")
    headers = list(df.columns)
    if ws.row_values(2) != headers:
        ws.update("A2", [headers])

    # Skip already-pushed CINs
    try:
        eh = ws.row_values(2)
        ci = (eh.index("CIN_OR_UDYAM_NO")+1) if "CIN_OR_UDYAM_NO" in eh else 6
        known = set(v.strip() for v in ws.col_values(ci)[2:] if v.strip())
    except Exception:
        known = set()

    info(f"Sheet already has {len(known)} known IDs")
    new_df = df[~df["CIN_OR_UDYAM_NO"].astype(str).str.strip().isin(known)]
    if new_df.empty:
        ok("No new rows — sheet is up to date."); return 0

    rows = new_df.fillna("").astype(str).values.tolist()
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    ok(f"{len(rows)} new rows pushed!")
    print(f"\n  {B}{C}Sheet URL:{RS} {sh.url}\n")
    return len(rows)

# ════════════════════════════════════════════════════════════════════
#   TASK 6 — EMAIL ALERT
# ════════════════════════════════════════════════════════════════════

def send_email_alert(summary):
    if not all([ALERT_EMAIL_SENDER, ALERT_EMAIL_PASSWORD, ALERT_EMAIL_RECIPIENT]):
        warn("Email alert skipped — fill ALERT_EMAIL_SENDER/PASSWORD/RECIPIENT at top of this file")
        return
    top5 = "\n".join(
        f"  {i+1}. {r.get('COMPANY_NAME','')[:42]} | {r.get('DISTRICT','')} | {r.get('SCORE',0)}/100"
        for i,r in enumerate(summary.get("top5",[]))
    ) or "  (no data)"
    body = (
        f"IOB Nagapattinam RO — Daily Lead Sync  |  "
        f"{datetime.now().strftime('%d-%b-%Y %I:%M %p')}\n"
        f"{'─'*62}\n"
        f"New MCA Companies   : {summary['mca']}\n"
        f"New Udyam MSMEs     : {summary['msme']}\n"
        f"New GeM Sellers     : {summary['gem']}\n"
        f"Total Master Leads  : {summary['total']}\n\n"
        f"TOP 5 LEADS:\n{top5}\n\n"
        f"Google Sheet: Nagapattinam RO - Live Leads\n"
        f"{'─'*62}\n"
        f"Automated message — IOB Lead Generation System"
    )
    msg = MIMEMultipart()
    msg["From"]    = ALERT_EMAIL_SENDER
    msg["To"]      = ALERT_EMAIL_RECIPIENT
    msg["Subject"] = (f"IOB Leads: {summary['mca']} MCA + {summary['msme']} MSME "
                      f"+ {summary['gem']} GeM [{datetime.now().strftime('%d-%b-%Y')}]")
    msg.attach(MIMEText(body,"plain"))
    if MASTER_CSV.exists():
        with open(MASTER_CSV,"rb") as f:
            part = MIMEBase("application","octet-stream"); part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f'attachment; filename="master_leads_{datetime.now():%Y%m%d}.csv"')
        msg.attach(part)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo(); s.starttls()
            s.login(ALERT_EMAIL_SENDER, ALERT_EMAIL_PASSWORD)
            s.sendmail(ALERT_EMAIL_SENDER, ALERT_EMAIL_RECIPIENT, msg.as_string())
        ok(f"Email sent → {ALERT_EMAIL_RECIPIENT}")
    except Exception as e:
        err(f"Email failed: {e}")

# ════════════════════════════════════════════════════════════════════
#   MAIN PIPELINE
# ════════════════════════════════════════════════════════════════════

def run():
    print(f"\n{B}{C}"
          "╔══════════════════════════════════════════════════════════════╗\n"
          "║   Indian Overseas Bank — Nagapattinam Regional Office        ║\n"
          "║          Automated Lead Generation Pipeline                  ║\n"
          "║   Districts: Nagapattinam | Thiruvarur | Mayiladuthurai       ║\n"
          f"╚══════════════════════════════════════════════════════════════╝{RS}\n")

    log.info("Pipeline started — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    t0 = time.time()

    try:
        df_mca          = fetch_mca()
        df_mfg, df_svc  = fetch_udyam()
        df_gem          = fetch_gem()
        master          = score_and_merge(df_mca, df_mfg, df_svc, df_gem)
        sheets_new      = push_to_sheets(master)
    except Exception as e:
        err(f"Pipeline crashed: {e}")
        traceback.print_exc()
        try: input("\nPress Enter to exit ...")
        except: pass
        return

    elapsed = round(time.time()-t0, 1)

    sec("TASK 6 — Email Alert")
    summary = {
        "mca":   len(df_mca),
        "msme":  len(df_mfg) + len(df_svc),
        "gem":   len(df_gem),
        "total": len(master),
        "top5":  master.head(5).to_dict("records") if not master.empty else [],
    }
    send_email_alert(summary)

    log.info("Done in %ss — MCA:%d MSME:%d GeM:%d Total:%d Sheets+:%d",
             elapsed, summary["mca"], summary["msme"],
             summary["gem"], summary["total"], sheets_new)

    bar = "═"*62
    print(f"\n{B}{G}{bar}\n  PIPELINE COMPLETE  ·  {elapsed}s\n{bar}{RS}")
    print(f"  CSV  : {MASTER_CSV}")
    print(f"  XLSX : {MASTER_XLSX}")
    print(f"  Log  : {LOG_FILE}")
    print(f"{B}{G}{bar}{RS}\n")
    try: input("Press Enter to exit ...")
    except: pass

# ════════════════════════════════════════════════════════════════════
#   OPTIONAL 6 AM DAILY SCHEDULER
# ════════════════════════════════════════════════════════════════════

def start_scheduler():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        _pip("apscheduler")
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

    sched = BlockingScheduler(timezone="Asia/Kolkata")
    sched.add_job(run, CronTrigger(hour=SCHEDULE_HOUR, minute=0, timezone="Asia/Kolkata"),
                  id="iob_leads", misfire_grace_time=3600, coalesce=True)
    print(f"\n{B}Scheduler running — pipeline fires daily at {SCHEDULE_HOUR:02d}:00 AM IST")
    print("Keep this window open. Press Ctrl+C to stop.\n")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown(); print("Scheduler stopped.")

# ════════════════════════════════════════════════════════════════════
#   ENTRY POINT
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="IOB Nagapattinam Lead Pipeline")
    p.add_argument("--schedule", action="store_true",
                   help="Start 6 AM daily auto-scheduler")
    args = p.parse_args()
    start_scheduler() if args.schedule else run()
