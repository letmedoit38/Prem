import os, json, re, pyotp, requests
from datetime import date, datetime
from urllib.parse import urlparse, parse_qs
from kiteconnect import KiteConnect
from config.settings import (
    ZERODHA_API_KEY, ZERODHA_API_SECRET,
    ZERODHA_USER_ID, ZERODHA_PASSWORD, ZERODHA_TOTP_SECRET, LOG_DIR,
)
from utils.logger import setup_logger

log = setup_logger("session_manager")
TOKEN_FILE = os.path.join(LOG_DIR, "session_token.json")

_COOKIE_NAMES = ["user_id", "public_token", "enctoken"]


def _extract_cookies(response) -> dict:
    """
    Extract user_id, public_token, enctoken from a requests.Response.
    kite.zerodha.com requires all 3 cookies for authenticated requests.
    Tries urllib3 getlist(), combined header string, then cookie jar.
    """
    found = {}
    patterns = {n: re.compile(rf"{n}=([^;,\s]+)") for n in _COOKIE_NAMES}

    # Method 1 — per-cookie via urllib3 raw header list
    try:
        for cookie_str in response.raw.headers.getlist("Set-Cookie"):
            for name, pat in patterns.items():
                if name not in found:
                    m = pat.search(cookie_str)
                    if m:
                        found[name] = m.group(1).strip()
    except Exception:
        pass

    # Method 2 — combined Set-Cookie string
    if len(found) < len(_COOKIE_NAMES):
        combined = response.headers.get("Set-Cookie", "")
        for name, pat in patterns.items():
            if name not in found:
                m = pat.search(combined)
                if m:
                    found[name] = m.group(1).strip()

    # Method 3 — requests cookie jar
    for name in _COOKIE_NAMES:
        if name not in found:
            val = response.cookies.get(name, "")
            if val:
                found[name] = val

    return found


