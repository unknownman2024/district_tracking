import requests, json, os, time, random, string
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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; rv:123.0) Gecko/20100101 Firefox/123.0"
]

# 🔥 ONE DEVICE KEY FOR ENTIRE SESSION (CRITICAL)
DEVICE_KEY = ''.join(random.choices('abcdef' + string.digits, k=64))

os.makedirs(SAVE_DIR, exist_ok=True)

# =====================================================
# LOGIN (BROWSER VERIFIED)
# =====================================================
def get_guest_token():
    URL = "https://ticket.cineplexbd.com/login"
    API_KEYWORD = "/api/v1/guest-login"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            extra_http_headers={
                "device-key": DEVICE_KEY
            }
        )

        page = context.new_page()
        page.goto(URL, wait_until="networkidle")

        page.wait_for_selector(
            "button.btn.btn-button.guest-login.btn-block",
            timeout=15000
        )

        with page.expect_response(
            lambda r: API_KEYWORD in r.url and r.status == 200,
            timeout=15000
        ) as resp:
            page.click("button.btn.btn-button.guest-login.btn-block")

        data = resp.value.json()
        browser.close()

    token = data.get("data", {}).get("token")
    if not token:
        raise RuntimeError("❌ Guest token not found")

    return token

# =====================================================
# HELPERS
# =====================================================
def headers(bearer=None):
    h = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-GB,en;q=0.9",
        "appsource": "web",
        "cache-control": "no-cache",
        "content-type": "application/json;charset=UTF-8",
        "device-key": DEVICE_KEY,   # 🔥 SAME KEY ALWAYS
        "origin": "https://ticket.cineplexbd.com",
        "pragma": "no-cache",
        "referer": "https://ticket.cineplexbd.com/",
        "user-agent": random.choice(USER_AGENTS)
    }
    if bearer:
        h["authorization"] = f"Bearer {bearer}"
    return h

def safe_post(url, headers_, payload, retry=1):
    for _ in range(retry + 1):
        try:
            r = requests.post(url, headers=headers_, json=payload, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            time.sleep(0.4)
    return None

# =====================================================
# STEP 1: LOGIN
# =====================================================
print("🔐 Fetching fresh guest token...")
bearer = get_guest_token()
print(f"✅ Logged in. Token: {bearer[:12]}...\n")

# =====================================================
# STEP 2: GET MOVIES PER DATE PER LOCATION
# =====================================================
movies = {}

for loc in LOCATIONS:
    res = safe_post(
        f"{API_BASE}/get-showdate",
        headers(bearer),
        {"location": loc}
    )

    if not res or not isinstance(res.get("data"), list):
        print(f"⚠️ Location {loc}: no usable data")
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

# =====================================================
# STEP 3: THREADED SHOW + SEAT FETCH
# =====================================================
def fetch_show_details(args):
    loc, movie_id, date, title = args
    result = []

    show = safe_post(
        f"{API_BASE}/get-shows",
        headers(bearer),
        {"location": loc, "movieId": movie_id, "showDate": date}
    )

    if not show or not show.get("data"):
        return None

    for s in show["data"][0].get("showTimes", []):
        pid = s.get("programId")
        if not pid:
            continue

        prices = {p["seatTypeID"]: p["unitPrice"] for p in s.get("seatPrices", [])}

        seat = safe_post(
            f"{API_BASE}/get-seat",
            headers(bearer),
            {"location": loc, "programId": pid}
        )

        if not seat or not seat.get("data"):
            continue

        seat_types = seat["data"].get("seatTypes") or []
        total = sold = gross = 0

        for st in seat_types:
            sid = st.get("seatTypeId")
            statuses = st.get("seatStatus") or []
            sold_count = sum(1 for x in statuses if x.get("seatStatus") == 0)
            total += len(statuses)
            sold += sold_count
            gross += sold_count * prices.get(sid, 0)

        result.append({
            "programId": pid,
            "location": loc,
            "showTime": s.get("showTime"),
            "total": total,
            "sold": sold,
            "gross": gross
        })

    return (date, title, result) if result else None

tasks = [
    (loc, mid, date, movies[date][mid]["title"])
    for date in movies
    for mid in movies[date]
    for loc in movies[date][mid]["locs"]
]

print(f"🚀 Fetching {len(tasks)} tasks using {MAX_WORKERS} threads...\n")

results = []
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    for f in as_completed(ex.submit(fetch_show_details, t) for t in tasks):
        if f.result():
            results.append(f.result())

# =====================================================
# STEP 4: SAVE DAILY JSONs
# =====================================================
def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

for date, title, shows in results:
    path = os.path.join(SAVE_DIR, f"{date}.json")
    daily = load_json(path)
    daily.setdefault(title, [])

    for show in shows:
        key = (show["programId"], show["location"], show["showTime"])
        old = next(
            (s for s in daily[title]
             if (s["programId"], s["location"], s["showTime"]) == key),
            None
        )
        old.update(show) if old else daily[title].append(show)

    save_json(path, daily)

# =====================================================
# STEP 5: SUMMARY
# =====================================================
for date in sorted({d for d, _, _ in results}):
    data = load_json(os.path.join(SAVE_DIR, f"{date}.json"))

    print(f"\n------------------ {date} ------------------")
    print(f"{'Movie':45} {'Shows':>5} {'Sold':>6} {'Total':>6} {'Gross':>9} {'Occ%':>7} {'ATP':>7}")
    print("-" * 90)

    for title, shows in data.items():
        sold = sum(s["sold"] for s in shows)
        total = sum(s["total"] for s in shows)
        gross = sum(s["gross"] for s in shows)

        occ = (sold / total * 100) if total else 0
        atp = (gross / sold) if sold else 0

        print(
            f"{title[:43]:45} {len(shows):5} {sold:6} {total:6} "
            f"{gross:9} {occ:6.2f}% {atp:7.2f}"
        )

print("\n✅ Data saved under:", os.path.abspath(SAVE_DIR))
print("⏰ Last Updated:", datetime.now().strftime("%I:%M %p, %d %B %Y"))
