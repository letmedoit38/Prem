"""
Zerodha KiteConnect Session Manager.

Handles the full daily authentication flow:
  1. Hit Connect OAuth URL to establish API key context in the session
  2. POST credentials (user_id + password)
  3. POST TOTP code
  4. Capture request_token from the 302 redirect Location header
  5. Exchange request_token + api_secret for access_token
  6. Persist access_token for the trading day
"""
import os
import json
import pyotp
import requests
from datetime import date
from urllib.parse import urlparse, parse_qs
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

    def get_kite(self) -> KiteConnect:
        """Return an authenticated KiteConnect instance, refreshing if needed."""
        if not self._is_token_valid():
            self._authenticate()
        return self.kite

    def _authenticate(self) -> None:
        """
        Full Zerodha OAuth login flow.

        Root cause of previous failures:
          Zerodha only includes request_token in the post-TOTP redirect when
          the session was started through the Connect OAuth URL with the API key.
          Hitting /api/login directly (without step 1) returns a plain web
          session with no request_token -- hence the empty {"data":{"profile":{}}}
          response seen in debug output.
        """
        log.info("Starting Zerodha authentication…")
        session = requests.Session()

        # ── Step 1: Establish OAuth context ──────────────────────────────────
        # This GET call sets session cookies that bind the login to the API key
        # and redirect URL registered in kite.trade → My Apps.
        # Without this, Zerodha has no API context and never issues a request_token.
        connect_url = (
            f"https://kite.zerodha.com/connect/login?api_key={ZERODHA_API_KEY}&v=3"
        )
        session.get(connect_url, timeout=15)
        log.info("OAuth context established.")

        # ── Step 2: Submit credentials ────────────────────────────────────────
        r1 = session.post("https://kite.zerodha.com/api/login", data={
            "user_id":  ZERODHA_USER_ID,
            "password": ZERODHA_PASSWORD,
        }, timeout=15)
        r1.raise_for_status()
        login_data = r1.json()

        if login_data.get("status") != "success":
            raise RuntimeError(f"Login failed: {login_data}")

        request_id = login_data["data"]["request_id"]
        log.info("Password accepted, submitting TOTP…")

        # ── Step 3: Submit TOTP (no redirect follow) ──────────────────────────
        # With the OAuth context active, Zerodha responds with HTTP 302 and sets
        # the Location header to:
        #   https://127.0.0.1?request_token=XXX&action=login&type=login
        # We must NOT follow this redirect (it goes to localhost which is unreachable).
        totp_code = pyotp.TOTP(ZERODHA_TOTP_SECRET).now()
        r2 = session.post("https://kite.zerodha.com/api/twofa", data={
            "user_id":     ZERODHA_USER_ID,
            "request_id":  request_id,
            "twofa_value": totp_code,
            "twofa_type":  "totp",
        }, timeout=15, allow_redirects=False)

        # If TOTP was wrong Zerodha returns 200 with status=error
        if r2.status_code == 200:
            try:
                body = r2.json()
                if body.get("status") == "error":
                    raise RuntimeError(f"TOTP rejected by Zerodha: {body}")
            except ValueError:
                pass

        # ── Step 4: Extract request_token from Location header ────────────────
        location = r2.headers.get("Location", "")
        if not location:
            raise RuntimeError(
                f"No Location header in TOTP response (status={r2.status_code}).\n"
                f"Response body: {r2.text[:300]}\n"
                "Make sure the redirect URL in kite.trade → My Apps is exactly: "
                "https://127.0.0.1"
            )

        params = parse_qs(urlparse(location).query)
        if "request_token" not in params:
            raise RuntimeError(
                f"request_token not found in redirect: {location}\n"
                "Check kite.trade → My Apps redirect URL = https://127.0.0.1"
            )

        request_token = params["request_token"][0]
        log.info("request_token obtained, generating access token…")

        # ── Step 5: Exchange request_token for access_token ───────────────────
        kite_session = self.kite.generate_session(
            request_token, api_secret=ZERODHA_API_SECRET
        )
        access_token = kite_session["access_token"]
        self.kite.set_access_token(access_token)
        self._access_token = access_token
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
        return None

    def _is_token_valid(self) -> bool:
        if self._access_token:
            return True
        saved = self._load_token()
        if saved:
            self.kite.set_access_token(saved)
            self._access_token = saved
            log.info("Loaded today's access token from cache.")
            try:
                self.kite.profile()
                return True
            except Exception:
                log.warning("Cached token invalid, re-authenticating…")
                self._access_token = None
        return False


_session: SessionManager | None = None


def get_session() -> SessionManager:
    global _session
    if _session is None:
        _session = SessionManager()
    return _session


def get_kite() -> KiteConnect:
    """Convenience function – returns a ready KiteConnect instance."""
    return get_session().get_kite()
