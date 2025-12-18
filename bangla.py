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

os.makedirs(SAVE_DIR, exist_ok=True)

# =====================================================
# TOKEN FETCH (NEW LOGIN METHOD)
# =====================================================
def get_guest_token():
    URL = "https://ticket.cineplexbd.com/login"
    API_KEYWORD = "/api/v1/guest-login"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
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
        "pragma": "no-cache",
        "referer": "https://ticket.cineplexbd.com/",
        "user-agent": random.choice(USER_AGENTS)
    }
    if bearer:
        h["authorization"] = f"Bearer {bearer}"
    return h

def safe_post(url, headers, payload):
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
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
            movies.setdefault(date, {}).setdefault(
                mid, {"title": title, "locs": set()}
            )
            movies[date][mid]["locs"].add(loc)

print(f"🎬 Found {sum(len(v) for v in movies.values())} movie-date entries.\n")

# =====================================================
# STEP 3: THREADED FETCH
# =====================================================
def fetch_show_details(args):
    loc, movie_id, date, title = args
    result = []

    show = safe_post(
        f"{API_BASE}/get-shows",
        random_headers(bearer),
        {"location": loc, "movieId": movie_id, "showDate": date}
    )

    if not show or "data" not in show or not show["data"]:
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

        data = seat["data"]
        seat_types = data.get("seatTypes") or []
        if not isinstance(seat_types, list):
            seat_types = []

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

print(f"🚀 Fetching {len(tasks)} tasks using {MAX_WORKERS} threads...\n")

results = []
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = [ex.submit(fetch_show_details, t) for t in tasks]
    for f in as_completed(futures):
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

    for new_show in shows:
        key = (new_show["programId"], new_show["location"], new_show["showTime"])
        existing = next(
            (s for s in daily[title]
             if (s["programId"], s["location"], s["showTime"]) == key),
            None
        )
        if existing:
            existing.update(new_show)
        else:
            daily[title].append(new_show)

    save_json(path, daily)

# =====================================================
# STEP 5: SUMMARY
# =====================================================
for date in sorted({d for d, _, _ in results}):
    path = os.path.join(SAVE_DIR, f"{date}.json")
    data = load_json(path)

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
            f"{title[:43]:45} {len(shows):5} {sold:6} {total:6} {gross:9} {occ:6.2f}% {atp:7.2f}"
        )

print("\n✅ Data saved under:", os.path.abspath(SAVE_DIR))
print("⏰ Last Updated:", datetime.now().strftime("%I:%M %p, %d %B %Y"))
