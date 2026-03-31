import os, json
from dotenv import load_dotenv
load_dotenv()

import pyotp, requests

USER_ID     = os.getenv("ZERODHA_USER_ID", "")
PASSWORD    = os.getenv("ZERODHA_PASSWORD", "")
TOTP_SECRET = os.getenv("ZERODHA_TOTP_SECRET", "")
API_KEY     = os.getenv("ZERODHA_API_KEY", "")

print("=" * 60)
print("  ZERODHA AUTH DEBUGGER")
print("=" * 60)
print(f"  User ID   : {USER_ID}")
print(f"  API Key   : {API_KEY[:6]}...{API_KEY[-4:] if len(API_KEY) > 10 else API_KEY}")
print(f"  TOTP now  : {pyotp.TOTP(TOTP_SECRET).now()}")
print()

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
})

print("STEP 1: POST /api/login")
r1 = session.post("https://kite.zerodha.com/api/login",
                  data={"user_id": USER_ID, "password": PASSWORD},
                  timeout=15)
print(f"  Status  : {r1.status_code}")
print(f"  Response: {r1.text[:500]}")
print()

if r1.status_code != 200 or r1.json().get("status") != "success":
    print("FAILED at login. Check USER_ID and PASSWORD in .env")
    input("Press Enter to exit...")
    exit(1)

request_id = r1.json()["data"]["request_id"]
print(f"  request_id = {request_id}")
print()

print("STEP 2: POST /api/twofa  (allow_redirects=False)")
totp_code = pyotp.TOTP(TOTP_SECRET).now()
print(f"  TOTP code being sent: {totp_code}")

r2 = session.post("https://kite.zerodha.com/api/twofa",
                  data={"user_id": USER_ID, "request_id": request_id,
                        "twofa_value": totp_code, "twofa_type": "totp"},
                  timeout=15, allow_redirects=False)

print(f"  Status  : {r2.status_code}")
print(f"  Location: {r2.headers.get('Location', '(none)')}")
print(f"  Response: {r2.text[:500]}")
print()

print(f"  All cookies in session after twofa:")
for c in session.cookies:
    print(f"    {c.name}={c.value[:20]}...  domain={c.domain}")
print()

# Extract enctoken
enctoken = session.cookies.get("enctoken") or ""
user_id_cookie = session.cookies.get("user_id") or USER_ID

if not enctoken:
    # Try parsing from r2 headers
    import re
    m = re.search(r"enctoken=([^;,\s]+)", r2.headers.get("Set-Cookie", ""))
    if m:
        enctoken = m.group(1)

print(f"  enctoken found: {'YES (' + enctoken[:12] + '...)' if enctoken else 'NO'}")
print()

# ── STEP 3: Test enctoken directly using the SAME session ────────────────
# kf_session = Django CSRF token — must be sent as X-CSRFToken header
csrf_token = session.cookies.get("kf_session") or ""
print(f"  kf_session (CSRF): {'YES (' + csrf_token[:12] + '...)' if csrf_token else 'MISSING'}")
print()

print("STEP 3: Test /api/user/profile using authenticated session (reused) + X-CSRFToken")
session.headers.update({
    "X-Kite-Version": "3",
    "Authorization":  f"enctoken {enctoken}",
    "X-Kite-Userid":  user_id_cookie,
    "X-CSRFToken":    csrf_token,
    "Referer":        "https://kite.zerodha.com/dashboard",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
})
r3 = session.get("https://kite.zerodha.com/api/user/profile", timeout=15)
print(f"  Status  : {r3.status_code}")
print(f"  Response: {r3.text[:500]}")
print()

# ── STEP 4: Test enctoken with a fresh session ────────────────────────────
print("STEP 4: Test /api/user/profile using FRESH session (manual cookies + X-CSRFToken)")
fresh = requests.Session()
fresh.headers.update({
    "X-Kite-Version": "3",
    "Authorization":  f"enctoken {enctoken}",
    "X-Kite-Userid":  user_id_cookie,
    "X-CSRFToken":    csrf_token,
    "Referer":        "https://kite.zerodha.com/dashboard",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
})
fresh.cookies.set("user_id",    user_id_cookie, domain="kite.zerodha.com")
fresh.cookies.set("enctoken",   enctoken,        domain="kite.zerodha.com")
fresh.cookies.set("kf_session", csrf_token,      domain="kite.zerodha.com")
r4 = fresh.get("https://kite.zerodha.com/api/user/profile", timeout=15)
print(f"  Status  : {r4.status_code}")
print(f"  Response: {r4.text[:500]}")
print()

print("=" * 60)
print("  Copy ALL output above and share it to fix the auth code.")
print("  Step 3 = reused session | Step 4 = fresh session")
print("  If Step 3 passes but Step 4 fails → need to reuse session")
print("  If both fail → enctoken itself is invalid (re-check credentials)")
print("=" * 60)
input("\nPress Enter to exit...")
