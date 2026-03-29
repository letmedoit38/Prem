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
print(f"  Headers : {dict(r2.headers)}")
print(f"  Response: {r2.text[:1000]}")
print()

print("STEP 2b: POST /api/twofa  (allow_redirects=True, fresh TOTP)")
import time; time.sleep(2)
totp_code2 = pyotp.TOTP(TOTP_SECRET).now()

r1b = session.post("https://kite.zerodha.com/api/login",
                   data={"user_id": USER_ID, "password": PASSWORD}, timeout=15)
request_id2 = r1b.json()["data"]["request_id"]

r2b = session.post("https://kite.zerodha.com/api/twofa",
                   data={"user_id": USER_ID, "request_id": request_id2,
                         "twofa_value": totp_code2, "twofa_type": "totp"},
                   timeout=15, allow_redirects=True)

print(f"  Status  : {r2b.status_code}")
print(f"  Final URL: {r2b.url}")
print(f"  Response: {r2b.text[:500]}")
print()

print("=" * 60)
print("  Copy ALL output above and share it to fix the auth code.")
print("=" * 60)
input("\nPress Enter to exit...")
