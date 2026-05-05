"""
Task 5 — Google Sheets Integration
Pushes master_leads.csv to "Nagapattinam RO - Live Leads" Google Sheet.
Uses a service account for authentication (no OAuth browser popup needed).

How to set up:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "Google Sheets API" and "Google Drive API"
  3. IAM & Admin → Service Accounts → Create service account
  4. Generate JSON key → download → save as credentials/service_account.json
  5. Open your Google Sheet → Share with the service account email (Editor)
  6. Set GOOGLE_SERVICE_ACCOUNT_JSON path in .env
"""

import os
import logging
from datetime import datetime

import pandas as pd

import config

logger = logging.getLogger(__name__)


# ── Auth & client setup ───────────────────────────────────────────────────────

def _get_gspread_client():
    """Return an authenticated gspread client using the service account JSON."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("gspread / google-auth not installed. Run: pip install gspread google-auth")
        return None

    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON",
                        config.GOOGLE_SERVICE_ACCOUNT_JSON
                        if hasattr(config, "GOOGLE_SERVICE_ACCOUNT_JSON")
                        else "credentials/service_account.json")

    if not os.path.exists(sa_json):
        logger.error(
            "Service account JSON not found at: %s\n"
            "  • Go to https://console.cloud.google.com/\n"
            "  • Create service account → download JSON key\n"
            "  • Save at: %s\n"
            "  • Share the Google Sheet with the service account email",
            sa_json, sa_json,
        )
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(sa_json, scopes=scopes)
    client = gspread.authorize(creds)
    return client


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open_or_create_sheet(client, sheet_name: str):
    """Open an existing sheet, or create a new one and set up the header."""
    import gspread
    try:
        sh = client.open(sheet_name)
        print(f"  Opened existing sheet: '{sheet_name}'")
        return sh
    except gspread.SpreadsheetNotFound:
        print(f"  Sheet '{sheet_name}' not found — creating …")
        sh = client.create(sheet_name)
        sh.share(None, perm_type="anyone", role="reader")   # optional public read
        print(f"  Created: {sh.url}")
        return sh


def _get_or_create_worksheet(sh, tab_name: str = "Leads"):
    """Get the first worksheet, or create a named one."""
    try:
        return sh.worksheet(tab_name)
    except Exception:
        return sh.add_worksheet(title=tab_name, rows=10000, cols=30)


def _existing_ids(ws) -> set:
    """Return the set of CIN/Udyam numbers already in the sheet (column C)."""
    try:
        all_values = ws.col_values(
            _header_col_index(ws, "CIN_OR_UDYAM_NO")
        )
        return set(v.strip() for v in all_values[1:] if v.strip())
    except Exception:
        return set()


def _header_col_index(ws, col_name: str) -> int:
    """Return 1-based column index for a given header name (default 3)."""
    try:
        headers = ws.row_values(2)   # row 1 = timestamp, row 2 = column headers
        return headers.index(col_name) + 1
    except (ValueError, Exception):
        return 3   # fallback: column C


# ── Main push function ────────────────────────────────────────────────────────

def push_to_sheets(df: pd.DataFrame = None) -> int:
    """
    Push master leads to Google Sheets.
    - Row 1 : timestamp of last sync
    - Row 2 : column headers
    - Row 3+ : data rows (new rows appended, duplicates skipped by CIN/Udyam)
    Returns the number of new rows appended.
    """
    # Load from file if no DataFrame passed
    if df is None or df.empty:
        if os.path.exists(config.MASTER_LEADS_CSV_OUT):
            df = pd.read_csv(config.MASTER_LEADS_CSV_OUT)
            print(f"  Loaded {len(df)} rows from {config.MASTER_LEADS_CSV_OUT}")
        else:
            logger.error("master_leads.csv not found. Run score_leads.py first.")
            return 0

    client = _get_gspread_client()
    if client is None:
        return 0

    sheet_name = os.getenv("GOOGLE_SHEET_NAME",
                            getattr(config, "GOOGLE_SHEET_NAME",
                                    "Nagapattinam RO - Live Leads"))

    print(f"\n[Sheets] Connecting to: '{sheet_name}' …")
    sh = _open_or_create_sheet(client, sheet_name)
    ws = _get_or_create_worksheet(sh, "Leads")

    # Write / refresh timestamp in A1
    now_str = datetime.now().strftime("Last sync: %d-%b-%Y %I:%M %p")
    ws.update("A1", [[now_str]])

    # Write column headers in row 2 (if sheet is new or headers missing)
    existing_headers = ws.row_values(2)
    headers = list(df.columns)
    if existing_headers != headers:
        print("  Writing column headers in row 2 …")
        ws.update("A2", [headers])

    # Fetch existing CIN/Udyam IDs to avoid duplicates
    known_ids = _existing_ids(ws)
    print(f"  Sheet already has {len(known_ids)} known CIN/Udyam IDs")

    # Filter to only new rows
    if "CIN_OR_UDYAM_NO" in df.columns:
        new_rows_df = df[
            ~df["CIN_OR_UDYAM_NO"].astype(str).str.strip().isin(known_ids)
        ]
    else:
        new_rows_df = df

    if new_rows_df.empty:
        print("  No new leads to push (all already present in sheet).")
        return 0

    # Convert to list of lists (gspread requirement)
    new_rows_df = new_rows_df.fillna("").astype(str)
    rows_to_append = new_rows_df.values.tolist()

    print(f"  Appending {len(rows_to_append)} new rows …")
    ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")

    print(f"  ✓ {len(rows_to_append)} rows pushed to '{sheet_name}'")
    print(f"  Sheet URL: {sh.url}")
    return len(rows_to_append)


# ── CLI runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    n = push_to_sheets()
    print(f"\nDone. {n} new rows pushed to Google Sheets.")
