#!/usr/bin/env python3
import json
import requests
import os
import pytz
from datetime import datetime, timedelta
from collections import defaultdict

BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_DIR = "Chain Daily Breakdown"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHAIN_LIST = [
    "PVR", "INOX", "Cinepolis", "Movietime Cinemas", "Wave Cinemas",
    "Miraj Cinemas", "Rajhans Cinemas", "Asian Mukta",
    "MovieMax", "Mythri Cinemas", "Maxus Cinemas"
]

def log(msg):
    print(f"➡️ {msg}")

def detect_chain(venue):
    venue_lower = venue.lower()
    for chain in CHAIN_LIST:
        if chain.lower() in venue_lower:
            return chain
    return None

def month_str(year, month):
    return f"{year}-{month:02d}"

def fetch_json(date):
    url = f"{BASE_URL}/{date}_Detailed.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            log(f"   📥 Fetched: {url}")
            return r.json()
        else:
            log(f"   ⚠️ No data: {url} (status {r.status_code})")
    except Exception as e:
        log(f"   ❌ Fetch error: {e}")
    return None

def process_chain_data(shows):
    chain_data = defaultdict(lambda: defaultdict(float))

    for show in shows:
        if not isinstance(show, dict):
            continue

        venue = show.get("venue", "")
        chain = detect_chain(venue)
        if not chain:
            continue

        sold = show.get("sold", 0) or 0
        seats = show.get("totalSeats", 0) or 0
        gross = show.get("gross", 0) or 0

        chain_data[chain]["shows"] += 1
        chain_data[chain]["sold"] += sold
        chain_data[chain]["seats"] += seats
        chain_data[chain]["gross"] += gross

    for c, v in chain_data.items():
        v["occ"] = round((v["sold"] / v["seats"]) * 100, 2) if v["seats"] else 0

    return chain_data

def update_current_month(year, month):
    file_path = os.path.join(OUTPUT_DIR, f"{month_str(year, month)}.json")

    # Load existing data if exists
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            month_result = json.load(f)
        log(f"📂 Updating existing current month file: {file_path}")
    else:
        month_result = {}
        log(f"🆕 Creating new file for current month: {file_path}")

    today = datetime.now().date()
    start = datetime(year, month, 1)

    current = start
    while current.date() <= today:
        date_str = current.strftime("%Y-%m-%d")

        # Rule: Skip already saved previous days, rewrite only today
        if date_str in month_result and current.date() < today:
            log(f"   ⏭ Skipping (already exists): {date_str}")
            current += timedelta(days=1)
            continue

        log(f"   🔎 Processing: {date_str}")

        daily = fetch_json(date_str)
        if not daily:
            current += timedelta(days=1)
            continue

        for movie, shows in daily.items():
            if movie in ["date", "lastUpdated"] or not isinstance(shows, list):
                continue

            valid = [s for s in shows if isinstance(s, dict)]
            chains = process_chain_data(valid)

            if chains:
                if movie not in month_result:
                    month_result[movie] = {}

                month_result[movie][date_str] = {
                    chain: [
                        stats["shows"],
                        stats["sold"],
                        stats["seats"],
                        stats["gross"],
                        stats["occ"]
                    ]
                    for chain, stats in chains.items()
                }

                log(f"      ✔ Saved {movie} → {date_str}")

        current += timedelta(days=1)

    ist = pytz.timezone("Asia/Kolkata")
    month_result["lastUpdated"] = datetime.now(ist).strftime("%I:%M %p, %d %B %Y")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(month_result, f, indent=2, ensure_ascii=False)

    log(f"🎉 Current month updated → {file_path}")

def generate_past_month(year, month):
    file_path = os.path.join(OUTPUT_DIR, f"{month_str(year, month)}.json")
    
    if os.path.exists(file_path):
        log(f"⏭ Already exists (past month): {file_path}")
        return

    log(f"\n📅 Generating full past month: {month_str(year, month)} → {file_path}")

    month_result = {}
    start = datetime(year, month, 1)
    end = (start.replace(day=28) + timedelta(days=5)).replace(day=1) - timedelta(days=1)

    current = start
    while current.date() <= end.date():
        date_str = current.strftime("%Y-%m-%d")
        log(f"   ▶ Fetching: {date_str}")

        daily = fetch_json(date_str)
        if daily:
            for movie, shows in daily.items():
                if movie in ["lastUpdated", "date"] or not isinstance(shows, list):
                    continue

                valid = [s for s in shows if isinstance(s, dict)]
                chains = process_chain_data(valid)

                if chains:
                    month_result.setdefault(movie, {})[date_str] = {
                        chain: [
                            stats["shows"],
                            stats["sold"],
                            stats["seats"],
                            stats["gross"],
                            stats["occ"]
                        ]
                        for chain, stats in chains.items()
                    }
        current += timedelta(days=1)

    ist = pytz.timezone("Asia/Kolkata")
    month_result["lastUpdated"] = datetime.now(ist).strftime("%I:%M %p, %d %B %Y")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(month_result, f, indent=2, ensure_ascii=False)

    log(f"🎉 Saved full past month → {file_path}")

def main():
    today = datetime.now()
    start_month = 9
    start_year = today.year

    if today.month < start_month:
        start_year -= 1

    year, month = start_year, start_month

    while (year < today.year) or (month <= today.month):
        if year == today.year and month == today.month:
            update_current_month(year, month)
        else:
            generate_past_month(year, month)

        month += 1
        if month > 12:
            month = 1
            year += 1

if __name__ == "__main__":
    main()
