"""
Zerodha KiteConnect Session Manager.

Handles the full daily authentication flow:
  1. Generate Kite login URL
  2. Auto-submit credentials + TOTP via requests (no browser needed)
  3. Exchange the request_token for an access_token
  4. Persist the access_token for the trading day
  5. Provide a ready-to-use KiteConnect instance to all bots

Zerodha login endpoint uses a standard form + TOTP – this module
replicates that flow programmatically using `requests`.
"""
import os
import json
import time
import pyotp
import requests
from datetime import date
from kiteconnect import KiteConnect

from config.settings import (
    ZERODHA_API_KEY, ZERODHA_API_SECRET,
    ZERODHA_USER_ID, ZERODHA_PASSWORD, ZERODHA_TOTP_SECRET,
    LOG_DIR,
)
from utils.logger import setup_logger

log = setup_logger("session_manager")

TOKEN_FILE = os.path.join(LOG_DIR, "session_token.json")


class SessionManager:
    """Manages a single KiteConnect session for the trading day."""

    def __init__(self):
        self.kite: KiteConnect = KiteConnect(api_key=ZERODHA_API_KEY)
        self._access_token: str | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_kite(self) -> KiteConnect:
        """Return an authenticated KiteConnect instance, refreshing if needed."""
        if not self._is_token_valid():
            self._authenticate()
        return self.kite

    # ── Authentication flow ───────────────────────────────────────────────────

    def _authenticate(self) -> None:
        """Run the full Zerodha login flow and store the access token."""
        log.info("Starting Zerodha authentication…")

        # Step 1 – POST credentials to Kite login API
        session = requests.Session()
        login_url = "https://kite.zerodha.com/api/login"
        resp = session.post(login_url, data={
            "user_id": ZERODHA_USER_ID,
            "password": ZERODHA_PASSWORD,
        }, timeout=15)
        resp.raise_for_status()
        login_data = resp.json()

        if login_data.get("status") != "success":
            raise RuntimeError(f"Login failed: {login_data}")

        request_id = login_data["data"]["request_id"]
        log.info("Password accepted, submitting TOTP…")

        # Step 2 – POST TOTP  (do NOT follow redirects – the redirect goes to
        # the app's redirect URL, e.g. https://127.0.0.1, which is unreachable.
        # The request_token is embedded in that redirect URL, which Zerodha
        # returns inside the JSON body under data.redirect_url.)
        totp_code = pyotp.TOTP(ZERODHA_TOTP_SECRET).now()
        twofa_url = "https://kite.zerodha.com/api/twofa"
        resp2 = session.post(twofa_url, data={
            "user_id":     ZERODHA_USER_ID,
            "request_id":  request_id,
            "twofa_value": totp_code,
            "twofa_type":  "totp",
        }, timeout=15, allow_redirects=False)

        # Zerodha may respond with 200 (JSON body) or 302 (Location header)
        twofa_data = {}
        if resp2.status_code in (200, 302):
            try:
                twofa_data = resp2.json()
            except Exception:
                pass
        else:
            resp2.raise_for_status()

        if twofa_data.get("status") not in ("success", None):
            # status key missing on 302 responses – that is still a success
            if twofa_data.get("status") == "error":
                raise RuntimeError(f"TOTP failed: {twofa_data}")

        # Step 3 – Extract request_token
        # Priority 1: JSON body → data.redirect_url
        # Priority 2: HTTP Location header (302 response)
        from urllib.parse import urlparse, parse_qs

        redirect_url = (
            twofa_data.get("data", {}).get("redirect_url", "")
            or resp2.headers.get("Location", "")
        )

        if not redirect_url:
            raise RuntimeError(
                "Zerodha did not return a redirect URL after TOTP. "
                "Verify your TOTP secret and that TOTP is enabled on your account."
            )

        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)

        if "request_token" not in params:
            raise RuntimeError(
                f"request_token not found in redirect URL: {redirect_url}\n"
                "Check API redirect URL is set to https://127.0.0.1 in kite.trade → My Apps."
            )

        request_token = params["request_token"][0]
        log.info("Obtained request_token, generating session…")

        # Step 4 – Generate session (access_token)
        kite_session = self.kite.generate_session(
            request_token, api_secret=ZERODHA_API_SECRET
        )
        access_token = kite_session["access_token"]
        self.kite.set_access_token(access_token)
        self._access_token = access_token

        # Step 5 – Persist token for today
        self._save_token(access_token)
        log.info("Authentication successful. Access token saved.")

    # ── Token persistence ─────────────────────────────────────────────────────

    def _save_token(self, token: str) -> None:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            json.dump({"date": str(date.today()), "token": token}, f)

    def _load_token(self) -> str | None:
        if not os.path.exists(TOKEN_FILE):
            return None
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        if data.get("date") == str(date.today()):
            return data.get("token")
        return None  # Token is from a previous day

    def _is_token_valid(self) -> bool:
        if self._access_token:
            return True
        saved = self._load_token()
        if saved:
            self.kite.set_access_token(saved)
            self._access_token = saved
            log.info("Loaded today's access token from cache.")
            # Quick validation ping
            try:
                self.kite.profile()
                return True
            except Exception:
                log.warning("Cached token invalid, re-authenticating…")
                self._access_token = None
        return False


# Module-level singleton
_session: SessionManager | None = None


def get_session() -> SessionManager:
    global _session
    if _session is None:
        _session = SessionManager()
    return _session


def get_kite() -> KiteConnect:
    """Convenience function – returns a ready KiteConnect instance."""
    return get_session().get_kite()
