import requests
import json
import os
import random
import string
from datetime import datetime
from playwright.sync_api import sync_playwright

# =====================================================
# CONFIG
# =====================================================
API_BASE = "https://cineplex-ticket-api.cineplexbd.com/api/v1"
LOCATIONS = range(1, 9)
SAVE_DIR = "Bangladesh"
DEBUG_DIR = os.path.join(SAVE_DIR, "debug")

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
]

# 🔥 ONE DEVICE KEY (MANDATORY FOR API)
DEVICE_KEY = ''.join(random.choices('abcdef' + string.digits, k=64))

# =====================================================
# STEP 1: GET GUEST TOKEN (YOUR EXACT CODE)
# =====================================================
def get_guest_token():
    URL = "https://ticket.cineplexbd.com/login"
    API_KEYWORD = "/api/v1/guest-login"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            extra_http_headers={
                "device-key": DEVICE_KEY   # ONLY addition
            }
        )
        page = context.new_page()

        print("🔹 STEP 1: Visiting login page")
        page.goto(URL, wait_until="networkidle")

        print("🔹 STEP 2: Waiting for Guest Login button")
        page.wait_for_selector(
            "button.btn.btn-button.guest-login.btn-block",
            timeout=15000
        )

        print("🔹 STEP 3: Clicking Guest Login button")

        with page.expect_response(
            lambda r: API_KEYWORD in r.url and r.status == 200,
            timeout=15000
        ) as response_info:
            page.click("button.btn.btn-button.guest-login.btn-block")

        response = response_info.value
        data = response.json()

        browser.close()

    token = data.get("data", {}).get("token")
    if not token:
        raise RuntimeError("Guest token not found")

    return token

# =====================================================
# HELPERS
# =====================================================
def headers(bearer):
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-GB,en;q=0.9",
        "appsource": "web",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://ticket.cineplexbd.com",
        "referer": "https://ticket.cineplexbd.com/",
        "user-agent": random.choice(USER_AGENTS),
        "authorization": f"Bearer {bearer}",
        "device-key": DEVICE_KEY,   # 🔥 REQUIRED
    }

def safe_post(url, hdrs, payload, debug_path):
    r = requests.post(url, headers=hdrs, json=payload, timeout=20)

    try:
        content = r.json()
    except Exception:
        content = r.text

    with open(debug_path, "w", encoding="utf-8") as f:
        json.dump({
            "url": url,
            "payload": payload,
            "status_code": r.status_code,
            "headers_sent": hdrs,
            "response": content
        }, f, indent=2, ensure_ascii=False)

    if r.status_code == 200 and isinstance(content, dict):
        return content

    return None

# =====================================================
# STEP 2: LOGIN
# =====================================================
print("🔐 Fetching fresh guest token...")
bearer = get_guest_token()
print(f"✅ Logged in. Token: {bearer}\n")

# =====================================================
# STEP 3: GET SHOWDATE (SAVE RAW RESPONSE)
# =====================================================
for loc in LOCATIONS:
    debug_file = os.path.join(DEBUG_DIR, f"location_{loc}_get-showdate.json")

    res = safe_post(
        f"{API_BASE}/get-showdate",
        headers(bearer),
        {"location": loc},
        debug_file
    )

    if not res:
        print(f"⚠️ Location {loc}: no usable data (saved raw)")
    else:
        print(f"✅ Location {loc}: response saved")

print("\n🪵 Debug files saved in:", DEBUG_DIR)
print("⏰ Last Updated:", datetime.now().strftime("%I:%M %p, %d %B %Y"))
