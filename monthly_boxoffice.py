import json
import requests
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict

BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_DIR = "Monthly Database"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------
# Helper Functions
# -------------------------
IST = timezone(timedelta(hours=5, minutes=30))

def log(msg):
    print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] {msg}")

def get_month(year_offset=0, month_offset=0):
    today = datetime.now(IST)
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
            log(f"✅ Fetched data for {date}")
            return r.json()
        else:
            log(f"⚠️ {date} not found ({r.status_code})")
    except Exception as e:
        log(f"❌ Error fetching {date}: {e}")
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

        city_data[city]["shows"] += 1
        city_data[city]["sold"] += sold
        city_data[city]["totalSeats"] += totalSeats
        city_data[city]["gross"] += gross
        city_data[city]["state"] = state

        state_data[state]["shows"] += 1
        state_data[state]["sold"] += sold
        state_data[state]["totalSeats"] += totalSeats
        state_data[state]["gross"] += gross

        chain = venue.split()[0].replace(",", "")
        chain_data[chain]["shows"] += 1
        chain_data[chain]["sold"] += sold
        chain_data[chain]["totalSeats"] += totalSeats
        chain_data[chain]["gross"] += gross

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
    log(f"📅 Aggregating {month_str(year, month)} → {month_file}")

    monthly_data = {}
    if os.path.exists(month_file):
        try:
            with open(month_file, "r", encoding="utf-8") as f:
                monthly_data = json.load(f)
            log("🔄 Loaded existing monthly data")
        except Exception as e:
            log(f"⚠️ Could not load existing file ({e})")

    start_date = datetime(year, month, 1)
    next_month = (month % 12) + 1
    next_year = year + (month // 12)
    end_date = (datetime(next_year, next_month, 1) - timedelta(days=1)).date()

    today = datetime.now(IST).date()
    if year == today.year and month == today.month:
        end_date = today - timedelta(days=1)
        if force_today:
            log("🟢 Forcing today's update as well")
            end_date = today

    current = start_date
    while current.date() <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        already = any(date_str in movie.get("daily", {}) for movie in monthly_data.values())
        if already and not (force_today and date_str == today.strftime("%Y-%m-%d")):
            log(f"⏭ Skipping {date_str} (already in monthly data)")
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
            for k in ["shows", "sold", "totalSeats", "gross"]:
                m["summary"][k] = m["summary"].get(k, 0) + summary[k]

            for dataset, key in [(cities, "cities"), (states, "states"), (chains, "chains")]:
                for k, v in dataset.items():
                    if k not in m[key]:
                        m[key][k] = v
                    else:
                        for kk in ["shows", "sold", "totalSeats", "gross"]:
                            m[key][k][kk] = m[key][k].get(kk, 0) + v[kk]
                        m[key][k]["occupancy"] = round(100 * m[key][k]["sold"] / m[key][k]["totalSeats"], 2) if m[key][k]["totalSeats"] else 0

            m["daily"][date_str] = summary

        log(f"✅ Merged {date_str}")
        current += timedelta(days=1)

    for movie, m in monthly_data.items():
        m["summary"]["occupancy"] = round(100 * m["summary"]["sold"] / m["summary"]["totalSeats"], 2) if m["summary"]["totalSeats"] else 0
        for key in ["cities", "states", "chains"]:
            top10 = dict(sorted(m[key].items(), key=lambda x: x[1]["gross"], reverse=True)[:10])
            m[key] = top10

    # 🕓 Add IST time update without changing structure
    monthly_data["lastUpdated"] = datetime.now(IST).strftime("%I:%M %p, %d %B %Y")

    with open(month_file, "w", encoding="utf-8") as f:
        json.dump(monthly_data, f, indent=2, ensure_ascii=False)
    log(f"🎉 Saved {month_file} (lastUpdated added)")


# -------------------------
# Auto-run Logic
# -------------------------
def main():
    today = datetime.now(IST)
    prev_year, prev_month = get_month(month_offset=-1)
    curr_year, curr_month = get_month()

    prev_file = os.path.join(OUTPUT_DIR, f"{month_str(prev_year, prev_month)}.json")
    if not os.path.exists(prev_file):
        log(f"🕓 Processing previous month ({month_str(prev_year, prev_month)})")
        aggregate_month(prev_year, prev_month)
    else:
        log(f"⏭ Previous month already exists → skipping {month_str(prev_year, prev_month)}")

    aggregate_month(curr_year, curr_month, force_today=True)


if __name__ == "__main__":
    main()
