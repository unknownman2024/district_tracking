import json
import requests
import os
from datetime import datetime, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo  # Python 3.9+

BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_DIR = "Monthly Database"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------
# Helper Functions
# -------------------------
def get_month(year_offset=0, month_offset=0):
    """Return (year, month) tuple adjusted by offsets"""
    today = datetime.now(ZoneInfo("Asia/Kolkata"))
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
    """Process shows for a single movie, return summary, cities, states, chains"""
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

        # Chain aggregation
        chain = venue.split()[0].replace(",", "")
        chain_data[chain]["shows"] += 1
        chain_data[chain]["sold"] += sold
        chain_data[chain]["totalSeats"] += totalSeats
        chain_data[chain]["gross"] += gross

    # Calculate occupancy
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

    start_date = datetime(year, month, 1, tzinfo=ZoneInfo("Asia/Kolkata"))
    # Last day of month
    next_month = (month % 12) + 1
    next_year = year + (month // 12)
    end_date = (datetime(next_year, next_month, 1, tzinfo=ZoneInfo("Asia/Kolkata")) - timedelta(days=1)).date()
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if year == today.year and month == today.month:
        end_date = today

    # Store raw daily shows to avoid refetching
    daily_raw_data = {}  # date_str -> full data dict

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

        daily_raw_data[date_str] = data  # store raw data

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

            # Add/Update daily summary
            m["daily"][date_str] = summary

        current += timedelta(days=1)

    # -------------------------
    # Rebuild totals from all daily summaries
    # -------------------------
    for movie, m in monthly_data.items():
        total_summary = defaultdict(float)
        total_cities = defaultdict(lambda: defaultdict(float))
        total_states = defaultdict(lambda: defaultdict(float))
        total_chains = defaultdict(lambda: defaultdict(float))

        for day_str, day_summary in m["daily"].items():
            # Add daily summary totals
            for k in ["shows", "sold", "totalSeats", "gross"]:
                total_summary[k] += day_summary[k]

            # Rebuild city/state/chain totals from raw daily shows
            day_data = daily_raw_data.get(day_str) or fetch_json(day_str)
            if not day_data:
                continue
            for movie_day, shows_day in day_data.items():
                if movie_day in ["date", "lastUpdated"]:
                    continue
                s, cities_day, states_day, chains_day = process_movie_data(shows_day)

                for k, v in cities_day.items():
                    for kk in ["shows", "sold", "totalSeats", "gross"]:
                        total_cities[k][kk] += v[kk]
                    total_cities[k]["state"] = v.get("state", "")
                for k, v in states_day.items():
                    for kk in ["shows", "sold", "totalSeats", "gross"]:
                        total_states[k][kk] += v[kk]
                for k, v in chains_day.items():
                    for kk in ["shows", "sold", "totalSeats", "gross"]:
                        total_chains[k][kk] += v[kk]

        # Recalculate occupancy
        total_summary["occupancy"] = round(100 * total_summary["sold"] / total_summary["totalSeats"], 2) if total_summary["totalSeats"] else 0
        for dataset in [total_cities, total_states, total_chains]:
            for k, v in dataset.items():
                v["occupancy"] = round(100 * v["sold"] / v["totalSeats"], 2) if v["totalSeats"] else 0

        # Keep top10 by gross
        m["summary"] = total_summary
        m["cities"] = dict(sorted(total_cities.items(), key=lambda x: x[1]["gross"], reverse=True)[:10])
        m["states"] = dict(sorted(total_states.items(), key=lambda x: x[1]["gross"], reverse=True)[:10])
        m["chains"] = dict(sorted(total_chains.items(), key=lambda x: x[1]["gross"], reverse=True)[:10])

    # Save file
    with open(month_file, "w", encoding="utf-8") as f:
        json.dump(monthly_data, f, indent=2, ensure_ascii=False)
    print(f"🎉 Saved {month_file}")

# -------------------------
# Auto-run logic
# -------------------------
def main():
    today = datetime.now(ZoneInfo("Asia/Kolkata"))
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
