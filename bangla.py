import json
import os
import sys
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# ---------------- SELENIUM WIRE ----------------
from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- CONFIG ----------------
NUM_WORKERS = 3
MAX_ERRORS = 10

IST = timezone(timedelta(hours=5, minutes=30))
DATE_CODE = (datetime.now(IST) + timedelta(days=1)).strftime("%Y%m%d")

BASE_DIR = DATE_CODE
os.makedirs(BASE_DIR, exist_ok=True)

FETCHED_FILE = f"{BASE_DIR}/fetchedvenues.json"
FAILED_FILE = f"{BASE_DIR}/failedvenues.json"
DATA_FILE = f"{BASE_DIR}/venues_data.json"

lock = threading.Lock()
error_count = 0
thread_local = threading.local()

# ---------------- USER AGENT ----------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

def random_ip():
    return ".".join(str(random.randint(10, 240)) for _ in range(4))

# ---------------- DRIVER ----------------
def get_driver():
    if hasattr(thread_local, "driver"):
        return thread_local.driver

    ua = random.choice(USER_AGENTS)
    ip = random_ip()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={ua}")

    seleniumwire_options = {
        "disable_encoding": True,
        "custom_headers": {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://in.bookmyshow.com",
            "Referer": "https://in.bookmyshow.com",
            "X-Forwarded-For": ip,
            "Client-IP": ip,
        },
    }

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
        seleniumwire_options=seleniumwire_options,
    )

    thread_local.driver = driver
    return driver

# ---------------- SELENIUM FETCH ----------------
def selenium_fetch_json(url, timeout=25):
    driver = get_driver()
    driver.scopes = [".*bookmyshow.com/api/.*"]
    driver.requests.clear()

    driver.get(url)
    end = time.time() + timeout

    while time.time() < end:
        for req in driver.requests:
            if req.response and url in req.url:
                text = req.response.body.decode("utf-8", errors="ignore").strip()

                # 🔴 Cloudflare / HTML guard
                if not text.startswith("{"):
                    raise ValueError("Non-JSON response (Cloudflare / HTML)")

                return json.loads(text)

        time.sleep(0.25)

    raise TimeoutError("API response not captured")

# ---------------- FETCH DATA ----------------
def fetch_data(venue_code):
    url = (
        "https://in.bookmyshow.com/api/v2/mobile/showtimes/byvenue"
        f"?venueCode={venue_code}&dateCode={DATE_CODE}"
    )

    try:
        data = selenium_fetch_json(url)
    except Exception as e:
        print(f"⚠️ Failed {venue_code}: {e}")
        return None

    show_details = data.get("ShowDetails", [])
    if not show_details:
        return {}

    venue_info = show_details[0].get("Venues", {})
    if not venue_info:
        return {}

    venue_name = venue_info.get("VenueName", "")
    venue_add = venue_info.get("VenueAdd", "")
    shows_by_movie = defaultdict(list)

    for event in show_details[0].get("Event", []):
        parent_title = event.get("EventTitle", "Unknown")

        for child in event.get("ChildEvents", []):
            dim = child.get("EventDimension", "").strip()
            lang = child.get("EventLanguage", "").strip()
            parts = [x for x in [dim, lang] if x]
            movie = f"{parent_title} [{' | '.join(parts)}]" if parts else parent_title

            for show in child.get("ShowTimes", []):
                total = sold = available = gross = 0
                for cat in show.get("Categories", []):
                    seats = int(cat.get("MaxSeats", 0))
                    avail = int(cat.get("SeatsAvail", 0))
                    price = float(cat.get("CurPrice", 0))
                    total += seats
                    available += avail
                    sold += seats - avail
                    gross += (seats - avail) * price

                shows_by_movie[movie].append({
                    "venue": venue_name,
                    "address": venue_add,
                    "movie": movie,
                    "time": show.get("ShowTime"),
                    "total": total,
                    "sold": sold,
                    "available": available,
                    "occupancy": round((sold / total * 100), 2) if total else 0,
                    "gross": gross,
                })

    return shows_by_movie

# ---------------- LOAD STATE ----------------
def load_set(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return set(json.load(f))
    return set()

fetched_venues = load_set(FETCHED_FILE)
failed_venues = load_set(FAILED_FILE)

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        all_data = json.load(f)
else:
    all_data = {}

# ---------------- SAVE STATE ----------------
def dump_progress():
    with open(DATA_FILE, "w") as f:
        json.dump(all_data, f)

    with open(FETCHED_FILE, "w") as f:
        json.dump(list(fetched_venues), f)

    with open(FAILED_FILE, "w") as f:
        json.dump(list(failed_venues), f)

    print(f"💾 Saved | fetched={len(fetched_venues)} failed={len(failed_venues)}")

# ---------------- SAFE FETCH ----------------
def fetch_venue_safe(venue_code):
    global error_count

    with lock:
        if venue_code in fetched_venues or venue_code in failed_venues:
            return

    data = fetch_data(venue_code)

    if data is None:
        with lock:
            failed_venues.add(venue_code)
            error_count += 1
            print(f"❌ Marked failed: {venue_code}")

            if error_count >= MAX_ERRORS:
                print("🛑 Too many errors — exiting safely")
                dump_progress()
                sys.exit(1)
        return

    with lock:
        all_data[venue_code] = data
        fetched_venues.add(venue_code)
        print(f"✅ {venue_code} fetched ({len(fetched_venues)})")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    with open("venues.json", "r") as f:
        venues = json.load(f)

    print(f"🚀 Selenium-Wire start | workers={NUM_WORKERS}")
    print(f"📌 Resume | fetched={len(fetched_venues)} failed={len(failed_venues)}")

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as exe:
        futures = [exe.submit(fetch_venue_safe, v) for v in venues.keys()]
        for _ in as_completed(futures):
            pass

    dump_progress()
    print("✅ Done — clean exit")
