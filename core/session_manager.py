import os, json, pyotp, requests
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


class KiteEncTokenWrapper:
    """Drop-in replacement for KiteConnect using enctoken authentication."""
    BASE = "https://api.kite.trade"
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

    def __init__(self, api_key, enctoken):
        self.api_key = api_key
        self._enctoken = enctoken
        self._sess = requests.Session()
        self._sess.headers.update({
            "X-Kite-Version": "3",
            "Authorization": f"enctoken {enctoken}",
        })

    def profile(self):
        return self._get("/user/profile")["data"]

    def margins(self, segment=None):
        path = f"/user/margins/{segment}" if segment else "/user/margins"
        return self._get(path)["data"]

    def ltp(self, instruments):
        return self._get("/quote/ltp", params={"i": instruments})["data"]

    def quote(self, instruments):
        return self._get("/quote", params={"i": instruments})["data"]

    def instruments(self, exchange=None):
        path = f"/instruments/{exchange}" if exchange else "/instruments"
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
            f"/instruments/historical/{instrument_token}/{interval}", params=params
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
        return str(self._post(f"/orders/{variety}", data=data)["data"]["order_id"])

    def orders(self):
        return self._get("/orders")["data"]

    def positions(self):
        return self._get("/portfolio/positions")["data"]

    def set_access_token(self, token):
        pass

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
        if r.status_code != 200:
            try:
                msg = r.json().get("message", r.text[:200])
            except Exception:
                msg = r.text[:200]
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

        r1 = session.post("https://kite.zerodha.com/api/login", data={
            "user_id": ZERODHA_USER_ID, "password": ZERODHA_PASSWORD,
        }, timeout=15)
        r1.raise_for_status()
        login_data = r1.json()
        if login_data.get("status") != "success":
            raise RuntimeError(f"Login failed: {login_data}")
        request_id = login_data["data"]["request_id"]
        log.info("Password accepted, submitting TOTP...")

        totp_code = pyotp.TOTP(ZERODHA_TOTP_SECRET).now()
        r2 = session.post("https://kite.zerodha.com/api/twofa", data={
            "user_id": ZERODHA_USER_ID, "request_id": request_id,
            "twofa_value": totp_code, "twofa_type": "totp",
        }, timeout=15, allow_redirects=False)

        if r2.status_code == 200:
            try:
                body = r2.json()
                if body.get("status") == "error":
                    raise RuntimeError(f"TOTP rejected: {body.get('message', body)}")
            except ValueError:
                pass

        enctoken = r2.cookies.get("enctoken") or session.cookies.get("enctoken", "")

        if enctoken:
            log.info("enctoken received - authenticating via enctoken.")
            self._kite = KiteEncTokenWrapper(ZERODHA_API_KEY, enctoken)
            profile = self._kite.profile()
            log.info(f"Logged in as: {profile.get('user_name')} ({profile.get('user_id')})")
            self._token = enctoken
            self._token_type = "enctoken"
            self._save_token(enctoken, "enctoken")
            return

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

        raise RuntimeError(
            f"Authentication failed: no enctoken or request_token.\n"
            f"TOTP status={r2.status_code}, body={r2.text[:300]}"
        )

    def _save_token(self, token, token_type):
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            json.dump({"date": str(date.today()), "token": token, "type": token_type}, f)

    def _load_token(self):
        if not os.path.exists(TOKEN_FILE):
            return None, "enctoken"
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        if data.get("date") == str(date.today()):
            return data.get("token"), data.get("type", "enctoken")
        return None, "enctoken"

    def _is_token_valid(self):
        if self._kite and self._token:
            return True
        token, token_type = self._load_token()
        if not token:
            return False
        try:
            if token_type == "enctoken":
                kite = KiteEncTokenWrapper(ZERODHA_API_KEY, token)
            else:
                kite = KiteConnect(api_key=ZERODHA_API_KEY)
                kite.set_access_token(token)
            kite.profile()
            self._kite = kite
            self._token = token
            self._token_type = token_type
            log.info(f"Loaded cached {token_type} for today.")
            return True
        except Exception:
            log.warning("Cached token invalid, re-authenticating...")
            return False


_session = None

def get_session():
    global _session
    if _session is None:
        _session = SessionManager()
    return _session

def get_kite():
    return get_session().get_kite()
