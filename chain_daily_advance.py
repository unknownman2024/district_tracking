#!/usr/bin/env python3
import json, os, requests, pytz
from datetime import datetime, timedelta
from collections import defaultdict

BASE_URL = "https://district24.pages.dev/Daily%20Advance"
OUTPUT_DIR = "Chain Daily Advance"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_CHAINS = ["PVR", "INOX", "CINEPOLIS"]

BLOCK_RATES = {
    "PVR": 0.005,
    "CINEPOLIS": 0.0325,
    "INOX": 0.0
}

def log(msg): print("➡", msg)

def detect_chain(venue):
    venue = venue.upper()
    for chain in TARGET_CHAINS:
        if chain in venue:
            return chain
    return None

def apply_discount(chain, sold, gross, seats):
    """Apply blocked seat correction"""
    rate = BLOCK_RATES.get(chain, 0)
    if sold > 0 and rate > 0:
        avg_price = gross / sold if sold > 0 else 0
        blocked = seats * rate
        adjusted_sold = max(0, sold - blocked)
        sold = round(adjusted_sold)
        gross = round(adjusted_sold * avg_price)
    return sold, gross

def fetch(date):
    url = f"{BASE_URL}/{date}_Detailed.json"
    try:
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            log(f"📥 Data received for {date}")
            return r.json()
    except:
        pass
    log(f"⚠ No data for {date}")
    return None

def process_day(shows):
    """Return only chain-level data after discount"""
    data = defaultdict(lambda: defaultdict(float))

    for s in shows:
        if not isinstance(s, dict): 
            continue

        venue = s.get("venue", "")
        chain = detect_chain(venue)
        if not chain:
            continue

        sold = s.get("sold", 0) or 0
        seats = s.get("totalSeats", 0) or 0
        gross = s.get("gross", 0) or 0

        sold, gross = apply_discount(chain, sold, gross, seats)

        data[chain]["shows"] += 1
        data[chain]["sold"] += sold
        data[chain]["seats"] += seats
        data[chain]["gross"] += gross

    for c, v in data.items():
        v["occ"] = round((v["sold"] / v["seats"]) * 100, 2) if v["seats"] else 0

    return data

def save(path, structure):
    ist = pytz.timezone("Asia/Kolkata")
    structure["lastUpdated"] = datetime.now(ist).strftime("%I:%M %p, %d %B %Y")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2, ensure_ascii=False)
    log(f"💾 Saved → {path}")

def process_month(year, month, is_current):
    filename = f"{year}-{month:02d}.json"
    path = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(path):
        with open(path, "r") as f:
            month_json = json.load(f)
        log(f"🔁 Updating existing {filename}")
    else:
        month_json = {}
        log(f"🆕 Creating month file {filename}")

    today = datetime.now().date()
    end_date = today + timedelta(days=3) if is_current else \
        (datetime(year, month, 28) + timedelta(days=5)).replace(day=1).date() - timedelta(days=1)

    current = datetime(year, month, 1)

    while current.date() <= end_date:
        d = current.strftime("%Y-%m-%d")

        # RULES:
        if d in month_json and not is_current:
            log(f"⏭ Past month: exists {d}")
            current += timedelta(days=1)
            continue

        if d in month_json and current.date() < today and is_current:
            log(f"⏭ Skip older existing {d}")
            current += timedelta(days=1)
            continue

        log(f"🔎 Fetching {d}")
        data = fetch(d)
        if data:
            for movie, shows in data.items():
                if not isinstance(shows, list): 
                    continue

                stats = process_day(shows)
                if stats:
                    month_json.setdefault(movie, {})[d] = {
                        c: [v["shows"], v["sold"], v["seats"], v["gross"], v["occ"]]
                        for c, v in stats.items()
                    }

                    log(f"✔ Updated {movie} → {d}")

        current += timedelta(days=1)

    save(path, month_json)

def main():
    today = datetime.now()
    start_month = 9
    start_year = 2025

    y, m = start_year, start_month

    while (y < today.year) or (m <= today.month):
        process_month(y, m, is_current=(y == today.year and m == today.month))
        m += 1
        if m > 12:
            m = 1
            y += 1

    # Also generate **future 3-day file**
    process_month(today.year, today.month, is_current=True)

if __name__ == "__main__":
    main()