class KiteEncTokenWrapper:
    """
    Drop-in replacement for KiteConnect that uses Zerodha web enctoken.

    Targets kite.zerodha.com (the web API) since the enctoken is issued
    by the web login flow, NOT the paid KiteConnect API (api.kite.trade).
    """
    BASE = "https://kite.zerodha.com"

    TRANSACTION_TYPE_BUY  = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"
    PRODUCT_MIS           = "MIS"
    PRODUCT_CNC           = "CNC"
    PRODUCT_NRML          = "NRML"
    ORDER_TYPE_MARKET     = "MARKET"
    ORDER_TYPE_LIMIT      = "LIMIT"
    VARIETY_REGULAR       = "regular"
    EXCHANGE_NSE          = "NSE"
    EXCHANGE_BSE          = "BSE"

    def __init__(self, api_key, enctoken, user_id="", public_token=""):
        self.api_key    = api_key
        self._enctoken  = enctoken
        self._sess      = requests.Session()
        # kite.zerodha.com requires all 3 cookies + Authorization header
        self._sess.headers.update({
            "X-Kite-Version": "3",
            "Authorization":  f"enctoken {enctoken}",
        })
        if user_id:
            self._sess.cookies.set("user_id",      user_id,      domain="kite.zerodha.com")
        if public_token:
            self._sess.cookies.set("public_token", public_token, domain=".zerodha.com")
        self._sess.cookies.set("enctoken",         enctoken,     domain="kite.zerodha.com")

    # ── API methods ─────────────────────────────────────────────────────

    def profile(self):
        return self._get("/api/user/profile")["data"]

    def margins(self, segment=None):
        path = f"/api/user/margins/{segment}" if segment else "/api/user/margins"
        return self._get(path)["data"]

    def ltp(self, instruments):
        return self._get("/api/quote/ltp", params={"i": instruments})["data"]

    def quote(self, instruments):
        return self._get("/api/quote", params={"i": instruments})["data"]

    def instruments(self, exchange=None):
        path = f"/api/instruments/{exchange}" if exchange else "/api/instruments"
        r = self._sess.get(f"{self.BASE}{path}", timeout=30)
        r.raise_for_status()
        import csv, io
        result = []
        for row in csv.DictReader(io.StringIO(r.text)):
            try:
                row["instrument_token"] = int(row["instrument_token"])
                row["last_price"] = float(row.get("last_price") or 0)
                row["lot_size"]   = int(row.get("lot_size") or 0)
            except (ValueError, KeyError):
                pass
            result.append(row)
        return result

    def historical_data(self, instrument_token, from_date, to_date, interval,
                        continuous=False, oi=False):
        params = {
            "from": from_date.strftime("%Y-%m-%d %H:%M:%S"),
            "to":   to_date.strftime("%Y-%m-%d %H:%M:%S"),
            "continuous": int(continuous), "oi": int(oi),
        }
        candles = self._get(
            f"/api/instruments/historical/{instrument_token}/{interval}", params=params
        )["data"]["candles"]
        result = []
        for c in candles:
            dt = c[0]
            if isinstance(dt, str):
                dt = datetime.strptime(dt[:19], "%Y-%m-%dT%H:%M:%S")
            result.append({
                "date": dt, "open": float(c[1]), "high": float(c[2]),
                "low": float(c[3]), "close": float(c[4]), "volume": int(c[5]),
                "oi": int(c[6]) if len(c) > 6 else 0,
            })
        return result

    def place_order(self, variety, exchange, tradingsymbol, transaction_type,
                    quantity, product, order_type, price=None,
                    trigger_price=None, tag=None):
        data = {
            "tradingsymbol": tradingsymbol, "exchange": exchange,
            "transaction_type": transaction_type, "order_type": order_type,
            "quantity": quantity, "product": product,
        }
        if price:         data["price"] = price
        if trigger_price: data["trigger_price"] = trigger_price
        if tag:           data["tag"] = tag
        return str(self._post(f"/api/orders/{variety}", data=data)["data"]["order_id"])

    def orders(self):
        return self._get("/api/orders")["data"]

    def positions(self):
        return self._get("/api/portfolio/positions")["data"]

    def set_access_token(self, token):
        pass

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get(self, path, params=None):
        r = self._sess.get(f"{self.BASE}{path}", params=params, timeout=15)
        self._check(r)
        return r.json()

    def _post(self, path, data=None):
        r = self._sess.post(f"{self.BASE}{path}", data=data, timeout=15)
        self._check(r)
        return r.json()

    @staticmethod
    def _check(r):
        if r.status_code not in (200, 201):
            try:
                msg = r.json().get("message", r.text[:300])
            except Exception:
                msg = r.text[:300]
            raise RuntimeError(f"Kite API {r.status_code}: {msg}")


