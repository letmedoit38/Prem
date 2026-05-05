"""
Central configuration: districts, API endpoints, scoring weights,
product mapping, and column schemas.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Target geography ──────────────────────────────────────────────────────────

STATE = "Tamil Nadu"
STATE_CODE = "33"          # MCA state code for Tamil Nadu

DISTRICTS = ["Nagapattinam", "Thiruvarur", "Mayiladuthurai"]

# MCA district codes (used in API filter)
MCA_DISTRICT_CODES = {
    "Nagapattinam": "Nagapattinam",
    "Thiruvarur": "Thiruvarur",
    "Mayiladuthurai": "Mayiladuthurai",
}

# ── API endpoints ─────────────────────────────────────────────────────────────

MCA_API_BASE = "https://api.mca.gov.in/MCA21_SFTP/V2/MasterData/CompanyMasterData"
MCA_PUBLIC_SEARCH = "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do"

DATA_GOV_API_BASE = "https://api.data.gov.in/resource/"
UDYAM_MANUFACTURING_RESOURCE = "091a8776-fa68-4f36-9b8c-8c3b3e4d8b2a"
UDYAM_SERVICES_RESOURCE      = "district-wise-services-msme"

GEM_API_BASE    = "https://mkp.gem.gov.in/api/v2/sellers"
GEM_PUBLIC_PAGE = "https://gem.gov.in/sellerRegistration"

DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY", "")

# ── Output paths ──────────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

MCA_JSON_OUT          = os.path.join(DATA_DIR, "companies.json")
MCA_CSV_OUT           = os.path.join(DATA_DIR, "companies.csv")
UDYAM_MFG_CSV_OUT     = os.path.join(DATA_DIR, "msme_manufacturing.csv")
UDYAM_SVC_CSV_OUT     = os.path.join(DATA_DIR, "msme_services.csv")
GEM_CSV_OUT           = os.path.join(DATA_DIR, "gem_sellers.csv")
MASTER_LEADS_CSV_OUT  = os.path.join(DATA_DIR, "master_leads.csv")
MASTER_LEADS_XLSX_OUT = os.path.join(DATA_DIR, "master_leads.xlsx")
PIPELINE_LOG          = os.path.join(LOGS_DIR, "pipeline.log")

# ── Scoring rules ─────────────────────────────────────────────────────────────

SCORING_RULES = {
    "authorized_capital_above_10L":  20,   # Auth capital > ₹10 Lakh
    "incorporated_after_jan_2024":   25,   # New company, high priority
    "has_gst":                       15,
    "sector_manufacturing":          20,
    "sector_services":               10,
    "gem_registered":                20,   # Govt contract potential
    "has_contact_info":              10,   # Email or phone present
}

SCORE_MAX = sum(SCORING_RULES.values())    # 120 raw; will normalise to 100

# ── Bank product mapping ──────────────────────────────────────────────────────

BANK_PRODUCTS = {
    "Manufacturing": "MSME-TL; CC; Machinery Loan",
    "Services":      "MSME-CC; OD; GeM Finance",
    "Technology":    "MSME-CC; OD; GeM Finance",
    "Trading":       "CC; GeM Order Finance; Current Account",
    "Construction":  "Project Finance; CC; BG",
    "Other":         "MSME-CC; Current Account",
}

# ── Master leads schema ───────────────────────────────────────────────────────

MASTER_COLUMNS = [
    "SOURCE",
    "DISTRICT",
    "TALUK",
    "SECTOR",
    "COMPANY_NAME",
    "CIN_OR_UDYAM_NO",
    "INCORPORATION_DATE",
    "AUTHORIZED_CAPITAL",
    "DIRECTOR_NAMES",
    "EMAIL",
    "PHONE",
    "ADDRESS",
    "HAS_GST",
    "GEM_REGISTERED",
    "BANK_PRODUCT",
    "SCORE",
]

# ── Scheduler ─────────────────────────────────────────────────────────────────

SCHEDULE_HOUR   = 6
SCHEDULE_MINUTE = 0

# ── Misc ──────────────────────────────────────────────────────────────────────

API_RATE_LIMIT  = int(os.getenv("API_RATE_LIMIT_SECONDS", "2"))
MAX_RETRIES     = int(os.getenv("MAX_RETRIES", "3"))

REQUEST_HEADERS = {
    "User-Agent": (
        "IOB-LeadGen-Pipeline/1.0 "
        "(Indian Overseas Bank; Nagapattinam RO; official use)"
    ),
    "Accept": "application/json",
}
