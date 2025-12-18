import requests, json, os, time, random, string, re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

# ================= CONFIG =================
LOGIN_URL = "https://ticket.cineplexbd.com/login"
API_BASE = "https://cineplex-ticket-api.cineplexbd.com/api/v1"
LOCATIONS = range(1, 9)
MAX_WORKERS = 8
SAVE_DIR = "Bangladesh"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; rv:123.0) Gecko/20100101 Firefox/123.0"
]

os.makedirs(SAVE_DIR, exist_ok=True)

# ================= LOGIN VIA PLAYWRIGHT =================
def get_bearer_token():
    print("🌐 Opening browser for Guest Login...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        bearer = None

        def on_response(resp):
            nonlocal bearer
            if "/api/v1/guest-login" in resp.url:
                try:
                    data = resp.json()
                    token = data.get("data", {}).get("token")
                    if token:
                        bearer = token
                        print("\n✅ LOGIN SUCCESSFUL — TOKEN CAPTURED\n")
                except:
                    pass

        page.on("response", on_response)

        page.goto(LOGIN_URL, wait_until="networkidle")

        print("🧑 ACTION REQUIRED:")
        print("👉 Click **Guest Login** in the browser")
        print("👉 Complete login normally\n")

        timeout = time.time() + 180
        while not bearer and time.time() < timeout:
            time.sleep(1)

        browser.close()

        if not bearer:
            raise SystemExit("❌ Failed to capture bearer token")

        return bearer

# ================= HELPERS =================
def random_device_key():
    return ''.join(random.choices('abcdef' + string.digits, k=64))

def random_headers(bearer=None):
    h = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-GB,en;q=0.9",
        "appsource": "web",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "device-key": random_device_key(),
        "origin": "https://ticket.cineplexbd.com",
        "referer": "https://ticket.cineplexbd.com/",
        "user-agent": random.choice(USER_AGENTS)
    }
    if bearer:
        h["authorization"] = f"Bearer {bearer}"
    return h

def safe_post(url, headers, payload):
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

# ================= MAIN =================
bearer = get_bearer_token()
print(f"🔑 Bearer token ready: {bearer[:10]}...\n")

# ===== STEP 2: Get movies =====
movies = {}

for loc in LOCATIONS:
    res = safe_post(
        f"{API_BASE}/get-showdate",
        random_headers(bearer),
        {"location": loc}
    )
    if not res or "data" not in res:
        continue

    for entry in res["data"]:
        date = entry["showDate"]
        for mv in entry["availableMovies"]:
            mid = mv["movie_id"]
            title = mv["movie_title"]
            movies.setdefault(date, {}).setdefault(mid, {"title": title, "locs": set()})
            movies[date][mid]["locs"].add(loc)

print(f"🎬 Found {sum(len(v) for v in movies.values())} movie-date entries\n")

# ===== STEP 3: Fetch shows =====
def fetch_show_details(args):
    loc, movie_id, date, title = args
    result = []

    show = safe_post(
        f"{API_BASE}/get-shows",
        random_headers(bearer),
        {"location": loc, "movieId": movie_id, "showDate": date}
    )

    if not show or not show.get("data"):
        return None

    for s in show["data"][0]["showTimes"]:
        pid = s["programId"]
        show_time = s["showTime"]
        prices = {p["seatTypeID"]: p["unitPrice"] for p in s["seatPrices"]}

        seat = safe_post(
            f"{API_BASE}/get-seat",
            random_headers(bearer),
            {"location": loc, "programId": pid}
        )

        if not seat or "data" not in seat:
            continue

        total = sold = gross = 0
        for st in seat["data"].get("seatTypes", []):
            statuses = st.get("seatStatus") or []
            sold_count = sum(1 for x in statuses if x.get("seatStatus") == 0)
            total += len(statuses)
            sold += sold_count
            gross += sold_count * prices.get(st.get("seatTypeId"), 0)

        result.append({
            "programId": pid,
            "location": loc,
            "showTime": show_time,
            "total": total,
            "sold": sold,
            "gross": gross
        })

    return (date, title, result)

tasks = [
    (loc, mid, date, movies[date][mid]["title"])
    for date in movies
    for mid in movies[date]
    for loc in movies[date][mid]["locs"]
]

results = []
with ThreadPoolExecutor(MAX_WORKERS) as ex:
    for f in as_completed([ex.submit(fetch_show_details, t) for t in tasks]):
        if f.result():
            results.append(f.result())

# ===== SAVE =====
for date, title, shows in results:
    path = os.path.join(SAVE_DIR, f"{date}.json")
    daily = json.load(open(path)) if os.path.exists(path) else {}
    daily.setdefault(title, []).extend(shows)
    json.dump(daily, open(path, "w"), indent=2)

print("\n✅ Data saved under:", os.path.abspath(SAVE_DIR))
print("⏰ Last Updated:", datetime.now().strftime("%I:%M %p, %d %B %Y"))
