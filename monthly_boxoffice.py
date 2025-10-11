import json
import requests
import os
from datetime import datetime, timedelta
from collections import defaultdict

BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_DIR = "Monthly Database"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------
# Helper Functions
# -------------------------
def get_month(year_offset=0, month_offset=0):
    """Return (year, month) tuple adjusted by offsets"""
    today = datetime.now()
    month = today.month + month_offset
    year = today.year + year_offset
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month

def month_str(year, month):
    return f"{year}-{month:02d}"

def fetch_json(date):
    url = f"{BASE_URL}/{date}_Detailed.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"⚠️ Error fetching {date}: {e}")
    return None

def process_movie_data(movie_data):
    summary = defaultdict(float)
    city_data = defaultdict(lambda: defaultdict(float))
    state_data = defaultdict(lambda: defaultdict(float))
    chain_data = defaultdict(lambda: defaultdict(float))

    for show in movie_data:
        city = show.get("city", "Unknown")
        state = show.get("state", "Unknown")
        venue = show.get("venue", "")
        totalSeats = show.get("totalSeats", 0) or 0
        sold = show.get("sold", 0) or 0
        gross = show.get("gross", 0) or 0

        summary["shows"] += 1
        summary["sold"] += sold
        summary["totalSeats"] += totalSeats
        summary["gross"] += gross

        # City aggregation
        city_data[city]["shows"] += 1
        city_data[city]["sold"] += sold
        city_data[city]["totalSeats"] += totalSeats
        city_data[city]["gross"] += gross
        city_data[city]["state"] = state

        # State aggregation
        state_data[state]["shows"] += 1
        state_data[state]["sold"] += sold
        state_data[state]["totalSeats"] += totalSeats
        state_data[state]["gross"] += gross

        # Detect chain name (first word in venue)
        chain = venue.split()[0].replace(",", "")
        chain_data[chain]["shows"] += 1
        chain_data[chain]["sold"] += sold
        chain_data[chain]["totalSeats"] += totalSeats
        chain_data[chain]["gross"] += gross

    # calculate occupancy
    for dataset in (city_data, state_data, chain_data):
        for k, v in dataset.items():
            v["occupancy"] = round(100 * v["sold"] / v["totalSeats"], 2) if v["totalSeats"] else 0
    summary["occupancy"] = round(100 * summary["sold"] / summary["totalSeats"], 2) if summary["totalSeats"] else 0

    return summary, city_data, state_data, chain_data

# -------------------------
# Main Aggregation
# -------------------------
def aggregate_month(year, month, force_today=False):
    month_file = os.path.join(OUTPUT_DIR, f"{month_str(year, month)}.json")
    print(f"📅 Aggregating {month_str(year, month)} → {month_file}")

    # Load existing monthly data if exists
    monthly_data = {}
    if os.path.exists(month_file):
        try:
            with open(month_file, "r", encoding="utf-8") as f:
                monthly_data = json.load(f)
            print("🔄 Loaded existing file, will append new days...")
        except:
            monthly_data = {}

    start_date = datetime(year, month, 1)
    # Last day of month
    next_month = (month % 12) + 1
    next_year = year + (month // 12)
    end_date = (datetime(next_year, next_month, 1) - timedelta(days=1)).date()
    today = datetime.now().date()
    if year == today.year and month == today.month:
        end_date = today

    # -------------------------
    # Loop through all days
    # -------------------------
    current = start_date
    while current.date() <= end_date:
        date_str = current.strftime("%Y-%m-%d")

        # Skip previous days if they exist, but always process today if force_today=True
        if not (force_today and date_str == today.strftime("%Y-%m-%d")):
            if any(date_str in movie.get("daily", {}) for movie in monthly_data.values()):
                current += timedelta(days=1)
                continue

        data = fetch_json(date_str)
        if not data:
            current += timedelta(days=1)
            continue

        for movie, shows in data.items():
            if movie in ["date", "lastUpdated"]:
                continue
            summary, cities, states, chains = process_movie_data(shows)

            if movie not in monthly_data:
                monthly_data[movie] = {
                    "summary": defaultdict(float),
                    "cities": {},
                    "states": {},
                    "chains": {},
                    "daily": {}
                }

            m = monthly_data[movie]
            # Merge totals
            for k in ["shows", "sold", "totalSeats", "gross"]:
                m["summary"][k] = m["summary"].get(k, 0) + summary[k]

            # Merge city/state/chain
            for dataset, key in [(cities, "cities"), (states, "states"), (chains, "chains")]:
                for k, v in dataset.items():
                    if k not in m[key]:
                        m[key][k] = v
                    else:
                        for kk in ["shows", "sold", "totalSeats", "gross", "occupancy"]:
                            m[key][k][kk] = m[key][k].get(kk, 0) + v[kk]

            # Add daily summary
            m["daily"][date_str] = summary

        current += timedelta(days=1)

    # Finalize top10 lists
    for movie, m in monthly_data.items():
        m["summary"]["occupancy"] = round(
            100 * m["summary"]["sold"] / m["summary"]["totalSeats"], 2
        ) if m["summary"]["totalSeats"] else 0
        for key in ["cities", "states", "chains"]:
            top10 = dict(sorted(m[key].items(), key=lambda x: x[1]["gross"], reverse=True)[:10])
            m[key] = top10

    # Save file
    with open(month_file, "w", encoding="utf-8") as f:
        json.dump(monthly_data, f, indent=2, ensure_ascii=False)
    print(f"🎉 Saved {month_file}")


# -------------------------
# Auto-run logic
# -------------------------
def main():
    today = datetime.now()
    prev_year, prev_month = get_month(month_offset=-1)
    curr_year, curr_month = get_month()

    # ----------------------
    # Previous month
    # ----------------------
    prev_file = os.path.join(OUTPUT_DIR, f"{month_str(prev_year, prev_month)}.json")
    if not os.path.exists(prev_file):
        aggregate_month(prev_year, prev_month)
    else:
        print(f"⏭ Previous month file exists → skipping {month_str(prev_year, prev_month)}")

    # ----------------------
    # Current month
    # ----------------------
    curr_file = os.path.join(OUTPUT_DIR, f"{month_str(curr_year, curr_month)}.json")
    if os.path.exists(curr_file):
        print(f"🔄 Current month file exists → updating today only")
        aggregate_month(curr_year, curr_month, force_today=True)
    else:
        print(f"📅 Current month file does not exist → aggregating full month so far")
        aggregate_month(curr_year, curr_month)


if __name__ == "__main__":
    main()
