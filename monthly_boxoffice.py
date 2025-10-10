import json
import requests
from datetime import datetime, timedelta, date
from collections import defaultdict
import os

BASE_URL = "https://district24.pages.dev/Daily%20Boxoffice"
OUTPUT_DIR = "Monthly Database"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_json(date_str):
    url = f"{BASE_URL}/{date_str}.json"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def month_start(year, month):
    return date(year, month, 1)

def next_month(year, month):
    return (year + (month // 12), 1 if month == 12 else month + 1)

def aggregate_month(year, month):
    start_date = month_start(year, month)
    next_y, next_m = next_month(year, month)
    end_date = month_start(next_y, next_m)
    today = datetime.now().date()

    if end_date > today:
        end_date = today + timedelta(days=1)

    output_file = os.path.join(OUTPUT_DIR, f"{year}-{month:02d}.json")
    monthly_data = {"month": f"{year}-{month:02d}"}

    movie_data = defaultdict(lambda: {
        "shows": 0,
        "gross": 0.0,
        "sold": 0,
        "chains": defaultdict(lambda: {"gross": 0.0, "sold": 0}),
        "cities": defaultdict(lambda: {"gross": 0.0, "sold": 0}),
        "states": defaultdict(lambda: {"gross": 0.0, "sold": 0}),
        "daily": {}
    })

    current = start_date
    while current < end_date:
        date_str = current.isoformat()
        data = fetch_json(date_str)
        if not data:
            current += timedelta(days=1)
            continue

        for movie_key, info in data.items():
            if movie_key in ["date", "lastUpdated"]:
                continue

            m = movie_data[movie_key]
            m["shows"] += info.get("shows", 0)
            m["gross"] += info.get("gross", 0)
            m["sold"] += info.get("sold", 0)

            day_city = defaultdict(lambda: {"gross": 0.0, "sold": 0})
            day_state = defaultdict(lambda: {"gross": 0.0, "sold": 0})
            for d in info.get("details", []):
                city, state = d.get("city"), d.get("state")
                gross, sold = d.get("gross", 0), d.get("sold", 0)
                if city:
                    m["cities"][city]["gross"] += gross
                    m["cities"][city]["sold"] += sold
                    day_city[city]["gross"] += gross
                    day_city[city]["sold"] += sold
                if state:
                    m["states"][state]["gross"] += gross
                    m["states"][state]["sold"] += sold
                    day_state[state]["gross"] += gross
                    day_state[state]["sold"] += sold

            for c in info.get("Chain_details", []):
                chain = c.get("chain")
                if chain:
                    m["chains"][chain]["gross"] += c.get("gross", 0)
                    m["chains"][chain]["sold"] += c.get("sold", 0)

            occ = round(info["sold"] / info["totalSeats"] * 100, 2) if info.get("totalSeats") else 0

            def top_n(dct, n=3):
                return [
                    {"name": k, "gross": round(v["gross"], 2), "sold": v["sold"]}
                    for k, v in sorted(dct.items(), key=lambda x: x[1]["gross"], reverse=True)[:n]
                ]

            m["daily"][date_str] = {
                "gross": round(info.get("gross", 0), 2),
                "sold": info.get("sold", 0),
                "occupancy": occ,
                "topCities": top_n(day_city, 3),
                "topStates": top_n(day_state, 3)
            }

        current += timedelta(days=1)

    def top_list(data_dict, n=10):
        items = sorted(data_dict.items(), key=lambda x: x[1]["gross"], reverse=True)[:n]
        return [{"name": k, "gross": round(v["gross"], 2), "sold": v["sold"]} for k, v in items]

    final_data = {"month": f"{year}-{month:02d}"}
    for movie_key, info in movie_data.items():
        occ_month = round(info["sold"] / (info["shows"] * 100 if info["shows"] else 1) * 100, 2)
        final_data[movie_key] = {
            "shows": info["shows"],
            "gross": round(info["gross"], 2),
            "sold": info["sold"],
            "occupancy": occ_month,
            "topCities": top_list(info["cities"]),
            "topStates": top_list(info["states"]),
            "topChains": top_list(info["chains"]),
            "daywise": info["daily"]
        }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {output_file} ({len(final_data)-1} movies)")

def auto_update():
    now = datetime.now()
    year, month = now.year, now.month
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    aggregate_month(prev_year, prev_month)
    aggregate_month(year, month)

if __name__ == "__main__":
    auto_update()
