import json
import requests
import os
import pytz
from datetime import datetime, timedelta
from collections import defaultdict

BASE_URL = "https://bfilmy.pages.dev/Daily%20Advance/data"
OUTPUT_DIR = "Monthly Advance"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------
# Helper Functions
# -------------------------
def get_month(year_offset=0, month_offset=0):
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
    url = f"{BASE_URL}/{date}.json"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"⚠️ Error fetching {date}: {e}")
    return None


# -------------------------
# Aggregate a month
# -------------------------
def aggregate_month(year, month):
    month_file = os.path.join(OUTPUT_DIR, f"{month_str(year, month)}.json")
    print(f"📅 Aggregating full month {month_str(year, month)} → {month_file}")

    monthly_data = {}
    start_date = datetime(year, month, 1)
    next_month = (month % 12) + 1
    next_year = year + (month // 12)
    end_date = (datetime(next_year, next_month, 1) - timedelta(days=1)).date()
    today = datetime.now().date()
    if year == today.year and month == today.month:
        end_date = today

    current = start_date
    while current.date() <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        data = fetch_json(date_str)
        if not data:
            current += timedelta(days=1)
            continue

        for movie, mdata in data.items():
            if not isinstance(mdata, dict):
                continue

            if movie not in monthly_data:
                monthly_data[movie] = {
                    "summary": defaultdict(float),
                    "cities": defaultdict(lambda: defaultdict(float)),
                    "states": defaultdict(lambda: defaultdict(float)),
                    "chains": defaultdict(lambda: defaultdict(float)),
                    "daily": {}
                }

            m = monthly_data[movie]

            # --- Daily ---
            m["daily"][date_str] = {
                "shows": mdata.get("shows", 0),
                "gross": mdata.get("gross", 0),
                "sold": mdata.get("sold", 0),
                "totalSeats": mdata.get("totalSeats", 0),
                "venues": mdata.get("venues", 0),
                "cities": mdata.get("cities", 0),
                "occupancy": mdata.get("occupancy", 0),
            }

            # --- Summary totals ---
            for key in ["shows", "gross", "sold", "totalSeats"]:
                m["summary"][key] += mdata.get(key, 0)

            # --- City-level ---
            for d in mdata.get("details", []):
                city = d.get("city", "Unknown")
                state = d.get("state", "Unknown")
                for key in ["shows", "gross", "sold", "totalSeats"]:
                    m["cities"][city][key] += d.get(key, 0)
                    m["states"][state][key] += d.get(key, 0)

            # --- Chain-level ---
            for d in mdata.get("Chain_details", []):
                chain = d.get("chain", "Unknown")
                for key in ["shows", "gross", "sold", "totalSeats"]:
                    m["chains"][chain][key] += d.get(key, 0)

        current += timedelta(days=1)

    # -------------------------
    # Final calculations
    # -------------------------
    for movie, m in monthly_data.items():
        # --- Summary occupancy ---
        s = m["summary"]
        s["occupancy"] = round(100 * s["sold"] / s["totalSeats"], 2) if s["totalSeats"] else 0
        m["summary"] = dict(s)

        # --- Cities: occupancy + top 10 by gross ---
        m["cities"] = dict(sorted(
            (
                (city, {**vals, "occupancy": round(100 * vals["sold"] / vals["totalSeats"], 2)
                        if vals["totalSeats"] else 0})
                for city, vals in m["cities"].items()
            ),
            key=lambda x: x[1]["gross"], reverse=True
        )[:10])

        # --- States: occupancy + top 10 by gross ---
        m["states"] = dict(sorted(
            (
                (state, {**vals, "occupancy": round(100 * vals["sold"] / vals["totalSeats"], 2)
                         if vals["totalSeats"] else 0})
                for state, vals in m["states"].items()
            ),
            key=lambda x: x[1]["gross"], reverse=True
        )[:10])

        # --- Chains: occupancy + top 10 by gross ---
        m["chains"] = dict(sorted(
            (
                (chain, {**vals, "occupancy": round(100 * vals["sold"] / vals["totalSeats"], 2)
                         if vals["totalSeats"] else 0})
                for chain, vals in m["chains"].items()
            ),
            key=lambda x: x[1]["gross"], reverse=True
        )[:10])

    # -------------------------
    # Add timestamp & save
    # -------------------------
    ist = pytz.timezone("Asia/Kolkata")
    monthly_data["lastUpdated"] = datetime.now(ist).strftime("%I:%M %p, %d %B %Y")

    with open(month_file, "w", encoding="utf-8") as f:
        json.dump(monthly_data, f, indent=2, ensure_ascii=False)

    print(f"🎉 Saved full month file {month_file}")


# -------------------------
# Main
# -------------------------
def main():
    prev_year, prev_month = get_month(month_offset=-1)
    curr_year, curr_month = get_month()

    prev_file = os.path.join(OUTPUT_DIR, f"{month_str(prev_year, prev_month)}.json")
    if not os.path.exists(prev_file):
        aggregate_month(prev_year, prev_month)
    else:
        print(f"⏭ Skipping previous month → {month_str(prev_year, prev_month)}")

    aggregate_month(curr_year, curr_month)


if __name__ == "__main__":
    main()
