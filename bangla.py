import requests
import json
import os
import time
import random
import string
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

# =====================================================
# CONFIG
# =====================================================
API_BASE = "https://cineplex-ticket-api.cineplexbd.com/api/v1"
LOCATIONS = range(1, 9)
MAX_WORKERS = 8
SAVE_DIR = "Bangladesh"
DEBUG_DIR = os.path.join(SAVE_DIR, "debug")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36",
]

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

# 🔥 ONE DEVICE KEY (MANDATORY)
DEVICE_KEY = ''.join(random.choices('abcdef' + string.digits, k=64))

# =====================================================
# STEP 1: GET GUEST TOKEN (CI-SAFE)
# =====================================================
def get_guest_token():
    URL = "https://ticket.cineplexbd.com/login"
    token_box = {"token": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = browser.new_context(
            extra_http_headers={"device-key": DEVICE_KEY}
        )
        page = context.new_page()

        def on_response(resp):
            if "/api/v1/guest-login" in resp.url and resp.status == 200:
                try:
                    data = resp.json()
                    token_box["token"] = data.get("data", {}).get("token")
                except Exception:
                    pass

        # 🔥 LISTENER FIRST (NO RACE)
        page.on("response", on_response)

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        page.wait_for_selector(
            "button.btn.btn-button.guest-login.btn-block",
            timeout=30000
        )

        page.click("button.btn.btn-button.guest-login.btn-block")

        # manual wait (max 15s)
        for _ in range(150):
            if token_box["token"]:
                break
            time.sleep(0.1)

        browser.close()

    if not token_box["token"]:
        raise RuntimeError("❌ Guest token capture failed")

    return token_box["token"]

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
        "device-key": DEVICE_KEY,
    }

def safe_post(url, hdrs, payload, debug_path=None):
    try:
        r = requests.post(url, headers=hdrs, json=payload, timeout=20)

        try:
            content = r.json()
        except Exception:
            content = r.text

        if debug_path:
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

    except Exception as e:
        if debug_path:
            with open(debug_path, "w", encoding="utf-8") as f:
                json.dump({"error": str(e)}, f, indent=2)

    return None

# =====================================================
# STEP 2: LOGIN
# =====================================================
print("🔐 Fetching fresh guest token...")
bearer = get_guest_token()
print(f"✅ Logged in. Token: {bearer[:12]}...\n")

# =====================================================
# STEP 3: GET SHOW DATES (DEBUG ENABLED)
# =====================================================
movies = {}

for loc in LOCATIONS:
    debug_file = os.path.join(DEBUG_DIR, f"location_{loc}_get-showdate.json")

    res = safe_post(
        f"{API_BASE}/get-showdate",
        headers(bearer),
        {"location": loc},
        debug_path=debug_file
    )

    if not res or not isinstance(res.get("data"), list):
        print(f"⚠️ Location {loc}: no usable data (raw saved)")
        continue

    for entry in res["data"]:
        date = entry.get("showDate")
        for mv in entry.get("availableMovies", []):
            mid = mv.get("movie_id")
            title = mv.get("movie_title")
            if not mid or not title:
                continue

            movies.setdefault(date, {}).setdefault(
                mid, {"title": title, "locs": set()}
            )
            movies[date][mid]["locs"].add(loc)

print(f"\n🎬 Found {sum(len(v) for v in movies.values())} movie-date entries.\n")

print("✅ Token + device-key working. Debug files saved.")
print("⏰ Last Updated:", datetime.now().strftime("%I:%M %p, %d %B %Y"))
