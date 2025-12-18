import os, json, time, random, string, requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= CONFIG =================
API_BASE = "https://cineplex-ticket-api.cineplexbd.com/api/v1"
LOCATIONS = range(1, 9)
MAX_WORKERS = 8
SAVE_DIR = "Bangladesh"

LOGIN_URL = "https://ticket.cineplexbd.com/login"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh) Version/17 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13) Chrome/120 Mobile"
]

os.makedirs(SAVE_DIR, exist_ok=True)

# ================= HELPERS =================
def random_device_key():
    return ''.join(random.choices('abcdef' + string.digits, k=64))

def random_headers(bearer=None):
    h = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-GB,en;q=0.9",
        "appsource": "web",
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
    except Exception:
        pass
    return None

# ================= STEP 1: AUTO LOGIN (SELENIUM) =================
def selenium_guest_login():
    """
    Works ONLY on local machine / VPS / self-hosted runner.
    Will FAIL gracefully on GitHub hosted / Replit.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        print("🧭 Attempting Selenium Guest Login...")

        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--start-maximized")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        token = None

        def capture_token(request):
            nonlocal token
            if "/guest-login" in request.url and request.response:
                try:
                    data = request.response.json()
                    token = data.get("data", {}).get("token")
                except Exception:
                    pass

        driver.get(LOGIN_URL)
        time.sleep(5)

        btn = driver.find_element(By.CSS_SELECTOR, "button.guest-login")
        btn.click()
        print("🟢 Guest Login clicked")

        timeout = time.time() + 60
        while not token and time.time() < timeout:
            time.sleep(1)

        driver.quit()

        if token:
            print("✅ Selenium login successful")
            return token

    except Exception as e:
        print("⚠ Selenium login not available:", e)

    return None

# ================= GET TOKEN =================
bearer = os.getenv("BD_BEARER")

if not bearer:
    bearer = selenium_guest_login()

if not bearer:
    raise SystemExit(
        "❌ No bearer token available.\n"
        "➡ Use local machine OR set BD_BEARER secret."
    )

print(f"🔑 Using Bearer: {bearer[:10]}...")

# ================= STEP 2: SHOWDATES =================
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

print(f"🎬 Found {sum(len(v) for v in movies.values())} movie-date entries")

# ================= STEP 3: FETCH SHOWS =================
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
        prices = {p["seatTypeID"]: p["unitPrice"] for p in s["seatPrices"]}

        seat = safe_post(
            f"{API_BASE}/get-seat",
            random_headers(bearer),
            {"location": loc, "programId": pid}
        )
        if not seat or "data" not in seat:
            continue

        total = sold = gross = 0
        for st in seat["data"].get("seatTypes", []) or []:
            statuses = st.get("seatStatus", [])
            sc = sum(1 for x in statuses if x.get("seatStatus") == 0)
            total += len(statuses)
            sold += sc
            gross += sc * prices.get(st.get("seatTypeId"), 0)

        result.append({
            "programId": pid,
            "location": loc,
            "showTime": s["showTime"],
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
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    for f in as_completed(ex.submit(fetch_show_details, t) for t in tasks):
        if f.result():
            results.append(f.result())

# ================= STEP 4: SAVE =================
def load_json(p):
    return json.load(open(p)) if os.path.exists(p) else {}

for date, title, shows in results:
    path = f"{SAVE_DIR}/{date}.json"
    daily = load_json(path)
    daily.setdefault(title, []).extend(shows)
    json.dump(daily, open(path, "w"), indent=2)

print("✅ Data saved")
print("⏰ Updated:", datetime.now().strftime("%d %b %Y %I:%M %p"))
