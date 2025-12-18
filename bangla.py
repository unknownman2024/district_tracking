import json
import os
import sys
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import cloudscraper

# ---------------- SELENIUM ----------------
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- CONFIG ----------------
NUM_WORKERS = 3
MAX_ERRORS = 20
MAX_RETRY_CLOUD = 2

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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

def random_ip():
    return ".".join(str(random.randint(10, 240)) for _ in range(4))

def get_headers():
    ip = random_ip()
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://in.bookmyshow.com",
        "Referer": "https://in.bookmyshow.com/",
        "X-Forwarded-For": ip,
        "X-Real-IP": ip,
        "Client-IP": ip,
        "Connection": "keep-alive",
    }

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

# ---------------- CLOUDSCRAPER FETCH ----------------
def fetch_cloudscraper(url):
    for attempt in range(MAX_RETRY_CLOUD):
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            res = scraper.get(url, headers=get_headers(), timeout=15)
            text = res.text.strip()

            if not text.startswith("{"):
                raise ValueError("HTML / Cloudflare")

            return res.json()

        except Exception as e:
            if attempt + 1 < MAX_RETRY_CLOUD:
                time.sleep(2 + random.random())
            else:
                raise e

# ---------------- SELENIUM FETCH ----------------
def get_driver():
    if hasattr(thread_local, "driver"):
        return thread_local.driver

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )

    thread_local.driver = driver
    return driver

def fetch_selenium(url, timeout=25):
    driver = get_driver()
    driver.set_page_load_timeout(timeout)
    driver.get(url)

    body = driver.page_source.strip()
    if not body.startswith("{"):
        raise ValueError("Selenium HTML response")

    return json.loads(body)

# ---------------- HYBRID FETCH ----------------
def hybrid_fetch(url):
    try:
        return fetch_cloudscraper(url)
    except Exception as e:
        print("⚠️ Cloudscraper failed, switching to Selenium")
        return fetch_selenium(url)

# ---------------- FETCH DATA ----------------
def fetch_data(venue_code):
    url = (
        "https://in.bookmyshow.com/api/v2/mobile/showtimes/byvenue"
        f"?venueCode={venue_code}&dateCode={DATE_CODE}"
    )

    try:
        data = hybrid_fetch(url)
    except Exception as e:
        print(f"❌ Hybrid failed {venue_code}: {e}")
        return None

    show_details = data.get("ShowDetails")
    if not isinstance(show_details, list) or not show_details:
        return {}

    sd0 = show_details[0]
    if not isinstance(sd0, dict):
        return {}

    venue_info = sd0.get("Venues")
    if not isinstance(venue_info, dict):
        return {}

    venue_name = venue_info.get("VenueName", "")
    venue_add = venue_info.get("VenueAdd", "")

    shows_by_movie = defaultdict(list)

    for event in sd0.get("Event", []):
        parent_title = event.get("EventTitle", "Unknown")

        for child in event.get("ChildEvents", []):
            dim = child.get("EventDimension", "").strip()
            lang = child.get("EventLanguage", "").strip()
            parts = [x for x in (dim, lang) if x]
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
            print(f"❌ Failed: {venue_code}")

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

    print(f"🚀 Hybrid start | workers={NUM_WORKERS}")
    print(f"📌 Resume | fetched={len(fetched_venues)} failed={len(failed_venues)}")

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as exe:
        futures = [exe.submit(fetch_venue_safe, v) for v in venues.keys()]
        for _ in as_completed(futures):
            pass

    dump_progress()
    print("✅ Done — hybrid complete")