class SessionManager:
    def __init__(self):
        self._kite = None
        self._token = None
        self._token_type = "enctoken"

    def get_kite(self):
        if not self._is_token_valid():
            self._authenticate()
        return self._kite

    def _authenticate(self):
        log.info("Starting Zerodha authentication...")
        session = requests.Session()

        # ── Step 1: Password login ───────────────────────────────────────────
        r1 = session.post("https://kite.zerodha.com/api/login", data={
            "user_id": ZERODHA_USER_ID, "password": ZERODHA_PASSWORD,
        }, timeout=15)
        r1.raise_for_status()
        login_data = r1.json()
        if login_data.get("status") != "success":
            raise RuntimeError(f"Login failed: {login_data}")
        request_id = login_data["data"]["request_id"]
        log.info("Password accepted, submitting TOTP...")

        # ── Step 2: TOTP ─────────────────────────────────────────────────────
        totp_code = pyotp.TOTP(ZERODHA_TOTP_SECRET).now()
        r2 = session.post("https://kite.zerodha.com/api/twofa", data={
            "user_id":     ZERODHA_USER_ID,
            "request_id":  request_id,
            "twofa_value": totp_code,
            "twofa_type":  "totp",
        }, timeout=15, allow_redirects=False)

        # Check if TOTP was rejected
        if r2.status_code == 200:
            try:
                body = r2.json()
                if body.get("status") == "error":
                    raise RuntimeError(f"TOTP rejected: {body.get('message', body)}")
            except ValueError:
                pass

        # ── Extract all 3 session cookies ────────────────────────────────────
        cookies = _extract_cookies(r2)
        for name in _COOKIE_NAMES:
            if name not in cookies and session.cookies.get(name):
                cookies[name] = session.cookies.get(name)

        enctoken     = cookies.get("enctoken", "")
        user_id      = cookies.get("user_id", "")
        public_token = cookies.get("public_token", "")

        log.info(
            f"TOTP status={r2.status_code} | "
            f"enctoken={'YES (' + enctoken[:8] + '...)' if enctoken else 'MISSING'} | "
            f"user_id={'YES' if user_id else 'MISSING'} | "
            f"public_token={'YES' if public_token else 'MISSING'}"
        )

        if enctoken:
            log.info("Building Kite session with all 3 cookies...")
            self._kite = KiteEncTokenWrapper(
                ZERODHA_API_KEY, enctoken, user_id, public_token
            )
            profile = self._kite.profile()
            log.info(f"Logged in as: {profile.get('user_name')} ({profile.get('user_id')})")
            self._token      = enctoken
            self._token_type = "enctoken"
            self._save_token({"enctoken": enctoken, "user_id": user_id,
                              "public_token": public_token}, "enctoken")
            return

        # ── Fallback: OAuth redirect (KiteConnect paid API) ───────────────────────
        location = r2.headers.get("Location", "")
        if location and "request_token" in location:
            request_token = parse_qs(urlparse(location).query)["request_token"][0]
            kite = KiteConnect(api_key=ZERODHA_API_KEY)
            sess_data = kite.generate_session(request_token, api_secret=ZERODHA_API_SECRET)
            access_token = sess_data["access_token"]
            kite.set_access_token(access_token)
            self._kite = kite
            self._token = access_token
            self._token_type = "access_token"
            self._save_token(access_token, "access_token")
            log.info("Authenticated via OAuth access_token.")
            return

        # ── All methods failed ───────────────────────────────────────────────────────────
        raise RuntimeError(
            f"Authentication failed: could not obtain enctoken or request_token.\n"
            f"TOTP HTTP status={r2.status_code}\n"
            f"Set-Cookie header: {r2.headers.get('Set-Cookie', '(empty)')[:200]}\n"
            f"Response body: {r2.text[:200]}"
        )

    def _save_token(self, token_data, token_type):
        os.makedirs(LOG_DIR, exist_ok=True)
        payload = {"date": str(date.today()), "type": token_type}
        if isinstance(token_data, dict):
            payload.update(token_data)       # saves enctoken + user_id + public_token
        else:
            payload["token"] = token_data
        with open(TOKEN_FILE, "w") as f:
            json.dump(payload, f)

    def _load_token(self):
        if not os.path.exists(TOKEN_FILE):
            return None
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        if data.get("date") != str(date.today()):
            return None
        return data

    def _is_token_valid(self):
        if self._kite and self._token:
            return True
        data = self._load_token()
        if not data:
            return False
        try:
            token_type = data.get("type", "enctoken")
            if token_type == "enctoken":
                enctoken     = data.get("enctoken", "")
                user_id      = data.get("user_id", "")
                public_token = data.get("public_token", "")
                if not enctoken:
                    return False
                kite = KiteEncTokenWrapper(ZERODHA_API_KEY, enctoken, user_id, public_token)
            else:
                kite = KiteConnect(api_key=ZERODHA_API_KEY)
                kite.set_access_token(data.get("token", ""))
            kite.profile()
            self._kite       = kite
            self._token      = data.get("enctoken") or data.get("token", "")
            self._token_type = token_type
            log.info(f"Loaded cached {token_type} for today.")
            return True
        except Exception:
            log.warning("Cached token invalid — re-authenticating...")
            return False


_session = None

def get_session():
    global _session
    if _session is None:
        _session = SessionManager()
    return _session

def get_kite():
    return get_session().get_kite()
