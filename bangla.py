import json
import os
import sys
import time
import threading
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import pandas as pd

# ---------------- SELENIUM WIRE ----------------
from seleniumwire import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- CONFIG ----------------
NUM_WORKERS = 4
MAX_ERRORS = 5
dump_counter = 0

IST = timezone(timedelta(hours=5, minutes=30))
DATE_CODE = (datetime.now(IST) + timedelta(days=1)).strftime("%Y%m%d")

os.makedirs(DATE_CODE, exist_ok=True)

lock = threading.Lock()
error_count = 0

thread_local = threading.local()

# ---------------- USER AGENT ----------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0",
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
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={ua}")

    seleniumwire_options = {
        "disable_encoding": True,
        "custom_headers": {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
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

# ---------------- SELENIUM JSON FETCH ----------------
def selenium_fetch_json(url, timeout=25):
    driver = get_driver()
    driver.scopes = [".*bookmyshow.com/api/.*"]
    driver.requests.clear()

    driver.get(url)
    end = time.time() + timeout

    while time.time() < end:
        for req in driver.requests:
            if req.response and url in req.url:
                body = req.response.body
                return json.loads(body.decode("utf-8", errors="ignore"))
        time.sleep(0.2)

    raise RuntimeError("API response not captured")

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
        parent_event_code = event.get("EventGroup") or event.get("EventCode")

        for child in event.get("ChildEvents", []):
            dim = child.get("EventDimension", "").strip()
            lang = child.get("EventLanguage", "").strip()
            child_code = child.get("EventCode")

            parts = [x for x in [dim, lang] if x]
            movie_title = (
                f"{parent_title} [{' | '.join(parts)}]"
                if parts
                else parent_title
            )

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

                shows_by_movie[movie_title].append({
                    "venue_code": venue_code,
                    "venue": venue_name,
                    "address": venue_add,
                    "chain": venue_info.get("VenueCompName", "Unknown"),
                    "movie": movie_title,
                    "parent_event_code": parent_event_code,
                    "child_event_code": child_code,
                    "dimension": dim,
                    "language": lang,
                    "time": show.get("ShowTime"),
                    "session_id": show.get("SessionId"),
                    "audi": show.get("Attributes", ""),
                    "total": total,
                    "sold": sold,
                    "available": available,
                    "occupancy": round((sold / total * 100), 2) if total else 0,
                    "gross": gross,
                })

    return shows_by_movie

# ---------------- SAFE WRAPPER ----------------
def fetch_venue_safe(venue_code):
    global error_count, dump_counter

    with lock:
        if venue_code in fetched_venues:
            return

    data = fetch_data(venue_code)

    if data is None:
        with lock:
            error_count += 1
            if error_count >= MAX_ERRORS:
                print("🛑 Too many errors — restarting")
                os.execv(sys.executable, ["python"] + sys.argv)
        return

    with lock:
        all_data[venue_code] = data
        fetched_venues.add(venue_code)
        dump_counter += 1
        print(f"✅ {venue_code} fetched ({len(fetched_venues)})")

        if dump_counter >= 50:
            dump_progress(all_data, fetched_venues)
            dump_counter = 0

# ---------------- DUMP (UNCHANGED) ----------------
def dump_progress(all_data, fetched_venues):
    with open(f"{DATE_CODE}/venues_data.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f)

    with open(f"{DATE_CODE}/fetchedvenues.json", "w", encoding="utf-8") as f:
        json.dump(list(fetched_venues), f)

    print(f"💾 Dumped progress ({len(fetched_venues)})")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    with open("venues.json", "r", encoding="utf-8") as f:
        venues = json.load(f)

    fetched_venues = set()
    all_data = {}

    print(f"🚀 Selenium-Wire start | workers={NUM_WORKERS}")

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as exe:
        futures = [exe.submit(fetch_venue_safe, v) for v in venues.keys()]
        for _ in as_completed(futures):
            pass

    dump_progress(all_data, fetched_venues)
    print("✅ Done")
