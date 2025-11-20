#!/usr/bin/env python3
import json
import requests
import os
import pytz
from datetime import datetime, timedelta
from collections import defaultdict

BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_DIR = "Monthly Chains Data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHAIN_LIST = [
    "PVR", "INOX", "Cinepolis", "Movietime Cinemas", "Wave Cinemas",
    "Miraj Cinemas", "Rajhans Cinemas", "Asian Mukta",
    "MovieMax", "Mythri Cinemas", "Maxus Cinemas"
]


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
            return r.json()
    except:
        pass
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


def update_month(year, month):
    file_path = os.path.join(OUTPUT_DIR, f"{month_str(year, month)}.json")
    today = datetime.now().date()

    # Load old file if exists
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            month_result = json.load(f)
        print(f"\n♻ Updating current month file: {file_path}")
    else:
        month_result = defaultdict(dict)
        print(f"\n🆕 Creating new file: {file_path}")

    # Always update only today's data
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"   ▶ Fetching {date_str}")

    daily_data = fetch_json(date_str)

    if daily_data:
        for movie, shows in daily_data.items():
            if movie in ["date", "lastUpdated"] or not isinstance(shows, list):
                continue

            valid = [s for s in shows if isinstance(s, dict)]
            chain_stats = process_chain_data(valid)

            if chain_stats:
                month_result.setdefault(movie, {})[date_str] = {
                    chain: [
                        stats["shows"],
                        stats["sold"],
                        stats["seats"],
                        stats["gross"],
                        stats["occ"]
                    ]
                    for chain, stats in chain_stats.items()
                }

    # Update IST timestamp
    ist = pytz.timezone("Asia/Kolkata")
    month_result["lastUpdated"] = datetime.now(ist).strftime("%I:%M %p, %d %B %Y")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(month_result, f, indent=2, ensure_ascii=False)

    print(f"✔ Updated today only → {file_path}")


def generate_past_month(year, month):
    file_path = os.path.join(OUTPUT_DIR, f"{month_str(year, month)}.json")

    # Skip if already created once
    if os.path.exists(file_path):
        print(f"⏭ Past month exists → Skipping {file_path}")
        return

    print(f"\n📅 Generating past full month: {month_str(year, month)} → {file_path}")

    month_result = defaultdict(dict)
    start_date = datetime(year, month, 1)
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    end_date = (datetime(next_year, next_month, 1) - timedelta(days=1)).date()

    current = start_date
    while current.date() <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        print(f"   ▶ {date_str}")

        daily_data = fetch_json(date_str)
        if daily_data:
            for movie, shows in daily_data.items():
                if movie in ["date", "lastUpdated"] or not isinstance(shows, list):
                    continue

                valid = [s for s in shows if isinstance(s, dict)]
                chain_stats = process_chain_data(valid)

                if chain_stats:
                    month_result[movie][date_str] = {
                        chain: [
                            stats["shows"],
                            stats["sold"],
                            stats["seats"],
                            stats["gross"],
                            stats["occ"]
                        ]
                        for chain, stats in chain_stats.items()
                    }

        current += timedelta(days=1)

    # Add timestamp once
    ist = pytz.timezone("Asia/Kolkata")
    month_result["lastUpdated"] = datetime.now(ist).strftime("%I:%M %p, %d %B %Y")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(month_result, f, indent=2, ensure_ascii=False)

    print(f"🎉 Saved past month → {file_path}")


def main():
    today = datetime.now()
    start_month = 9
    start_year = today.year

    if today.month < start_month:
        start_year -= 1

    year, month = start_year, start_month

    while (year < today.year) or (month <= today.month):
        if year == today.year and month == today.month:
            update_month(year, month)
        else:
            generate_past_month(year, month)

        month += 1
        if month > 12:
            month = 1
            year += 1


if __name__ == "__main__":
    main()
